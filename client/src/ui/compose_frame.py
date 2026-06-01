"""Compose a new message — the chat input bar.

Extracted from ``main_frame.py``. ``ComposeFrame`` provides the send path:
``_send`` runs ``MessageService.send`` (TOFU → static ECDH + HKDF →
AES-256-GCM → Ed25519 → keccak256) on a worker thread and ``_on_send_success``
appends the sent message to the active conversation. All crypto stays in the
service/crypto layers; this component only orchestrates the UI and threading.

These methods run on a ``MainFrame`` instance and rely on its shared state
(``self._conversations``, ``self._active_peer``, ``self._svc``,
``self._plaintext_cache``, ``self._msg_input``, ``self.app`` …) and on
``_open_chat`` from the inbox component.
"""

import datetime
import os
import threading
from tkinter import messagebox

from constants import NOW_FMT
from errors import ClientError, NetworkError


class ComposeFrame:
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
