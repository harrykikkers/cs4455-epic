import customtkinter as ctk

BASE_URL   = "http://localhost:3000"
VERIFY_SSL = "localhost" not in BASE_URL and "127.0.0.1" not in BASE_URL

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
