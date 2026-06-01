"""Single message view — bubble, details dialog, and per-message actions.

Extracted from ``main_frame.py``. ``MessageFrame`` renders each message
bubble (``_make_msg_bubble`` / ``_build_action_buttons``) and drives the
per-message actions: forward (``_forward_msg``), delete (``_delete_msg``),
download to the C++ encrypted archive (``_download_msg``), the details dialog
with the forwarded-to/revoke list (``_show_msg_detail`` / ``_revoke_access``),
and the blockchain proof (``_view_chain``). These call ``MessageService`` and
``ChainService``; all crypto stays in those layers.

These methods run on a ``MainFrame`` instance and rely on its shared state
(``self._conversations``, ``self._active_peer``, ``self._svc``, ``self._auth``,
``self._chain``, ``self._plaintext_cache``, ``self._msg_area``, ``self.app`` …)
and on ``_open_chat`` / ``_load`` from the inbox/core.
"""

import datetime
import os
import subprocess
import threading
import customtkinter as ctk
from tkinter import messagebox

from constants import NOW_FMT
from errors import ClientError, NetworkError, NotFoundError, RateLimitError
from ui.utils import _format_time, resolve_store_binary


class MessageFrame:
    def _make_msg_bubble(self, m):
        mine = m.get("_mine", False)
        bg = ("#f0f0f0", "#f0f0f0") if mine else ("#1a1a1a", "#1a1a1a")
        text_col = "#000000" if mine else "#ffffff"
        time_col = "#666666" if mine else "#888888"
        side = "e" if mine else "w"

        # Outer wrapper for alignment
        wrapper = ctk.CTkFrame(self._msg_area, fg_color="transparent")
        wrapper.pack(fill="x", pady=4, padx=12)

        bubble = ctk.CTkFrame(wrapper, fg_color=bg, corner_radius=14,
                              border_width=1,
                              border_color=("#cccccc", "#cccccc") if mine
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
            enc_bg = ("#d8d8d8", "#d8d8d8") if mine else ("#111111", "#111111")
            enc_frame = ctk.CTkFrame(bubble, fg_color=enc_bg, corner_radius=8)
            enc_frame.pack(padx=10, pady=(10, 0), fill="x")
            ctk.CTkLabel(enc_frame, text="Encrypted message",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#555555" if mine else "#888888").pack(
                             padx=10, pady=(6, 2), anchor="w")
            ctk.CTkLabel(enc_frame, text="Decryption key required to view",
                         font=ctk.CTkFont(size=10),
                         text_color="#777777" if mine else "#555555").pack(
                             padx=10, pady=(0, 6), anchor="w")

        # Footer: timestamp + persistent actions toggle
        footer = ctk.CTkFrame(bubble, fg_color="transparent")
        footer.pack(fill="x", padx=10, pady=(2, 4))

        ctk.CTkLabel(footer, text=_format_time(m.get("created_at", "")),
                     font=ctk.CTkFont(size=10), text_color=time_col).pack(
                         side="left", padx=(4, 0))

        # Action buttons — opened via the ⋯ toggle, closable by
        # clicking ⋯ again or anywhere on the bubble
        action_btns = ctk.CTkFrame(bubble, fg_color="transparent")

        hover = ("#dddddd", "#dddddd") if mine else ("#333333", "#333333")
        border = "#aaaaaa" if mine else "#3a3a3a"
        btn_kw = dict(height=24, font=ctk.CTkFont(size=11),
                      fg_color="transparent", border_width=1,
                      border_color=border, hover_color=hover)

        self._build_action_buttons(action_btns, m, mine, btn_kw)

        def toggle_actions(event=None):
            if action_btns.winfo_ismapped():
                action_btns.pack_forget()
            else:
                action_btns.pack(fill="x", padx=10, pady=(0, 8))

        actions_btn = ctk.CTkButton(
            footer, text="⋯", width=30, height=20,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="transparent", hover_color=("#333333", "#333333"),
            text_color="#999999", command=toggle_actions)
        actions_btn.pack(side="right", padx=(0, 2))

        # Clicking the bubble body also toggles (closes) the actions
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
            if "_forwarded_to" not in m:
                m["_forwarded_to"] = []
            m["_forwarded_to"].append({
                "username": recipient,
                "user_id": f"user-{recipient}-id",
                "forwarded_at": datetime.datetime.now().strftime(NOW_FMT),
            })
            messagebox.showinfo(
                "Forwarded",
                f"Message forwarded to {recipient}.\n\n"
                f"(In production this will re-encrypt the message\n"
                f"under {recipient}'s public key and submit\n"
                f"a new keccak256 hash on-chain.)")
            return

        orig_id = m.get("originalMessageId") or m.get("messageId")
        plaintext = m.get("plaintext")
        def run():
            if self.app.keystore is None:
                self.app.after(0, lambda: messagebox.showerror(
                    "Cannot forward",
                    "Encryption keys are locked — please log in again."))
                return
            if not plaintext or plaintext.startswith("["):
                self.app.after(0, lambda: messagebox.showerror(
                    "Cannot forward",
                    "Cannot forward — this message has not been decrypted on this device."))
                return
            # catches all the placeholder strings like [sent], [encrypted], [unverified].
            # you can only forward a real decrypted plaintext — not a placeholder.
            try:
                rid = self._auth.api.get_user(recipient)["data"]["userId"]
                _, changed = self._svc.forward(orig_id, rid, plaintext)
                if changed:
                    self.app.after(0, lambda: self._conversations
                                   .get(rid, {}).update({"key_warning": True}))
                self.app.after(0, lambda: messagebox.showinfo(
                    "Forwarded", f"Message forwarded to {recipient}."))
                self.app.after(0, self._load)
            except NotFoundError:
                self.app.after(0, lambda: messagebox.showerror(
                    "Not found", f'No user "{recipient}" exists.'))
            except RateLimitError:
                self.app.after(0, lambda: messagebox.showerror(
                    "Rate limited", "Too many requests — wait a moment and try again."))
            except (ClientError, NetworkError) as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
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

        def run():
            try:
                self._svc.delete(msg_id)
                self.app.after(0, self._load)
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _show_msg_detail(self, m):
        win = ctk.CTkToplevel(self.app)
        win.title("Message Details")
        win.geometry("460x500")
        win.resizable(False, False)
        win.after(100, win.grab_set)

        ctk.CTkLabel(win, text="Message Details",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 12))

        # Message info
        info = ctk.CTkFrame(win, fg_color=("#1e1e1e", "#1e1e1e"), corner_radius=10,
                            border_width=1, border_color="#2a2a2a")
        info.pack(fill="x", padx=20, pady=(0, 12))

        sender = m.get("sender_username") or (self.app.username if m.get("_mine") else m.get("sender_id", "?"))
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

        # Fetch live share list from server
        orig_id = m.get("originalMessageId") or m.get("messageId")
        try:
            resp = self._svc.api.shares(orig_id)
            fwd_list = (resp or {}).get("data", [])
            for f in fwd_list:
                f["username"] = f.get("username", "?")
                f["user_id"]  = f.get("userId", "")
                f["forwarded_at"] = str(f.get("sharedAt", ""))
        except Exception:
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
        def run():
            try:
                self._svc.revoke(msg_id, user_id)
                self.app.after(0, lambda: messagebox.showinfo(
                    "Revoked", f"{username}'s access has been revoked."))
                self.app.after(0, self._load)
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror(
                    "Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _download_msg(self, m):
        # Archive the decrypted message into the C++ encrypted local store.
        # The plaintext never touches argv or disk in the clear: it is piped to
        # the binary on stdin and the binary encrypts it (AES-256-GCM) under a
        # key derived from the keystore KEK and passed only via env.
        plaintext = m.get("plaintext")
        if not plaintext:
            messagebox.showinfo(
                "Download",
                "Cannot download — message has not been decrypted yet.")
            return

        ks = self.app.keystore
        if ks is None:
            messagebox.showerror(
                "Download failed",
                "No keystore is loaded — log in before downloading.")
            return
        try:
            # Derives the archive key; raises RuntimeError if the keystore is
            # locked (no KEK in memory).
            key_hex = ks.archive_key_hex()
        except Exception as e:
            messagebox.showerror(
                "Download failed",
                f"Keystore is locked — cannot derive the archive key.\n{e}")
            return

        binary = resolve_store_binary()
        if binary is None:
            messagebox.showerror(
                "Download failed",
                "The message-store binary was not found.\n\n"
                "Build it first:\n"
                "  cd message-store && cmake -B build && cmake --build build\n\n"
                "Or set MESSAGE_STORE_BIN to its path.")
            return

        archive   = ks.archive_path()
        message_id = str(m.get("messageId", "?"))
        sender     = m.get("sender_username", "?")
        created    = m.get("created_at", "?")

        def run():
            try:
                env = {**os.environ, "MESSAGE_STORE_KEY": key_hex}
                result = subprocess.run(
                    [binary, "add",
                     "--archive", archive,
                     "--id", message_id,
                     "--sender", sender,
                     "--created", created],
                    input=plaintext.encode("utf-8"),
                    env=env, capture_output=True)
                if result.returncode == 0:
                    self.app.after(0, lambda: messagebox.showinfo(
                        "Downloaded",
                        "Message saved to your encrypted local archive."))
                else:
                    err = (result.stderr.decode("utf-8", "replace").strip()
                           or f"message-store exited with code {result.returncode}")
                    self.app.after(0, lambda e=err: messagebox.showerror(
                        "Download failed", e))
            except Exception as e:
                self.app.after(0, lambda e=str(e): messagebox.showerror(
                    "Download failed", e))
        threading.Thread(target=run, daemon=True).start()

    def _view_chain(self, m):
        # Forwards create no chain entry, so a forwarded message's on-chain
        # proof lives under the ORIGINAL message's id.
        msg_id = m.get("originalMessageId") or m.get("messageId", "?")
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

        def run():
            try:
                data = self._chain.proof(msg_id)["data"]
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
