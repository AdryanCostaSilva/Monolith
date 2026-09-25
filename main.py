import customtkinter as ctk

from src.ui.main_window import DataReadinessApp


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    DataReadinessApp().mainloop()


if __name__ == "__main__":
    main()
