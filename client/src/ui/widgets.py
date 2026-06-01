"""Shared UI components — the key-change warning banner dialogs.

Extracted from ``main_frame.py``. ``Widgets`` powers the TOFU
key-change banner: ``_show_key_warning_details`` opens the dialog and runs
``KeyService.reconcile`` against the server's append-only key history in a
worker thread (legitimate rotation vs possible substitution attack), and
``_view_key_history`` lists a peer's prior keys.

These methods run on a ``MainFrame`` instance and rely on its shared state
(``self._conversations``, ``self._active_peer``, ``self._svc``,
``self._key_banner``, ``self.app`` …) and on ``_rebuild_conv_list`` from the
inbox component.
"""

import threading
import customtkinter as ctk
from tkinter import messagebox


class Widgets:
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
