import os
import base64
import threading
import requests
import customtkinter as ctk
from tkinter import messagebox, filedialog

from config import BASE_URL, VERIFY_SSL

DEV_MODE_TOKEN = "dev-token"

# --- Demo data for navigating the GUI without a backend ---

_DEMO_CONVERSATIONS = {
    "user-alice-id": {
        "name": "alice",
        "key_warning": False,
        "messages": [
            {
                "messageId": "msg-001", "sender_id": "user-alice-id",
                "sender_username": "alice", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": "Hey, are you free to chat?",
                "created_at": "2025-05-20 09:15", "chain_status": "recorded",
            },
            {
                "messageId": "msg-002", "sender_id": "dev-user-id",
                "sender_username": "test", "recipient_id": "user-alice-id",
                "recipient_username": "alice", "_mine": True,
                "plaintext": "Yeah! What's up?",
                "created_at": "2025-05-20 09:17", "chain_status": "recorded",
            },
            {
                "messageId": "msg-003", "sender_id": "user-alice-id",
                "sender_username": "alice", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": "Wanted to share the project notes with you. Check your downloads.",
                "created_at": "2025-05-20 09:20", "chain_status": "pending",
                "_forwarded_to": [
                    {"username": "carol", "user_id": "user-carol-id",
                     "forwarded_at": "2025-05-20 09:25"},
                ],
            },
        ],
    },
    "user-bob-id": {
        "name": "bob",
        "key_warning": True,
        "messages": [
            {
                "messageId": "msg-004", "sender_id": "dev-user-id",
                "sender_username": "test", "recipient_id": "user-bob-id",
                "recipient_username": "bob", "_mine": True,
                "plaintext": "Meeting at 3pm tomorrow?",
                "created_at": "2025-05-19 14:00", "chain_status": "recorded",
            },
            {
                "messageId": "msg-005", "sender_id": "user-bob-id",
                "sender_username": "bob", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": "Works for me. I'll send the agenda.",
                "created_at": "2025-05-19 14:05", "chain_status": "recorded",
            },
        ],
    },
    "user-carol-id": {
        "name": "carol",
        "key_warning": False,
        "messages": [
            {
                "messageId": "msg-006", "sender_id": "user-carol-id",
                "sender_username": "carol", "recipient_id": "dev-user-id",
                "recipient_username": "test", "_mine": False,
                "plaintext": None,
                "created_at": "2025-05-21 11:00", "chain_status": "pending",
            },
        ],
    },
}


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


def _format_time(raw, short=False):
    """Format '2025-05-20 09:15' into shorter forms."""
    if not raw:
        return ""
    try:
        from datetime import datetime, date
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        today = date.today()
        hour = dt.strftime("%I:%M %p").lstrip("0")
        if dt.date() == today:
            return hour
        elif dt.year == today.year:
            day = str(dt.day)
            if short:
                return f"{dt.strftime('%b')} {day}"
            return f"{dt.strftime('%b')} {day}, {hour}"
        else:
            day = str(dt.day)
            return f"{dt.strftime('%b')} {day} {dt.year}"
    except (ValueError, TypeError):
        return raw


class MainFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color="transparent")
        self.app = app
        self._conversations = {}
        self._active_peer = None
        self._selected_msg = None
        self._plaintext_cache = {}
        self._dev = app.token == DEV_MODE_TOKEN

        # ── Left sidebar ──
        sidebar = ctk.CTkFrame(self, width=280, corner_radius=0,
                               fg_color=("#0d0d0d", "#0d0d0d"))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Sidebar / chat divider
        divider = ctk.CTkFrame(self, width=1, fg_color=("#333333", "#333333"),
                               corner_radius=0)
        divider.pack(side="left", fill="y")

        ctk.CTkLabel(sidebar, text="Zebra",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(
                         pady=(18, 2), padx=16, anchor="w")
        ctk.CTkLabel(sidebar, text="Secure Messenger",
                     font=ctk.CTkFont(size=11), text_color="#666").pack(
                         padx=16, anchor="w")
        ctk.CTkLabel(sidebar, text=f"Logged in as {app.username}",
                     font=ctk.CTkFont(size=12), text_color="#888").pack(
                         padx=16, anchor="w", pady=(2, 0))

        ctk.CTkButton(sidebar, text="+ New Chat", height=36,
                      command=self._new_chat).pack(padx=14, pady=(16, 4), fill="x")

        # Search / filter
        self._search = ctk.CTkEntry(sidebar, placeholder_text="Search chats...",
                                    height=32)
        self._search.pack(padx=14, pady=(4, 10), fill="x")
        self._search.bind("<KeyRelease>", lambda e: self._filter_chats())

        self._conv_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._conv_list.pack(fill="both", expand=True, padx=4)

        # Bottom sidebar section
        bottom = ctk.CTkFrame(sidebar, fg_color=("#151515", "#151515"),
                              corner_radius=0)
        bottom.pack(fill="x", side="bottom")

        # Thin top border for bottom section
        ctk.CTkFrame(bottom, height=1, fg_color=("#333333", "#333333"),
                     corner_radius=0).pack(fill="x")


        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(10, 12))
        ctk.CTkButton(btn_row, text="Account", height=30, width=115,
                      fg_color="#1e1e1e", hover_color="#2a2a2a",
                      command=self._show_account).pack(
                          side="left", expand=True, padx=(0, 4))
        ctk.CTkButton(btn_row, text="Logout", height=30, width=115,
                      fg_color="#1e1e1e", hover_color="#2a2a2a",
                      text_color="#ef4444",
                      command=self._logout).pack(
                          side="right", expand=True, padx=(4, 0))

        # ── Right chat panel ──
        right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Header
        self._header = ctk.CTkFrame(right, height=64, corner_radius=0,
                                    fg_color=("#141414", "#141414"))
        self._header.pack(fill="x")
        self._header.pack_propagate(False)

        self._peer_label = ctk.CTkLabel(
            self._header, text="Select a chat",
            font=ctk.CTkFont(size=16, weight="bold"))
        self._peer_label.pack(side="left", padx=18)

        ctk.CTkButton(self._header, text="Refresh", width=70, height=28,
                      fg_color="#1e1e1e", hover_color="#2a2a2a",
                      command=self._load).pack(side="right", padx=14, pady=18)

        # Header bottom border
        ctk.CTkFrame(right, height=1, fg_color=("#333333", "#333333"),
                     corner_radius=0).pack(fill="x")

        # Key warning banner (hidden by default)
        self._key_banner = ctk.CTkFrame(right, height=44, corner_radius=0,
                                        fg_color=("#7c2d12", "#7c2d12"))
        self._key_banner_label = ctk.CTkLabel(
            self._key_banner,
            text="  Warning: This contact's encryption key has changed. Verify their identity.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24", anchor="w")
        self._key_banner_label.pack(side="left", fill="x", expand=True, padx=12)
        ctk.CTkButton(self._key_banner, text="Details", width=70, height=26,
                      fg_color="#991b1b", hover_color="#7f1d1d",
                      command=self._show_key_warning_details).pack(
                          side="right", padx=12, pady=9)
        # banner is packed/unpacked dynamically

        # Message area
        self._msg_area = ctk.CTkScrollableFrame(right, fg_color=("#181818", "#181818"))
        self._msg_area.pack(fill="both", expand=True)

        # Empty state
        self._empty_label = ctk.CTkLabel(
            self._msg_area,
            text="Select a conversation to start messaging",
            text_color="#555", font=ctk.CTkFont(size=14))
        self._empty_label.pack(expand=True, pady=100)

        # Input bar
        ctk.CTkFrame(right, height=1, fg_color=("#333333", "#333333"),
                     corner_radius=0).pack(fill="x", side="bottom")
        input_bar = ctk.CTkFrame(right, height=64, corner_radius=0,
                                 fg_color=("#141414", "#141414"))
        input_bar.pack(fill="x", side="bottom")
        input_bar.pack_propagate(False)

        self._msg_input = ctk.CTkEntry(input_bar,
                                       placeholder_text="Type a message...",
                                       height=40)
        self._msg_input.pack(side="left", fill="x", expand=True,
                             padx=(14, 8), pady=12)
        self._msg_input.bind("<Return>", lambda e: self._send())
        ctk.CTkButton(input_bar, text="Send", width=80, height=40,
                      command=self._send).pack(side="right", padx=(0, 14), pady=12)

        self._load()

    # ── Data loading ──

    def _load(self):
        if self._dev:
            self._populate_dev()
            return
        headers = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                inbox = requests.get(f"{BASE_URL}/api/messages/inbox",
                                     headers=headers, verify=VERIFY_SSL
                                     ).json().get("data", [])
                sent = requests.get(f"{BASE_URL}/api/messages/sent",
                                    headers=headers, verify=VERIFY_SSL
                                    ).json().get("data", [])
                self.app.after(0, lambda: self._populate(inbox, sent))
            except Exception as e:
                print(f"Load error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _populate_dev(self):
        import copy
        self._conversations = copy.deepcopy(_DEMO_CONVERSATIONS)
        self._rebuild_conv_list()
        if self._active_peer and self._active_peer in self._conversations:
            self._open_chat(self._active_peer)

    def _populate(self, inbox, sent):
        self._conversations = {}
        for m in inbox:
            m["_mine"] = False
            peer_id = m.get("sender_id", "")
            peer_name = m.get("sender_username") or peer_id
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {
                    "name": peer_name, "messages": [], "key_warning": False}
            self._conversations[peer_id]["messages"].append(m)
        for m in sent:
            m["_mine"] = True
            peer_id = m.get("recipient_id", "")
            peer_name = m.get("recipient_username") or peer_id
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {
                    "name": peer_name, "messages": [], "key_warning": False}
            self._conversations[peer_id]["messages"].append(m)
        for data in self._conversations.values():
            data["messages"].sort(key=lambda m: m.get("created_at", ""))
        self._rebuild_conv_list()
        if self._active_peer and self._active_peer in self._conversations:
            self._open_chat(self._active_peer)

    def _rebuild_conv_list(self):
        for w in self._conv_list.winfo_children():
            w.destroy()
        if not self._conversations:
            ctk.CTkLabel(self._conv_list, text="No chats yet.",
                         text_color="gray").pack(pady=20)
        for pid, data in self._conversations.items():
            self._make_conv_row(pid, data)

    def _filter_chats(self):
        query = self._search.get().strip().lower()
        for w in self._conv_list.winfo_children():
            w.destroy()
        for pid, data in self._conversations.items():
            if query and query not in data["name"].lower():
                continue
            self._make_conv_row(pid, data)

    def _make_conv_row(self, peer_id, data):
        name = data["name"]
        messages = data["messages"]
        key_warning = data.get("key_warning", False)
        is_active = peer_id == self._active_peer

        fg = ("#222222", "#222222") if is_active else ("#141414", "#141414")
        border_col = "#2563eb" if is_active else "#2a2a2a"

        card = ctk.CTkFrame(self._conv_list, fg_color=fg, corner_radius=10,
                            border_width=2 if is_active else 1,
                            border_color=border_col)
        card.pack(fill="x", pady=3, padx=4)
        card.bind("<Button-1>", lambda e, p=peer_id: self._open_chat(p))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        inner.bind("<Button-1>", lambda e, p=peer_id: self._open_chat(p))

        # Top row: name + warning indicator
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")
        top_row.bind("<Button-1>", lambda e, p=peer_id: self._open_chat(p))

        name_label = ctk.CTkLabel(
            top_row, text=name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff", anchor="w")
        name_label.pack(side="left")
        name_label.bind("<Button-1>", lambda e, p=peer_id: self._open_chat(p))

        # Timestamp (always shown if messages exist)
        if messages:
            time_label = ctk.CTkLabel(
                top_row, text=_format_time(messages[-1].get("created_at", ""),
                                           short=True),
                font=ctk.CTkFont(size=10), text_color="#666")
            time_label.pack(side="right")
            time_label.bind("<Button-1>", lambda e, p=peer_id: self._open_chat(p))

        if key_warning:
            warn_label = ctk.CTkLabel(
                inner, text="KEY CHANGED",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color="#0d0d0d", fg_color="#fbbf24",
                corner_radius=4, width=80, height=16)
            warn_label.pack(anchor="w", pady=(2, 0))
            warn_label.bind("<Button-1>", lambda e, p=peer_id: self._open_chat(p))

        # Last message preview
        if messages:
            last = messages[-1]
            preview_text = last.get("plaintext") or "(encrypted)"
            if len(preview_text) > 34:
                preview_text = preview_text[:34] + "..."
            preview = f"You: {preview_text}" if last.get("_mine") else preview_text
            preview_label = ctk.CTkLabel(
                inner, text=preview,
                font=ctk.CTkFont(size=11), text_color="#888", anchor="w")
            preview_label.pack(anchor="w", pady=(2, 0))
            preview_label.bind("<Button-1>",
                               lambda e, p=peer_id: self._open_chat(p))

    # ── Chat area ──

    def _open_chat(self, peer_id):
        self._active_peer = peer_id
        self._selected_msg = None
        conv = self._conversations[peer_id]
        self._peer_label.configure(text=conv["name"])


        # Key warning banner
        self._key_banner.pack_forget()
        if conv.get("key_warning"):
            self._key_banner.pack(fill="x", before=self._msg_area)

        # Rebuild message area
        for w in self._msg_area.winfo_children():
            w.destroy()

        if not conv["messages"]:
            ctk.CTkLabel(self._msg_area,
                         text="No messages yet. Say hello!",
                         text_color="#555", font=ctk.CTkFont(size=14)
                         ).pack(pady=60)
        else:
            for m in conv["messages"]:
                self._make_msg_bubble(m)

        # Refresh sidebar to show active highlight
        self._rebuild_conv_list()

    def _make_msg_bubble(self, m):
        mine = m.get("_mine", False)
        bg = ("#1e3a5f", "#1e3a5f") if mine else ("#252525", "#252525")
        text_col = "#ffffff"
        time_col = "#7799bb" if mine else "#666666"
        side = "e" if mine else "w"

        # Outer wrapper for alignment
        wrapper = ctk.CTkFrame(self._msg_area, fg_color="transparent")
        wrapper.pack(fill="x", pady=4, padx=12)

        bubble = ctk.CTkFrame(wrapper, fg_color=bg, corner_radius=14,
                              border_width=1,
                              border_color=("#2a4a6f", "#2a4a6f") if mine
                              else ("#333333", "#333333"))
        bubble.pack(anchor=side, padx=4)

        # Message body
        plaintext = m.get("plaintext")
        if plaintext:
            ctk.CTkLabel(bubble, text=plaintext,
                         font=ctk.CTkFont(size=13), text_color=text_col,
                         wraplength=480, justify="left").pack(
                             anchor="w", padx=14, pady=(10, 0))
        else:
            # Encrypted / undecrypted message
            enc_frame = ctk.CTkFrame(bubble, fg_color=("#1a1a1a", "#1a1a1a"),
                                     corner_radius=8)
            enc_frame.pack(padx=10, pady=(10, 0), fill="x")
            ctk.CTkLabel(enc_frame, text="Encrypted message",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#888").pack(padx=10, pady=(6, 2), anchor="w")
            ctk.CTkLabel(enc_frame, text="Decryption key required to view",
                         font=ctk.CTkFont(size=10),
                         text_color="#555").pack(padx=10, pady=(0, 6), anchor="w")

        # Timestamp
        ctk.CTkLabel(bubble, text=_format_time(m.get("created_at", "")),
                     font=ctk.CTkFont(size=10), text_color=time_col).pack(
                         anchor="w" if not mine else "e",
                         padx=14, pady=(4, 2))

        # Action buttons — hidden until bubble is clicked
        action_btns = ctk.CTkFrame(bubble, fg_color="transparent")
        # Not packed yet — toggled on click

        btn_kw = dict(height=24, font=ctk.CTkFont(size=11),
                      fg_color="transparent", border_width=1,
                      border_color="#3a3a3a", hover_color=("#333333", "#333333"))

        self._build_action_buttons(action_btns, m, mine, btn_kw)

        def toggle_actions(event=None):
            if action_btns.winfo_ismapped():
                action_btns.pack_forget()
            else:
                action_btns.pack(fill="x", padx=10, pady=(2, 8))

        # Bind click to bubble and all its non-button children
        def _bind_recursive(widget):
            widget.bind("<Button-1>", toggle_actions)
            for child in widget.winfo_children():
                if not isinstance(child, ctk.CTkButton):
                    _bind_recursive(child)
        _bind_recursive(bubble)

    def _build_action_buttons(self, frame, m, mine, btn_kw):
        ctk.CTkButton(frame, text="Details", width=65,
                      text_color="#a78bfa", **btn_kw,
                      command=lambda msg=m: self._show_msg_detail(msg)
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(frame, text="Forward", width=70,
                      text_color="#3b82f6", **btn_kw,
                      command=lambda msg=m: self._forward_msg(msg)
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(frame, text="Download", width=80,
                      text_color="#22c55e", **btn_kw,
                      command=lambda msg=m: self._download_msg(msg)
                      ).pack(side="left", padx=(0, 4))
        if mine:
            ctk.CTkButton(frame, text="Delete", width=65,
                          text_color="#ef4444", **btn_kw,
                          command=lambda msg=m: self._delete_msg(msg)
                          ).pack(side="left", padx=(0, 4))

    # ── Message actions ──

    def _send(self):
        if not self._active_peer:
            messagebox.showinfo("Send", "Select a chat first.")
            return
        text = self._msg_input.get().strip()
        if not text:
            return
        self._msg_input.delete(0, "end")

        if self._dev:
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            msg = {
                "messageId": f"msg-dev-{os.urandom(4).hex()}",
                "sender_id": "dev-user-id", "sender_username": "test",
                "recipient_id": self._active_peer,
                "recipient_username": self._conversations[self._active_peer]["name"],
                "_mine": True, "plaintext": text,
                "created_at": now, "chain_status": "pending",
            }
            self._conversations[self._active_peer]["messages"].append(msg)
            self._open_chat(self._active_peer)
            return

        headers = {"Authorization": f"Bearer {self.app.token}"}
        payload = {"recipientId": self._active_peer, **_dummy_msg_fields()}
        def run():
            try:
                resp = requests.post(f"{BASE_URL}/api/messages",
                                     json=payload, headers=headers,
                                     verify=VERIFY_SSL)
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

    def _forward_msg(self, m):
        dialog = ctk.CTkInputDialog(
            text=f"Forward message from {m.get('sender_username', '?')}.\n"
                 f"Enter recipient username:",
            title="Forward Message")
        recipient = dialog.get_input()
        if not recipient or not recipient.strip():
            return
        recipient = recipient.strip()

        if self._dev:
            import datetime
            if "_forwarded_to" not in m:
                m["_forwarded_to"] = []
            m["_forwarded_to"].append({
                "username": recipient,
                "user_id": f"user-{recipient}-id",
                "forwarded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            messagebox.showinfo(
                "Forwarded",
                f"Message forwarded to {recipient}.\n\n"
                f"(In production this will re-encrypt the message\n"
                f"under {recipient}'s public key and submit\n"
                f"a new keccak256 hash on-chain.)")
            return

        headers = {"Authorization": f"Bearer {self.app.token}"}
        msg_id = m.get("messageId")
        def run():
            try:
                resp = requests.get(f"{BASE_URL}/api/auth/user",
                                    params={"username": recipient},
                                    headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                rid = resp.json()["data"]["userId"]
                fields = _dummy_msg_fields()
                resp2 = requests.post(
                    f"{BASE_URL}/api/messages/{msg_id}/forward",
                    json={"recipientId": rid, "enc": fields["enc"],
                          "ciphertext": fields["ciphertext"],
                          "nonce": fields["nonce"]},
                    headers=headers, verify=VERIFY_SSL)
                resp2.raise_for_status()
                self.app.after(0, lambda: messagebox.showinfo(
                    "Forwarded", f"Message forwarded to {recipient}."))
                self.app.after(0, self._load)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    self.app.after(0, lambda: messagebox.showerror(
                        "Not found", f'No user "{recipient}" exists.'))
                else:
                    msg = str(e)
                    self.app.after(0, lambda m=msg: messagebox.showerror("Error", m))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _delete_msg(self, m):
        ok = messagebox.askyesno(
            "Delete Message",
            "Are you sure you want to delete this message?\n"
            "This action cannot be undone.")
        if not ok:
            return

        msg_id = m.get("messageId")

        if self._dev:
            conv = self._conversations.get(self._active_peer)
            if conv:
                conv["messages"] = [
                    x for x in conv["messages"]
                    if x.get("messageId") != msg_id]
            self._open_chat(self._active_peer)
            return

        headers = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                resp = requests.delete(f"{BASE_URL}/api/messages/{msg_id}",
                                       headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                self.app.after(0, self._load)
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _show_msg_detail(self, m):
        win = ctk.CTkToplevel(self.app)
        win.title("Message Details")
        win.geometry("460x500")
        win.resizable(False, False)
        win.grab_set()

        ctk.CTkLabel(win, text="Message Details",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 12))

        # Message info
        info = ctk.CTkFrame(win, fg_color=("#1e1e1e", "#1e1e1e"), corner_radius=10,
                            border_width=1, border_color="#2a2a2a")
        info.pack(fill="x", padx=20, pady=(0, 12))

        sender = m.get("sender_username") or m.get("sender_id", "?")
        ctk.CTkLabel(info, text=f"From:  {sender}",
                     font=ctk.CTkFont(size=13)).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(info, text=f"Date:  {m.get('created_at', '?')}",
                     font=ctk.CTkFont(size=13), text_color="#888").pack(
                         anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(info, text=f"ID:      {m.get('messageId', '?')}",
                     font=ctk.CTkFont(size=11), text_color="#555").pack(
                         anchor="w", padx=14, pady=(0, 4))

        chain = m.get("chain_status", "unknown")
        chain_colors = {
            "recorded": "#22c55e", "pending": "#eab308", "unknown": "#555555"}
        chain_row = ctk.CTkFrame(info, fg_color="transparent")
        chain_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(chain_row, text="Chain:",
                     font=ctk.CTkFont(size=12), text_color="#888").pack(
                         side="left")
        ctk.CTkButton(chain_row, text=chain, width=80, height=22,
                      font=ctk.CTkFont(size=11, weight="bold"),
                      fg_color="transparent", border_width=1,
                      border_color=chain_colors.get(chain, "#555"),
                      text_color=chain_colors.get(chain, "#555"),
                      hover_color=("#252525", "#252525"),
                      command=lambda msg=m: self._view_chain(msg)).pack(
                          side="left", padx=(6, 0))

        plaintext = m.get("plaintext")
        body = plaintext if plaintext else "(end-to-end encrypted)"
        body_color = "#ffffff" if plaintext else "#888"
        msg_frame = ctk.CTkFrame(info, fg_color=("#141414", "#141414"),
                                 corner_radius=8)
        msg_frame.pack(fill="x", padx=10, pady=(0, 12))
        ctk.CTkLabel(msg_frame, text=body, font=ctk.CTkFont(size=13),
                     text_color=body_color, wraplength=380,
                     justify="left").pack(padx=12, pady=10, anchor="w")

        # Forwarded-to section
        ctk.CTkLabel(win, text="Forwarded To",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
                         anchor="w", padx=24, pady=(4, 6))

        fwd_list = m.get("_forwarded_to", [])

        fwd_frame = ctk.CTkScrollableFrame(win, height=120,
                                           fg_color=("#1e1e1e", "#1e1e1e"),
                                           corner_radius=10)
        fwd_frame.pack(fill="x", padx=20, pady=(0, 12))

        if not fwd_list:
            ctk.CTkLabel(fwd_frame, text="Not forwarded to anyone.",
                         text_color="#555", font=ctk.CTkFont(size=12)).pack(
                             pady=16)
        else:
            for fwd in fwd_list:
                row = ctk.CTkFrame(fwd_frame, fg_color=("#252525", "#252525"),
                                   corner_radius=8)
                row.pack(fill="x", padx=6, pady=3)

                ctk.CTkLabel(row, text=fwd["username"],
                             font=ctk.CTkFont(size=13, weight="bold")).pack(
                                 side="left", padx=(10, 8), pady=8)
                ctk.CTkLabel(row, text=fwd.get("forwarded_at", ""),
                             font=ctk.CTkFont(size=10),
                             text_color="#666").pack(side="left")

                ctk.CTkButton(
                    row, text="Revoke", width=65, height=26,
                    font=ctk.CTkFont(size=11),
                    fg_color="#991b1b", hover_color="#7f1d1d",
                    text_color="#ffffff",
                    command=lambda f=fwd, msg=m, w=win: self._revoke_access(
                        msg, f, w)
                ).pack(side="right", padx=8, pady=6)

        # Bottom actions
        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="Forward", height=36, width=130,
                      command=lambda: (win.destroy(), self._forward_msg(m))
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Download", height=36, width=130,
                      fg_color="#166534", hover_color="#14532d",
                      command=lambda: (win.destroy(), self._download_msg(m))
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Close", height=36, width=90,
                      fg_color="#1e1e1e", hover_color="#2a2a2a",
                      command=win.destroy).pack(side="right")

    def _revoke_access(self, m, fwd, detail_win):
        username = fwd["username"]
        user_id = fwd["user_id"]
        ok = messagebox.askyesno(
            "Revoke Access",
            f"Revoke {username}'s access to this message?\n\n"
            f"They will no longer be able to fetch or\n"
            f"decrypt this message from the server.")
        if not ok:
            return

        if self._dev:
            fwd_list = m.get("_forwarded_to", [])
            m["_forwarded_to"] = [f for f in fwd_list
                                  if f["user_id"] != user_id]
            detail_win.destroy()
            self._show_msg_detail(m)
            messagebox.showinfo("Revoked",
                                f"{username}'s access has been revoked.")
            return

        msg_id = m.get("messageId")
        headers = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                resp = requests.post(
                    f"{BASE_URL}/api/messages/{msg_id}/revoke",
                    json={"userId": user_id},
                    headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                self.app.after(0, lambda: messagebox.showinfo(
                    "Revoked", f"{username}'s access has been revoked."))
                self.app.after(0, self._load)
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror(
                    "Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _download_msg(self, m):
        plaintext = m.get("plaintext")
        if not plaintext:
            messagebox.showinfo(
                "Download",
                "Cannot download — message has not been decrypted yet.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Message",
            defaultextension=".txt",
            initialfile=f"message_{m.get('messageId', 'unknown')}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return

        try:
            with open(path, "w") as f:
                f.write(f"From: {m.get('sender_username', '?')}\n")
                f.write(f"Date: {m.get('created_at', '?')}\n")
                f.write(f"Message ID: {m.get('messageId', '?')}\n")
                f.write(f"---\n{plaintext}\n")
            messagebox.showinfo("Downloaded", f"Message saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _view_chain(self, m):
        msg_id = m.get("messageId", "?")
        chain = m.get("chain_status", "unknown")

        if self._dev or chain in ("pending", "unknown"):
            info = (
                f"Message ID: {msg_id}\n"
                f"Chain status: {chain}\n"
                f"Digest hash: 0x{'0' * 64}\n"
                f"Transaction: {'(pending — not yet recorded)' if chain != 'recorded' else '0xabc...def'}\n"
                f"\nThe keccak256 hash of this message is recorded on\n"
                f"the Sepolia testnet for tamper-proof verification."
            )
            messagebox.showinfo("Blockchain Proof", info)
            return

        headers = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                resp = requests.get(
                    f"{BASE_URL}/api/messages/{msg_id}/chain",
                    headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                data = resp.json()["data"]
                info = (
                    f"Message ID: {data.get('messageId', msg_id)}\n"
                    f"Chain status: {data.get('chainStatus', '?')}\n"
                    f"Digest hash: {data.get('digestHash', '?')}\n"
                    f"Transaction: {data.get('txHash', '(none)')}\n"
                    f"Recorded at: {data.get('recordedAt', '?')}"
                )
                self.app.after(0, lambda: messagebox.showinfo(
                    "Blockchain Proof", info))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    # ── Key warning ──

    def _show_key_warning_details(self):
        peer = self._conversations.get(self._active_peer, {}).get("name", "?")
        win = ctk.CTkToplevel(self.app)
        win.title("Key Change Detected")
        win.geometry("420x340")
        win.resizable(False, False)
        win.grab_set()

        ctk.CTkLabel(win, text="Key Change Detected",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#fbbf24").pack(pady=(20, 12))

        info = ctk.CTkFrame(win, fg_color=("#1e1e1e", "#1e1e1e"),
                            corner_radius=10, border_width=1,
                            border_color="#7c2d12")
        info.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkLabel(info, text=f"{peer}'s encryption key has changed since\n"
                     f"your last interaction. This could mean:",
                     font=ctk.CTkFont(size=12), justify="left",
                     wraplength=360).pack(padx=14, pady=(12, 8), anchor="w")

        ctk.CTkLabel(info, text="1. They rotated their key (normal)\n"
                     "2. Someone is intercepting messages (attack)",
                     font=ctk.CTkFont(size=12), text_color="#888",
                     justify="left").pack(padx=14, pady=(0, 8), anchor="w")

        ctk.CTkLabel(info, text="Verify their identity through a separate\n"
                     "channel before continuing.",
                     font=ctk.CTkFont(size=12), text_color="#fbbf24",
                     justify="left").pack(padx=14, pady=(0, 12), anchor="w")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        def accept():
            if self._active_peer and self._active_peer in self._conversations:
                self._conversations[self._active_peer]["key_warning"] = False
            win.destroy()
            self._key_banner.pack_forget()
            self._rebuild_conv_list()

        ctk.CTkButton(btn_row, text="Accept New Key", height=36, width=140,
                      fg_color="#166534", hover_color="#14532d",
                      command=accept).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="View History", height=36, width=120,
                      fg_color="#1e1e1e", hover_color="#2a2a2a",
                      command=lambda: messagebox.showinfo(
                          "Key History",
                          f"Key history for {peer}:\n\n"
                          f"(Will query GET /api/keys/{peer}/history\n"
                          f"after crypto implementation)")
                      ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Reject", height=36, width=90,
                      fg_color="#991b1b", hover_color="#7f1d1d",
                      command=win.destroy).pack(side="right")

    # ── New chat ──

    def _new_chat(self):
        dialog = ctk.CTkInputDialog(
            text="Enter recipient username:", title="New Chat")
        username = dialog.get_input()
        if not username:
            return
        username = username.strip()

        if self._dev:
            peer_id = f"user-{username}-id"
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {
                    "name": username, "messages": [], "key_warning": False}
            self._rebuild_conv_list()
            self._open_chat(peer_id)
            return

        headers = {"Authorization": f"Bearer {self.app.token}"}
        def run():
            try:
                resp = requests.get(f"{BASE_URL}/api/auth/user",
                                    params={"username": username},
                                    headers=headers, verify=VERIFY_SSL)
                resp.raise_for_status()
                user = resp.json()["data"]
                peer_id = user["userId"]
                name = user["username"]
                def open_chat():
                    if peer_id not in self._conversations:
                        self._conversations[peer_id] = {
                            "name": name, "messages": [], "key_warning": False}
                        self._make_conv_row(peer_id,
                                            self._conversations[peer_id])
                    self._open_chat(peer_id)
                self.app.after(0, open_chat)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    self.app.after(0, lambda: messagebox.showerror(
                        "Not found", f'No user "{username}" exists.'))
                else:
                    self.app.after(0, lambda: messagebox.showerror("Error", str(e)))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    # ── Account ──

    def _show_account(self):
        win = ctk.CTkToplevel(self.app)
        win.title("Account Settings")
        win.geometry("420x500")
        win.resizable(False, False)
        win.grab_set()

        ctk.CTkLabel(win, text="Account Settings",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 16))

        info = ctk.CTkFrame(win, fg_color=("#1e1e1e", "#1e1e1e"), corner_radius=10,
                            border_width=1, border_color="#2a2a2a")
        info.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkLabel(info, text=f"Username:  {self.app.username}",
                     font=ctk.CTkFont(size=13)).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(info, text=f"User ID:     {self.app.user_id}",
                     font=ctk.CTkFont(size=13), text_color="#666").pack(
                         anchor="w", padx=16, pady=(0, 12))

        # Password change
        pw_frame = ctk.CTkFrame(win, fg_color="transparent")
        pw_frame.pack(fill="x", padx=24)

        ctk.CTkLabel(pw_frame, text="Change Password",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
                         anchor="w", pady=(0, 8))

        ctk.CTkLabel(pw_frame, text="Current Password", anchor="w").pack(
            fill="x")
        current_pw = ctk.CTkEntry(pw_frame, show="*", height=36)
        current_pw.pack(fill="x", pady=(2, 8))

        ctk.CTkLabel(pw_frame, text="New Password (min 12 chars)", anchor="w").pack(
            fill="x")
        new_pw = ctk.CTkEntry(pw_frame, show="*", height=36)
        new_pw.pack(fill="x", pady=(2, 8))

        ctk.CTkLabel(pw_frame, text="Confirm New Password", anchor="w").pack(
            fill="x")
        confirm_pw = ctk.CTkEntry(pw_frame, show="*", height=36)
        confirm_pw.pack(fill="x", pady=(2, 14))

        ctk.CTkButton(pw_frame, text="Change Password", height=36,
                      command=lambda: change_password()).pack(fill="x")

        status = ctk.CTkLabel(pw_frame, text="", font=ctk.CTkFont(size=11))
        status.pack(pady=(6, 0))

        def change_password():
            cur = current_pw.get().strip()
            new = new_pw.get().strip()
            confirm = confirm_pw.get().strip()
            if not cur or not new:
                status.configure(text="Both fields are required.", text_color="#ef4444")
                return
            if len(new) < 12:
                status.configure(text="New password must be at least 12 characters.",
                                 text_color="#ef4444")
                return
            if new != confirm:
                status.configure(text="New passwords do not match.", text_color="#ef4444")
                return

            if self._dev:
                status.configure(text="Password changed successfully.",
                                 text_color="#22c55e")
                return

            headers = {"Authorization": f"Bearer {self.app.token}"}
            def run():
                try:
                    resp = requests.put(
                        f"{BASE_URL}/api/auth/password",
                        json={"currentPassword": cur, "newPassword": new},
                        headers=headers, verify=VERIFY_SSL)
                    resp.raise_for_status()
                    self.app.after(0, lambda: status.configure(
                        text="Password changed successfully.",
                        text_color="#22c55e"))
                except requests.exceptions.HTTPError as e:
                    msg = e.response.json().get("error", {}).get("message", str(e))
                    self.app.after(0, lambda m=msg: status.configure(
                        text=m, text_color="#ef4444"))
                except Exception as e:
                    self.app.after(0, lambda m=str(e): status.configure(
                        text=m, text_color="#ef4444"))
            threading.Thread(target=run, daemon=True).start()


    # ── Logout ──

    def _logout(self):
        self.app.token = None
        self.app._show_login()
