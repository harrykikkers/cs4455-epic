import urllib3
import customtkinter as ctk

from .login_frame import LoginFrame
from .register_frame import RegisterFrame
from .main_frame import MainFrame

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# CustomTkinter theme (kept here so config.py stays GUI-free).
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Zebra")
        self.geometry("1050x700")
        self.minsize(900, 600)
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
