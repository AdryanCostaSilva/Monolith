import customtkinter as ctk

from src.ui.main_window import DataReadinessApp


def main():
    ctk.set_appearance_mode("dark")
    DataReadinessApp().mainloop()


if __name__ == "__main__":
    main()
