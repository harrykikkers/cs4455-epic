import threading
import requests
import customtkinter as ctk

from config import BASE_URL, VERIFY_SSL


class RegisterFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color="transparent")
        self.app = app

        inner = ctk.CTkFrame(self, width=380, corner_radius=16)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner, text="Create Account",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(30, 20))
        for label, attr, kw in [
            ("Username", "username", {}),
            ("Password (min 12 chars)", "password", {"show": "*"}),
        ]:
            ctk.CTkLabel(inner, text=label, anchor="w").pack(fill="x", padx=30)
            e = ctk.CTkEntry(inner, width=320, height=38, **kw)
            e.pack(padx=30, pady=(4, 12))
            setattr(self, attr, e)
        ctk.CTkButton(inner, text="Register", height=40, command=self._submit).pack(padx=30, fill="x")
        ctk.CTkButton(inner, text="Back to Login", height=40, fg_color="transparent",
                      border_width=2, command=app._show_login).pack(padx=30, pady=(10, 6), fill="x")
        self.status = ctk.CTkLabel(inner, text="", text_color="#ff6b6b")
        self.status.pack(pady=(0, 20))

    def _set_status(self, text, color="#ff6b6b"):
        self.status.configure(text=text, text_color=color)

    def _submit(self):
        self._set_status("Registering...", "gray")
        def run():
            try:
                resp = requests.post(f"{BASE_URL}/api/auth/register", json={
                    "username": self.username.get().strip(),
                    "password": self.password.get().strip(),
                }, verify=VERIFY_SSL)
                resp.raise_for_status()
                self.app.after(0, self.app._show_login)
            except requests.exceptions.ConnectionError:
                self.app.after(0, lambda: self._set_status("Cannot connect — is the backend running?"))
            except requests.exceptions.HTTPError as e:
                msg = e.response.json().get("error", {}).get("message", str(e))
                self.app.after(0, lambda m=msg: self._set_status(m))
            except Exception as e:
                self.app.after(0, lambda m=str(e): self._set_status(m))
        threading.Thread(target=run, daemon=True).start()
