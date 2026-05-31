import threading
import customtkinter as ctk

import config
from constants import MIN_PASSWORD_LENGTH
from crypto.keystore import Keystore
from errors import ConflictError, NetworkError, ValidationError
from services.auth_service import AuthService


class RegisterFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color="transparent")
        self.app = app

        inner = ctk.CTkFrame(self, width=400, corner_radius=16)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text="Zebra",
                     font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(30, 2))
        ctk.CTkLabel(inner, text="Create Account",
                     font=ctk.CTkFont(size=13), text_color="#888").pack(pady=(0, 4))
        ctk.CTkLabel(inner, text="Your encryption keys will be generated locally.",
                     font=ctk.CTkFont(size=11), text_color="#666").pack(pady=(0, 24))

        for label, attr, kw in [
            ("Username", "username", {}),
            (f"Password (min {MIN_PASSWORD_LENGTH} chars)", "password", {"show": "*"}),
            ("Confirm Password", "confirm", {"show": "*"}),
        ]:
            ctk.CTkLabel(inner, text=label, anchor="w").pack(fill="x", padx=30)
            e = ctk.CTkEntry(inner, width=340, height=40, **kw)
            e.pack(padx=30, pady=(4, 12))
            setattr(self, attr, e)

        self._register_btn = ctk.CTkButton(inner, text="Register", height=42,
                                           command=self._submit)
        self._register_btn.pack(padx=30, fill="x")

        ctk.CTkButton(inner, text="Back to Login", height=42, fg_color="transparent",
                      border_width=2, command=app._show_login).pack(
                          padx=30, pady=(10, 6), fill="x")

        # Progress section (hidden until registration starts)
        self._progress_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._progress_frame.pack(fill="x", padx=30, pady=(8, 0))
        self._progress_bar = ctk.CTkProgressBar(self._progress_frame, height=6)
        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="", font=ctk.CTkFont(size=11),
            text_color="#888")

        self.status = ctk.CTkLabel(inner, text="", text_color="#ff6b6b")
        self.status.pack(pady=(4, 24))

    def _set_status(self, text, color="#ff6b6b"):
        self.status.configure(text=text, text_color=color)

    def _show_progress(self, text):
        self._progress_bar.pack(fill="x", pady=(4, 4))
        self._progress_label.pack(anchor="w")
        self._progress_label.configure(text=text)

    def _hide_progress(self):
        self._progress_bar.pack_forget()
        self._progress_label.pack_forget()

    def _submit(self):
        user = self.username.get().strip()
        pw = self.password.get().strip()
        confirm = self.confirm.get().strip()

        if not user or not pw:
            self._set_status("Username and password are required.")
            return
        if len(pw) < MIN_PASSWORD_LENGTH:
            self._set_status(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            return
        if pw != confirm:
            self._set_status("Passwords do not match.")
            return

        self._register_btn.configure(state="disabled")
        self._set_status("")

        def run():
            steps = [
                "Deriving authentication credential...",
                "Generating X25519 key pair...",
                "Generating Ed25519 signing key...",
                "Encrypting private keys with local KEK...",
                "Registering with server...",
            ]
            import time
            for i, step in enumerate(steps):
                self.app.after(0, lambda s=step: self._show_progress(s))
                self.app.after(0, lambda v=(i + 1) / len(steps):
                               self._progress_bar.set(v))
                time.sleep(0.4)

            def fail(msg):
                self.app.after(0, lambda: self._set_status(msg))
                self.app.after(0, self._hide_progress)
                self.app.after(0, lambda: self._register_btn.configure(
                    state="normal"))

            try:
                # AuthService registers with the server, then generates the
                # local keystore (X25519 + Ed25519, private keys KEK-encrypted).
                # The keystore is scoped per-account so users on one machine
                # don't share a keypair / plaintext cache / replay counters.
                self.app.after(0, lambda: self._show_progress("Generating keypairs..."))
                auth = AuthService(
                    keystore=Keystore(path=config.keystore_path_for(user)))
                auth.register(user, pw)
                self.app.keystore = auth.keystore

                self.app.after(0, lambda: self._show_progress(
                    "Account created! Redirecting to login..."))
                time.sleep(0.8)
                self.app.after(0, self.app._show_login)

            except NetworkError:
                fail("Cannot connect — is the backend running?")
            except ConflictError:
                fail("That username is already taken.")
            except ValidationError as e:
                fail(str(e) or "Registration was rejected by the server.")
            except Exception as e:
                fail(str(e))

        threading.Thread(target=run, daemon=True).start()
