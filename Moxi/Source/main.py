import customtkinter as ctk
from ui import MoxiApp

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = MoxiApp()
    app.mainloop()
