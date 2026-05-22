import urllib3
import customtkinter as ctk

import config  # noqa: F401 — applies ctk theme on import
from views.login import LoginFrame
from views.register import RegisterFrame
from views.main import MainFrame

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Zebra")
        self.geometry("900x600")
        self.resizable(False, False)
        self.token    = None
        self.user_id  = None
        self.username = None
        self._show_login()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _show_login(self):
        self._clear()
        LoginFrame(self).pack(fill="both", expand=True)

    def _show_register(self):
        self._clear()
        RegisterFrame(self).pack(fill="both", expand=True)

    def _show_main(self):
        self._clear()
        MainFrame(self).pack(fill="both", expand=True)


if __name__ == "__main__":
    App().mainloop()
