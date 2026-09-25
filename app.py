# TODO: split this file into the modules defined by the PBL 4 architecture:
#   - src/loading/loader.py
#   - src/profiling/profiler.py
#   - src/evaluation/*.py
#   - src/aggregation/aggregator.py
#   - src/reporting/report_generator.py
#   - src/ui/main_window.py

import customtkinter as ctk
from tkinter import filedialog
import pandas as pd

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class DataReadinessApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Data Readiness Framework")
        self.geometry("900x650")
        self.minsize(700, 500)

        self.df = None

        self._build_interface()

    def _build_interface(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header,
            text="Data Readiness Framework",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(side="left")

        self.btn_upload = ctk.CTkButton(
            header,
            text="📂 Load Dataset",
            command=self.load_dataset,
            width=180
        )
        self.btn_upload.pack(side="right")

        self.label_status = ctk.CTkLabel(
            self,
            text="No dataset loaded.",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        self.label_status.pack(anchor="w", padx=20, pady=(0, 10))

        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.card_rows = self._create_card(cards_frame, "Rows", "-")
        self.card_columns = self._create_card(cards_frame, "Columns", "-")
        self.card_missing = self._create_card(cards_frame, "% Missing", "-")

        self.result_textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=13)
        )
        self.result_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.result_textbox.insert(
            "1.0",
            "Load a dataset (.csv or .xlsx) to view its basic profile."
        )
        self.result_textbox.configure(state="disabled")

    def _create_card(self, parent, title, initial_value):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(side="left", expand=True, fill="x", padx=5)

        title_label = ctk.CTkLabel(
            card, text=title, font=ctk.CTkFont(size=12), text_color="gray"
        )
        title_label.pack(pady=(10, 0))

        value_label = ctk.CTkLabel(
            card, text=initial_value, font=ctk.CTkFont(size=20, weight="bold")
        )
        value_label.pack(pady=(0, 10))

        card.value_label = value_label
        return card

    def load_dataset(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx")]
        )
        if not path:
            return

        try:
            if path.endswith(".csv"):
                self.df = pd.read_csv(path)
            else:
                self.df = pd.read_excel(path)
        except Exception as error:
            self._show_error(f"Error loading the file: {error}")
            return

        file_name = path.split("/")[-1]
        self.label_status.configure(
            text=f"Dataset loaded: {file_name}",
            text_color="lightgreen"
        )

        self._update_cards()
        self._show_profile()

    def _update_cards(self):
        rows, columns = self.df.shape
        total_cells = rows * columns
        missing_percentage = (self.df.isnull().sum().sum() / total_cells) * 100

        self.card_rows.value_label.configure(text=str(rows))
        self.card_columns.value_label.configure(text=str(columns))
        self.card_missing.value_label.configure(text=f"{missing_percentage:.1f}%")

    def _show_profile(self):
        text = "=== COLUMN TYPES ===\n"
        text += str(self.df.dtypes) + "\n\n"

        text += "=== MISSING VALUES BY COLUMN ===\n"
        text += str(self.df.isnull().sum()) + "\n\n"

        text += "=== UNIQUE VALUES BY COLUMN ===\n"
        text += str(self.df.nunique()) + "\n\n"

        text += "=== DESCRIPTIVE STATISTICS ===\n"
        text += str(self.df.describe())

        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", text)
        self.result_textbox.configure(state="disabled")

    def _show_error(self, message):
        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", message)
        self.result_textbox.configure(state="disabled")


if __name__ == "__main__":
    app = DataReadinessApp()
    app.mainloop()
