import threading
import requests
import customtkinter as ctk

from config import BASE_URL, VERIFY_SSL


class LoginFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color="transparent")
        self.app = app

        inner = ctk.CTkFrame(self, width=380, corner_radius=16)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text="Zebra Messenger",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(30, 20))
        ctk.CTkLabel(inner, text="Username", anchor="w").pack(fill="x", padx=30)
        self.username = ctk.CTkEntry(inner, width=320, height=38)
        self.username.pack(padx=30, pady=(4, 12))
        self.username.focus()
        ctk.CTkLabel(inner, text="Password", anchor="w").pack(fill="x", padx=30)
        self.password = ctk.CTkEntry(inner, width=320, height=38, show="*")
        self.password.pack(padx=30, pady=(4, 20))
        self.password.bind("<Return>", lambda e: self._login())
        ctk.CTkButton(inner, text="Login", height=40, command=self._login).pack(padx=30, fill="x")
        ctk.CTkButton(inner, text="Register", height=40, fg_color="transparent",
                      border_width=2, command=app._show_register).pack(padx=30, pady=(10, 6), fill="x")
        self.status = ctk.CTkLabel(inner, text="", text_color="#ff6b6b")
        self.status.pack(pady=(0, 20))

    def _login(self):
        def run():
            try:
                resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                    "username": self.username.get().strip(),
                    "password": self.password.get().strip(),
                }, verify=VERIFY_SSL)
                resp.raise_for_status()
                data = resp.json()["data"]
                self.app.token    = data["token"]
                self.app.user_id  = data["user"]["userId"]
                self.app.username = data["user"]["username"]
                self.app.after(0, self.app._show_main)
            except requests.exceptions.ConnectionError:
                self.app.after(0, lambda: self.status.configure(
                    text="Cannot connect — is the backend running?"))
            except Exception:
                self.app.after(0, lambda: self.status.configure(
                    text="Invalid username or password."))
        threading.Thread(target=run, daemon=True).start()
