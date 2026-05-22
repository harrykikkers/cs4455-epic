import os
import base64
import threading
import requests
import customtkinter as ctk
from tkinter import messagebox

from config import BASE_URL, VERIFY_SSL


def _dummy_msg_fields():
    b64 = lambda b: base64.b64encode(b).decode()
    return {
        "enc": b64(os.urandom(32)),
        "ciphertext": b64(os.urandom(64)),
        "nonce": b64(os.urandom(12)),
        "signature": b64(os.urandom(64)),
        "seqNo": 0,
        "digest": "0x" + "00" * 32,
    }


class MainFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color="transparent")
        self.app = app
        self._conversations = {}
        self._active_peer   = None
        self._plaintext_cache = {}

        # Left sidebar
        sidebar = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color=("#111111", "#111111"))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="Chats",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 8), padx=16, anchor="w")
        ctk.CTkButton(sidebar, text="+ New Chat", height=34,
                      command=self._new_chat).pack(padx=12, pady=(0, 8), fill="x")

        self._conv_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._conv_list.pack(fill="both", expand=True, padx=4)

        ctk.CTkLabel(sidebar, text=f"Logged in as {app.username}",
                     font=ctk.CTkFont(size=11), text_color="#888").pack(padx=12, pady=(4, 2))
        ctk.CTkButton(sidebar, text="Logout", height=30, fg_color="transparent",
                      border_width=1, command=self._logout).pack(padx=12, pady=(2, 10), fill="x")

        # Right chat panel
        right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        self._header = ctk.CTkFrame(right, height=50, corner_radius=0, fg_color=("#1a1a1a", "#1a1a1a"))
        self._header.pack(fill="x")
        self._header.pack_propagate(False)
        self._peer_label = ctk.CTkLabel(self._header, text="Select a chat",
                                        font=ctk.CTkFont(size=14, weight="bold"))
        self._peer_label.pack(side="left", padx=16)
        ctk.CTkButton(self._header, text="Refresh", width=80, height=30,
                      command=self._load).pack(side="right", padx=12, pady=10)

        self._msg_area = ctk.CTkScrollableFrame(right, fg_color=("#f5f5f5", "#222222"))
        self._msg_area.pack(fill="both", expand=True)

        input_bar = ctk.CTkFrame(right, height=60, corner_radius=0)
        input_bar.pack(fill="x", side="bottom")
        input_bar.pack_propagate(False)
        self._msg_input = ctk.CTkEntry(input_bar, placeholder_text="Type a message...", height=38)
        self._msg_input.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=11)
        self._msg_input.bind("<Return>", lambda e: self._send())
        ctk.CTkButton(input_bar, text="Send", width=80, height=38,
                      command=self._send).pack(side="right", padx=(0, 12), pady=11)

        self._load()

    def _load(self):
        headers = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                inbox = requests.get(f"{BASE_URL}/api/messages/inbox",
                                     headers=headers, verify=VERIFY_SSL).json().get("data", [])
                sent  = requests.get(f"{BASE_URL}/api/messages/sent",
                                     headers=headers, verify=VERIFY_SSL).json().get("data", [])
                self.app.after(0, lambda: self._populate(inbox, sent))
            except Exception as e:
                print(f"Load error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _populate(self, inbox, sent):
        self._conversations = {}

        for m in inbox:
            m["_mine"] = False
            peer_id   = m.get("sender_id", "")
            peer_name = m.get("sender_username") or peer_id
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {"name": peer_name, "messages": []}
            self._conversations[peer_id]["messages"].append(m)

        for m in sent:
            m["_mine"] = True
            peer_id   = m.get("recipient_id", "")
            peer_name = m.get("recipient_username") or peer_id
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {"name": peer_name, "messages": []}
            self._conversations[peer_id]["messages"].append(m)

        for data in self._conversations.values():
            data["messages"].sort(key=lambda m: m.get("created_at", ""))

        for w in self._conv_list.winfo_children():
            w.destroy()

        if not self._conversations:
            ctk.CTkLabel(self._conv_list, text="No chats yet.",
                         text_color="gray").pack(pady=20)
        for pid, data in self._conversations.items():
            self._make_conv_row(pid, data["name"], len(data["messages"]))

        if self._active_peer and self._active_peer in self._conversations:
            self._open_chat(self._active_peer)

    def _make_conv_row(self, peer_id, name, count):
        btn = ctk.CTkButton(
            self._conv_list, text=f"  {name}\n  {count} message{'s' if count != 1 else ''}",
            height=56, anchor="w", fg_color="transparent", hover_color=("#333333", "#333333"),
            font=ctk.CTkFont(size=13),
            command=lambda p=peer_id: self._open_chat(p)
        )
        btn.pack(fill="x", pady=2)

    def _open_chat(self, peer_id):
        self._active_peer = peer_id
        self._peer_label.configure(text=self._conversations[peer_id]["name"])
        for w in self._msg_area.winfo_children():
            w.destroy()
        for m in self._conversations[peer_id]["messages"]:
            self._make_msg_bubble(m)

    def _make_msg_bubble(self, m):
        mine      = m.get("_mine", False)
        bg        = ("#111111", "#111111") if mine else ("#ffffff", "#e0e0e0")
        name_col  = "#ffffff" if mine else "#111111"
        time_col  = "#aaaaaa" if mine else "#555555"
        side      = "e" if mine else "w"
        name      = "You" if mine else (m.get("sender_username") or m.get("sender_id", ""))

        bubble = ctk.CTkFrame(self._msg_area, fg_color=bg, corner_radius=10)
        bubble.pack(anchor=side, pady=4, padx=12)
        ctk.CTkLabel(bubble, text=name,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=name_col).pack(anchor="w", padx=10, pady=(6, 0))
        plaintext  = m.get("plaintext")
        body_text  = plaintext if plaintext else "(end-to-end encrypted)"
        body_color = name_col if plaintext else ("#888888" if mine else "#999999")
        ctk.CTkLabel(bubble, text=body_text,
                     font=ctk.CTkFont(size=12), text_color=body_color,
                     wraplength=400, justify="left").pack(anchor="w", padx=10)
        ctk.CTkLabel(bubble, text=m.get("created_at", ""),
                     font=ctk.CTkFont(size=10), text_color=time_col).pack(anchor="e", padx=10, pady=(0, 6))

    def _send(self):
        if not self._active_peer:
            messagebox.showinfo("Send", "Select a chat first.")
            return
        text = self._msg_input.get().strip()
        if not text:
            return
        self._msg_input.delete(0, "end")

        headers = {"Authorization": f"Bearer {self.app.token}"}
        payload = {"recipientId": self._active_peer, **_dummy_msg_fields()}

        def run():
            try:
                resp = requests.post(f"{BASE_URL}/api/messages",
                                     json=payload, headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                msg_id = resp.json().get("data", {}).get("messageId")
                if msg_id:
                    self._plaintext_cache[msg_id] = text
                self.app.after(0, self._load)
            except requests.exceptions.HTTPError as e:
                msg = e.response.json().get("error", {}).get("message", str(e))
                self.app.after(0, lambda m=msg: messagebox.showerror("Send failed", m))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _new_chat(self):
        dialog  = ctk.CTkInputDialog(text="Enter recipient username:", title="New Chat")
        username = dialog.get_input()
        if not username:
            return
        username = username.strip()
        headers  = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                resp = requests.get(f"{BASE_URL}/api/auth/user",
                                    params={"username": username},
                                    headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                user    = resp.json()["data"]
                peer_id = user["userId"]
                name    = user["username"]
                def open_chat():
                    if peer_id not in self._conversations:
                        self._conversations[peer_id] = {"name": name, "messages": []}
                        self._make_conv_row(peer_id, name, 0)
                    self._open_chat(peer_id)
                self.app.after(0, open_chat)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    self.app.after(0, lambda: messagebox.showerror("Not found", f'No user "{username}" exists.'))
                else:
                    self.app.after(0, lambda: messagebox.showerror("Error", str(e)))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _logout(self):
        self.app.token = None
        self.app._show_login()
