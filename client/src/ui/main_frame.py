import copy
import datetime
import os
import subprocess
import threading
import customtkinter as ctk
from tkinter import messagebox

from constants import DEV_MODE_TOKEN, MIN_PASSWORD_LENGTH, POLL_INTERVAL_MS, PREVIEW_MAX_CHARS, NOW_FMT
from crypto.messaging import SignatureError, ReplayError
from errors import ClientError, NetworkError, NotFoundError, RateLimitError
from session import Session
from services.auth_service import AuthService
from services.chain_service import ChainService
from services.message_service import MessageService
from ui.utils import _write_cache, _run_store_binary, _format_time, resolve_store_binary
from ui.demo_data import DEMO_CONVERSATIONS


class MainFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color="transparent")
        self.app = app
        # Match the login/register screens: their card is a default CTkFrame,
        # so reuse that same theme color for the chat panels instead of black.
        panel = self._panel = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
        self._conversations = {}
        self._active_peer = None
        self._selected_msg = None
        # Seed the plaintext cache from the KEK-encrypted store so messages read
        # in a previous session display immediately after a restart, instead of
        # being re-decrypted live (which the persistent replay counter rejects).
        self._plaintext_cache = {}
        _ks = getattr(app, "keystore", None)
        if _ks is not None:
            try:
                self._plaintext_cache = _ks.load_message_cache()
            except Exception:
                self._plaintext_cache = {}
        self._dev = app.token == DEV_MODE_TOKEN
        self._alive = True  # set False on logout to stop the poll loop

        _session = Session()
        _session.set(app.token, app.user_id, app.username)
        _ks_handle = getattr(app, "keystore", None)
        self._svc = MessageService(session=_session, keystore=_ks_handle)
        self._auth = AuthService(session=_session, keystore=_ks_handle)
        self._chain = ChainService(session=_session)

        # ── Left sidebar ──
        sidebar = ctk.CTkFrame(self, width=280, corner_radius=0,
                               fg_color=panel)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Sidebar / chat divider — white stripe
        divider = ctk.CTkFrame(self, width=2, fg_color=("#ffffff", "#ffffff"),
                               corner_radius=0)
        divider.pack(side="left", fill="y")

        ctk.CTkLabel(sidebar, text="Zebra",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#ffffff").pack(
                         pady=(18, 2), padx=16, anchor="w")
        ctk.CTkLabel(sidebar, text="Secure Messenger",
                     font=ctk.CTkFont(size=11), text_color="#888888").pack(
                         padx=16, anchor="w")
        ctk.CTkLabel(sidebar, text=f"Logged in as {app.username}",
                     font=ctk.CTkFont(size=12), text_color="#aaaaaa").pack(
                         padx=16, anchor="w", pady=(2, 0))

        ctk.CTkButton(sidebar, text="+ New Chat", height=36,
                      fg_color="#ffffff", hover_color="#e0e0e0",
                      text_color="#000000",
                      command=self._new_chat).pack(padx=14, pady=(16, 4), fill="x")

        # Search / filter
        self._search = ctk.CTkEntry(sidebar, placeholder_text="Search chats...",
                                    height=32)
        self._search.pack(padx=14, pady=(4, 10), fill="x")
        self._search.bind("<KeyRelease>", lambda e: self._filter_chats())

        self._conv_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._conv_list.pack(fill="both", expand=True, padx=4)

        # Bottom sidebar section
        bottom = ctk.CTkFrame(sidebar, fg_color=panel,
                              corner_radius=0)
        bottom.pack(fill="x", side="bottom")

        # Thin top border for bottom section — white stripe
        ctk.CTkFrame(bottom, height=1, fg_color=("#ffffff", "#ffffff"),
                     corner_radius=0).pack(fill="x")

        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(10, 12))
        ctk.CTkButton(btn_row, text="Account", height=30, width=115,
                      fg_color="#1a1a1a", hover_color="#333333",
                      text_color="#ffffff", border_width=1, border_color="#444444",
                      command=self._show_account).pack(
                          side="left", expand=True, padx=(0, 4))
        ctk.CTkButton(btn_row, text="Logout", height=30, width=115,
                      fg_color="#1a1a1a", hover_color="#333333",
                      text_color="#ef4444", border_width=1, border_color="#444444",
                      command=self._logout).pack(
                          side="right", expand=True, padx=(4, 0))

        # ── Right chat panel ──
        right = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        # Header
        self._header = ctk.CTkFrame(right, height=64, corner_radius=0,
                                    fg_color=panel)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)

        self._peer_label = ctk.CTkLabel(
            self._header, text="Select a chat",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ffffff")
        self._peer_label.pack(side="left", padx=18)

        ctk.CTkButton(self._header, text="Refresh", width=70, height=28,
                      fg_color="#1a1a1a", hover_color="#333333",
                      text_color="#ffffff", border_width=1, border_color="#444444",
                      command=self._load).pack(side="right", padx=14, pady=18)

        # Header bottom border — white stripe
        ctk.CTkFrame(right, height=2, fg_color=("#ffffff", "#ffffff"),
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
        self._msg_area = ctk.CTkScrollableFrame(right, fg_color=panel)
        self._msg_area.pack(fill="both", expand=True)

        # Empty state
        self._empty_label = ctk.CTkLabel(
            self._msg_area,
            text="Select a conversation to start messaging",
            text_color="#555555", font=ctk.CTkFont(size=14))
        self._empty_label.pack(expand=True, pady=100)

        # Input bar
        ctk.CTkFrame(right, height=2, fg_color=("#ffffff", "#ffffff"),
                     corner_radius=0).pack(fill="x", side="bottom")
        input_bar = ctk.CTkFrame(right, height=64, corner_radius=0,
                                 fg_color=panel)
        input_bar.pack(fill="x", side="bottom")
        input_bar.pack_propagate(False)

        self._msg_input = ctk.CTkEntry(input_bar,
                                       placeholder_text="Type a message...",
                                       height=40)
        self._msg_input.pack(side="left", fill="x", expand=True,
                             padx=(14, 8), pady=12)
        self._msg_input.bind("<Return>", lambda e: self._send())
        ctk.CTkButton(input_bar, text="Send", width=80, height=40,
                      fg_color="#ffffff", hover_color="#e0e0e0",
                      text_color="#000000",
                      command=self._send).pack(side="right", padx=(0, 14), pady=12)

        self._load()
        self._schedule_poll()

    # ── Data loading ──

    def _load(self):
        if self._dev:
            self._populate_dev()
            return
        def run():
            try:
                inbox = (self._svc.inbox() or {}).get("data", [])
                sent  = (self._svc.sent() or {}).get("data", [])
                self._decrypt_inbox(inbox)
                self._decrypt_sent(sent)
                _write_cache(inbox, sent)
                _run_store_binary()
                if self._alive:
                    self.app.after(0, lambda i=inbox, s=sent: self._alive and self._populate(i, s))
            except NetworkError:
                self.app.after(0, lambda: self._alive and self._show_load_error(
                    "Cannot reach server — is the backend running?"))
            except Exception as e:
                self.app.after(0, lambda m=str(e): self._alive and self._show_load_error(m))
        threading.Thread(target=run, daemon=True).start()

    def _show_load_error(self, msg):
        for w in self._conv_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._conv_list, text=f"Load failed:\n{msg}",
                     text_color="#ef4444", font=ctk.CTkFont(size=11),
                     wraplength=220, justify="center").pack(pady=20)

    def _schedule_poll(self):
        if not self._alive:
            return
        if not self._dev:
            self._load()
        self.app.after(POLL_INTERVAL_MS, self._schedule_poll)

    def _populate_dev(self):
        self._conversations = copy.deepcopy(DEMO_CONVERSATIONS)
        self._rebuild_conv_list()
        if self._active_peer and self._active_peer in self._conversations:
            self._open_chat(self._active_peer)

    def _populate(self, inbox, sent):
        def _norm(m):
            # Backend sends camelCase; normalise to snake_case for the UI.
            for camel, snake in (
                ("senderId", "sender_id"),
                ("recipientId", "recipient_id"),
                ("senderUsername", "sender_username"),
                ("recipientUsername", "recipient_username"),
                ("createdAt", "created_at"),
                ("chainStatus", "chain_status"),
            ):
                if camel in m and snake not in m:
                    m[snake] = m.pop(camel)
            return m

        # Remember active peer state before wiping so we can restore it if the
        # backend doesn't return it yet (e.g. new chat opened, no messages sent).
        prev_active = self._conversations.get(self._active_peer) if self._active_peer else None
        prev_msg_count = len(prev_active["messages"]) if prev_active else 0

        self._conversations = {}
        for m in inbox:
            m["_mine"] = False
            _norm(m)
            # Inbox plaintext was already set by _decrypt_inbox in the worker.
            peer_id = m.get("sender_id", "")
            peer_name = m.get("sender_username") or peer_id
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {
                    "name": peer_name, "messages": [], "key_warning": False}
            self._conversations[peer_id]["messages"].append(m)
        for m in sent:
            m["_mine"] = True
            _norm(m)
            if not m.get("plaintext"):
                msg_id = m.get("messageId")
                cached = self._plaintext_cache.get(msg_id) if msg_id else None
                m["plaintext"] = cached if cached else "[sent]"
            peer_id = m.get("recipient_id", "")
            peer_name = m.get("recipient_username") or peer_id
            if peer_id not in self._conversations:
                self._conversations[peer_id] = {
                    "name": peer_name, "messages": [], "key_warning": False}
            self._conversations[peer_id]["messages"].append(m)
        for data in self._conversations.values():
            data["messages"].sort(key=lambda m: m.get("created_at", ""))
            # Propagate per-message key warnings to the conversation.
            if any(m.get("_key_warning") for m in data["messages"]):
                data["key_warning"] = True

        # Restore active peer if the backend doesn't have them yet
        # (newly opened chat with no messages, or race with a just-sent message).
        if self._active_peer and self._active_peer not in self._conversations and prev_active:
            self._conversations[self._active_peer] = prev_active

        self._rebuild_conv_list()

        if self._active_peer and self._active_peer in self._conversations:
            new_msg_count = len(self._conversations[self._active_peer]["messages"])
            if new_msg_count != prev_msg_count:
                # Only redraw the message area when something actually changed.
                self._open_chat(self._active_peer)

    def _decrypt_inbox(self, inbox):
        """Decrypt received messages in the worker thread (network + crypto).

        Each message dict is mutated in place with ``plaintext`` (and possibly
        ``_key_warning``). Messages are processed per-sender in ASCENDING seqNo
        order: the inbox is sorted by created_at DESC, but the replay check is
        strictly-increasing, so out-of-order application would falsely reject.
        """
        ks = self.app.keystore
        added = False  # whether any new plaintext was decrypted this pass

        by_sender = {}
        for m in inbox:
            sender_id = m.get("senderId") or m.get("sender_id")
            by_sender.setdefault(sender_id, []).append(m)

        for sender_id, msgs in by_sender.items():
            msgs.sort(key=lambda m: int(m.get("seqNo", m.get("seq_no", 0))))
            for m in msgs:
                message_id = m.get("messageId")
                if message_id in self._plaintext_cache:
                    # Already decrypted on a prior poll — reusing the cache also
                    # avoids the replay check rejecting an already-seen message.
                    m["plaintext"] = self._plaintext_cache[message_id]
                    continue
                if not m.get("ciphertext"):
                    continue
                if ks is None:
                    m["plaintext"] = "[encrypted — keys locked]"
                    continue
                try:
                    pinned, key_changed = self._svc.key_svc.fetch_and_pin(sender_id)
                except Exception:
                    m["plaintext"] = "[encrypted — cannot fetch sender key]"
                    continue
                if "x25519" not in pinned or "ed25519" not in pinned:
                    m["plaintext"] = "[encrypted — sender key missing]"
                    continue
                try:
                    pt, _ = self._svc.receive(m, pinned=pinned, changed=key_changed)
                    if key_changed:
                        m["_key_warning"] = True
                    m["plaintext"] = pt
                    self._plaintext_cache[message_id] = pt
                    added = True
                except SignatureError:
                    m["plaintext"] = "[unverified — signature check failed]"
                except ReplayError:
                    # We already accepted this seq from this sender, but the
                    # local plaintext cache is gone (e.g. after a re-login). This
                    # is an inbox re-display, not a wire attack — re-decrypt for
                    # view only (no counter change) and re-heal the cache.
                    try:
                        pt, _ = self._svc.receive(
                            m, pinned=pinned, changed=key_changed,
                            enforce_replay=False)
                        m["plaintext"] = pt
                        self._plaintext_cache[message_id] = pt
                        added = True
                    except Exception:
                        m["plaintext"] = "[encrypted — cannot decrypt]"
                except Exception:
                    m["plaintext"] = "[encrypted — cannot decrypt]"

        # Persist the newly decrypted plaintext (encrypted under the KEK) so it
        # survives a restart without a live re-decrypt the replay check rejects.
        if added and ks is not None:
            try:
                ks.save_message_cache(self._plaintext_cache)
            except Exception:
                pass

    def _decrypt_sent(self, sent):
        """Decrypt our OWN sent messages in the worker thread, for display.

        Sent ciphertext is encrypted to the recipient, but static ECDH is
        symmetric, so we re-derive the key from our X25519 private key and the
        recipient's pinned public key; the signature is ours, verified against
        our own Ed25519 public key. Display-only — never touches the replay
        counter. Cache hits are reused; misses are decrypted and re-cached so
        the plaintext survives the next restart. Anything that can't be
        decrypted (e.g. the recipient rotated keys) is left for ``_populate`` to
        render as ``[sent]``.
        """
        ks = self.app.keystore
        if ks is None:
            return
        added = False

        by_recipient = {}
        for m in sent:
            rid = m.get("recipientId") or m.get("recipient_id")
            by_recipient.setdefault(rid, []).append(m)

        for recipient_id, msgs in by_recipient.items():
            pinned = None  # fetched lazily, once per recipient
            for m in msgs:
                message_id = m.get("messageId")
                if message_id in self._plaintext_cache:
                    m["plaintext"] = self._plaintext_cache[message_id]
                    continue
                if not m.get("ciphertext"):
                    continue
                if pinned is None:
                    try:
                        pinned, _ = self._svc.key_svc.fetch_and_pin(recipient_id)
                    except Exception:
                        break  # no key for this recipient — leave the rest as [sent]
                    if "x25519" not in pinned:
                        break
                try:
                    pt = self._svc.decrypt_own(m, pinned=pinned)
                    m["plaintext"] = pt
                    if message_id:
                        self._plaintext_cache[message_id] = pt
                        added = True
                except Exception:
                    pass  # _populate falls back to [sent]

        if added:
            try:
                ks.save_message_cache(self._plaintext_cache)
            except Exception:
                pass

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
            now = datetime.datetime.now().strftime(NOW_FMT)
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

        # Capture peer info on the main thread before handing off to worker.
        peer_id = self._active_peer
        peer_name = self._conversations[peer_id]["name"]

        def run():
            if self.app.keystore is None:
                self.app.after(0, lambda: messagebox.showerror(
                    "Cannot send",
                    "Encryption keys are locked — please log in again."))
                return
            try:
                resp_data, changed = self._svc.send(peer_id, text)
                if changed:
                    self.app.after(0, lambda: self._conversations
                                   .get(peer_id, {}).update({"key_warning": True}))
                msg_id = (resp_data or {}).get("data", {}).get("messageId")
                now = datetime.datetime.now().strftime(NOW_FMT)
                msg = {
                    "messageId": msg_id,
                    "sender_id": self.app.user_id,
                    "sender_username": self.app.username,
                    "recipient_id": peer_id,
                    "recipient_username": peer_name,
                    "_mine": True,
                    "plaintext": text,
                    "created_at": now,
                    "chain_status": "pending",
                }
                if msg_id:
                    self._plaintext_cache[msg_id] = text
                    try:
                        self.app.keystore.save_message_cache(self._plaintext_cache)
                    except Exception:
                        pass
                self.app.after(0, lambda: self._on_send_success(msg))
            except (ClientError, NetworkError) as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Send failed", m))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror("Error", m))
        threading.Thread(target=run, daemon=True).start()

    def _on_send_success(self, msg):
        peer_id = msg["recipient_id"]
        if peer_id not in self._conversations:
            self._conversations[peer_id] = {
                "name": msg["recipient_username"], "messages": [], "key_warning": False}
        self._conversations[peer_id]["messages"].append(msg)
        self._open_chat(peer_id)

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

    # ── Key warning ──

    def _show_key_warning_details(self):
        peer = self._conversations.get(self._active_peer, {}).get("name", "?")
        win = ctk.CTkToplevel(self.app)
        win.title("Key Change Detected")
        win.geometry("460x420")
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
                     f"your last interaction.",
                     font=ctk.CTkFont(size=12), justify="left",
                     wraplength=410).pack(padx=14, pady=(12, 8), anchor="w")

        # TOFU verdict — filled in by reconcile() in a worker thread below.
        verdict = ctk.CTkLabel(
            info, text="Checking this contact's signed key history…",
            font=ctk.CTkFont(size=12), text_color="#888",
            justify="left", wraplength=410)
        verdict.pack(padx=14, pady=(0, 12), anchor="w")

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        peer_id = self._active_peer

        def _clear_warning():
            if peer_id and peer_id in self._conversations:
                self._conversations[peer_id]["key_warning"] = False
                for m in self._conversations[peer_id]["messages"]:
                    m.pop("_key_warning", None)
            self._key_banner.pack_forget()
            self._rebuild_conv_list()

        def accept():
            win.destroy()
            ks = self.app.keystore
            if ks is None or not peer_id:
                # No keystore to re-pin into; just clear the flag as before.
                _clear_warning()
                return
            def run():
                try:
                    data = self._svc.key_svc.api.get(peer_id).get("data", [])
                    for kt in ("x25519", "ed25519"):
                        pub = next((k["publicKey"] for k in data
                                    if k["keyType"] == kt), None)
                        if pub is not None:
                            # Overwrite the pin: the user has accepted the new key.
                            ks.pin_peer_key(peer_id, kt, pub)
                    self.app.after(0, _clear_warning)
                except Exception as e:
                    self.app.after(0, lambda m=str(e): messagebox.showerror(
                        "Error", m))
            threading.Thread(target=run, daemon=True).start()

        accept_btn = ctk.CTkButton(btn_row, text="Accept New Key", height=36,
                                   width=140, fg_color="#166534",
                                   hover_color="#14532d", command=accept)
        accept_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="View History", height=36, width=120,
                      fg_color="#1e1e1e", hover_color="#2a2a2a",
                      command=lambda: self._view_key_history(peer_id, peer)
                      ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Reject", height=36, width=90,
                      fg_color="#991b1b", hover_color="#7f1d1d",
                      command=win.destroy).pack(side="right")

        # TOFU reconciliation: for each key type, KeyService.reconcile compares
        # the server's current key to our local pin and, on a mismatch, checks
        # the append-only key history. A change recorded in history is a
        # legitimate rotation; one that is absent is a possible substitution
        # attack. Network-bound, so it runs off the UI thread.
        def _reconcile():
            if self._dev or not peer_id:
                self.app.after(0, lambda: verdict.configure(
                    text="Key history is unavailable in demo mode.",
                    text_color="#888"))
                return
            try:
                legit = all(self._svc.key_svc.reconcile(peer_id, kt)
                            for kt in ("x25519", "ed25519"))
            except Exception as e:
                self.app.after(0, lambda m=str(e): verdict.configure(
                    text=f"Could not verify against the key history: {m}",
                    text_color="#fbbf24"))
                return
            if legit:
                self.app.after(0, lambda: verdict.configure(
                    text="✓ Verified rotation — the previous key is recorded in "
                         "this contact's signed key history, consistent with a "
                         "normal key change. Accepting is reasonable.",
                    text_color="#22c55e"))
            else:
                def show_attack():
                    verdict.configure(
                        text="⚠ The new key is NOT backed by this contact's key "
                             "history — this may be a key-substitution attack. "
                             "Do not accept unless you have verified their "
                             "identity through a separate channel.",
                        text_color="#ef4444")
                    accept_btn.configure(fg_color="#7f1d1d",
                                         hover_color="#991b1b")
                self.app.after(0, show_attack)
        threading.Thread(target=_reconcile, daemon=True).start()

    def _view_key_history(self, peer_id, peer_name):
        """Fetch and display the peer's append-only key rotation history.

        Pulls each key type's archived versions from
        ``GET /api/keys/:userId/history/:keyType`` (via ``KeyService.api``).
        The list holds prior (rotated-away) keys, oldest first; an empty list
        means the peer's current key is their first and only one.
        """
        if self._dev or not peer_id:
            messagebox.showinfo(
                "Key History", "Key history is unavailable in demo mode.")
            return

        def run():
            try:
                sections = []
                for kt in ("x25519", "ed25519"):
                    entries = self._svc.key_svc.api.history(
                        peer_id, kt).get("data", [])
                    if not entries:
                        sections.append(
                            f"{kt}: no prior keys — current key is the first.")
                        continue
                    lines = [f"{kt}: {len(entries)} prior key(s)"]
                    for e in entries:
                        pub = e.get("publicKey", "") or ""
                        fp = (pub[:16] + "…") if len(pub) > 16 else pub
                        rotated = e.get("rotatedAt") or "—"
                        lines.append(
                            f"  v{e.get('version', '?')}  {fp}  (rotated: {rotated})")
                    sections.append("\n".join(lines))
                text = f"Key history for {peer_name}:\n\n" + "\n\n".join(sections)
                self.app.after(0, lambda t=text: messagebox.showinfo(
                    "Key History", t))
            except Exception as e:
                self.app.after(0, lambda m=str(e): messagebox.showerror(
                    "Error", m))
        threading.Thread(target=run, daemon=True).start()

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
            if len(new) < MIN_PASSWORD_LENGTH:
                status.configure(text=f"New password must be at least {MIN_PASSWORD_LENGTH} characters.",
                                 text_color="#ef4444")
                return
            if new != confirm:
                status.configure(text="New passwords do not match.", text_color="#ef4444")
                return

            if self._dev:
                status.configure(text="Password changed successfully.",
                                 text_color="#22c55e")
                return

            # Fail closed: re-wrapping the keystore needs an unlocked keystore,
            # and changing the password without it would lock the user out of
            # their own private keys.
            ks = self.app.keystore
            if ks is None or not ks.exists():
                status.configure(
                    text="Encryption keys unavailable — cannot change password.",
                    text_color="#ef4444")
                return

            # AuthService sends the Argon2id auth-hash (derived from the
            # cleartext via the session username), NOT the cleartext password.
            # The cleartext is still needed for the local keystore re-wrap (KEK
            # derivation) below, so keep both around.
            def run():
                try:
                    # Server step only — keystore re-wrap is handled separately
                    # so its failure shows a distinct message.
                    self._auth.change_password(cur, new)
                except (ClientError, NetworkError) as e:
                    self.app.after(0, lambda m=str(e): status.configure(
                        text=m, text_color="#ef4444"))
                    return
                except Exception as e:
                    self.app.after(0, lambda m=str(e): status.configure(
                        text=m, text_color="#ef4444"))
                    return

                # Server is authoritative and already succeeded; now re-wrap the
                # local keystore under the new password so private keys stay
                # accessible on next unlock.
                try:
                    ks.change_password(cur, new)
                except Exception as e:
                    self.app.after(0, lambda m=str(e): status.configure(
                        text="Password changed on server but local key "
                             f"re-encryption failed — {m}", text_color="#ef4444"))
                    return

                # The change invalidated the current JWT server-side, so the
                # session is dead — force a re-login with the new password.
                def done():
                    # Stop the 10s poll loop *before* the modal below: the JWT
                    # is now invalid, and messagebox runs a nested event loop,
                    # so otherwise every poll while the dialog is open would hit
                    # the backend with a dead token (auth.token.invalidated).
                    self._alive = False
                    messagebox.showinfo(
                        "Password Changed",
                        "Password changed — please log in again "
                        "with your new password.")
                    win.destroy()
                    self._logout()
                self.app.after(0, done)
            threading.Thread(target=run, daemon=True).start()


    # ── Logout ──

    def _logout(self):
        self._alive = False
        self.app.token = None
        self.app.user_id = None
        self.app.username = None
        self.app._show_login()
