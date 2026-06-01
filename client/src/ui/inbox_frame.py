"""Conversation sidebar and message thread list.

Extracted from ``main_frame.py``. ``InboxFrame`` renders the left-hand
conversation list (``_rebuild_conv_list``, ``_filter_chats``, ``_make_conv_row``),
opens a conversation's thread (``_open_chat``), and starts a new conversation
(``_new_chat``). It reads the in-memory ``self._conversations`` built by
``MainFrame._populate`` from ``MessageService.inbox`` / ``.sent``.

These methods run on a ``MainFrame`` instance and rely on its shared state
(``self._conversations``, ``self._active_peer``, ``self._conv_list``,
``self._msg_area``, ``self._peer_label``, ``self._key_banner``, ``self._panel``,
``self._search``, ``self._auth`` …) and on ``_make_msg_bubble`` from the message
component.
"""

import threading
import customtkinter as ctk
from tkinter import messagebox

from constants import PREVIEW_MAX_CHARS
from errors import NotFoundError, RateLimitError
from ui.utils import _format_time


class InboxFrame:
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

        fg = ("#1a1a1a", "#1a1a1a") if is_active else self._panel
        border_col = "#ffffff" if is_active else "#333333"

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
            if len(preview_text) > PREVIEW_MAX_CHARS:
                preview_text = preview_text[:PREVIEW_MAX_CHARS] + "..."
            preview = f"You: {preview_text}" if last.get("_mine") else preview_text
            preview_label = ctk.CTkLabel(
                inner, text=preview,
                font=ctk.CTkFont(size=11), text_color="#888", anchor="w")
            preview_label.pack(anchor="w", pady=(2, 0))
            preview_label.bind("<Button-1>",
                               lambda e, p=peer_id: self._open_chat(p))

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

        def run():
            try:
                user = self._auth.api.get_user(username)["data"]
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
            except NotFoundError:
                self.app.after(0, lambda: messagebox.showerror(
                    "Not found", f'No user "{username}" exists.'))
            except RateLimitError:
                self.app.after(0, lambda: messagebox.showerror(
                    "Rate limited", "Too many requests — wait a moment and try again."))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()
