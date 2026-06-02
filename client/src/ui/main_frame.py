import copy
import threading
import customtkinter as ctk
from tkinter import messagebox

from constants import DEV_MODE_TOKEN, MIN_PASSWORD_LENGTH, POLL_INTERVAL_MS
from crypto.messaging import SignatureError, ReplayError
from errors import ClientError, NetworkError
from session import Session
from services.auth_service import AuthService
from services.chain_service import ChainService
from services.message_service import MessageService
from ui.demo_data import DEMO_CONVERSATIONS
from ui.compose_frame import ComposeFrame
from ui.inbox_frame import InboxFrame
from ui.message_frame import MessageFrame, rekey_archive
from ui.widgets import Widgets


class MainFrame(InboxFrame, MessageFrame, ComposeFrame, Widgets,
                ctk.CTkFrame):
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
        ctk.CTkLabel(
            self._key_banner,
            text="  Warning: This contact's encryption key has changed. Verify their identity.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24", anchor="w").pack(side="left", fill="x", expand=True, padx=12)
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

        # Keep the active chat open even when the backend returns nothing for it
        # (newly opened chat with no messages yet, or a race with a just-sent
        # message). Restore only the conversation *shell* — never the stale
        # message list. Resurrecting prev_active wholesale would bring back
        # messages the server no longer returns (e.g. ones just deleted, or a
        # forward whose original was deleted), so a manual refresh would never
        # clear them. A just-sent message that races the poll lives in the
        # plaintext cache and reappears on the next pass.
        if self._active_peer and self._active_peer not in self._conversations and prev_active:
            self._conversations[self._active_peer] = {
                "name": prev_active.get("name", self._active_peer),
                "messages": [],
                "key_warning": prev_active.get("key_warning", False),
            }

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

                # Capture the archive key under the OLD KEK before re-wrapping —
                # the archive key is HKDF(KEK), so it changes with the password
                # and the existing .archive must be re-keyed (below) or it would
                # fail GCM auth on the next Download.
                try:
                    old_arch_key = ks.archive_key_hex()
                except Exception:
                    old_arch_key = None

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

                # Re-key the C++ local archive under the new KEK so previously
                # downloaded messages stay readable. Non-fatal: login still
                # proceeds, but warn so the user knows a missing binary / failure
                # leaves old downloads unreadable until re-downloaded.
                try:
                    new_arch_key = ks.archive_key_hex()
                    rekey_archive(ks.archive_path(), old_arch_key, new_arch_key)
                except Exception as e:
                    self.app.after(0, lambda m=str(e): status.configure(
                        text="Password changed, but the local message archive "
                             f"could not be re-keyed — {m}", text_color="#f59e0b"))

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
