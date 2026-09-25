from pathlib import Path
from tkinter import BooleanVar, filedialog, ttk

import customtkinter as ctk

from src.context import DOCUMENTATION_ITEMS, PROVENANCE_ITEMS, UsageContext
from src.engine import evaluate_dataset
from src.loading import load
from src.profiling import profile
from src.reporting import export_html, export_json, generate_report


LOAD_TAB = "1. Load"
CONTEXT_TAB = "2. Context"
EVALUATE_TAB = "3. Evaluate"
RESULTS_TAB = "4. Results"
NO_TARGET = "No target"


class DataReadinessApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Data Readiness Framework")
        self.geometry("1120x780")
        self.minsize(900, 650)

        self.df = None
        self.info = None
        self.dataset_profile = None
        self.context = None
        self.result = None
        self.column_lookup = {}
        self.important_vars = {}
        self.documentation_vars = {}
        self.provenance_vars = {}

        self._build_interface()

    def _build_interface(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))
        ctk.CTkLabel(
            header,
            text="Data Readiness Framework",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Evaluate whether tabular data is ready for use",
            text_color="gray",
        ).pack(side="left", padx=16)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        for name in (LOAD_TAB, CONTEXT_TAB, EVALUATE_TAB, RESULTS_TAB):
            self.tabs.add(name)

        self._build_load_tab()
        self._build_context_tab()
        self._build_evaluate_tab()
        self._build_results_tab()
        self.tabs.set(LOAD_TAB)

    def _build_load_tab(self):
        tab = self.tabs.tab(LOAD_TAB)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        ctk.CTkLabel(
            top,
            text="Load a dataset",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top,
            text="Choose CSV or XLSX",
            command=self._load_dataset,
            width=180,
        ).pack(side="right")

        self.load_status = ctk.CTkLabel(
            tab, text="No dataset loaded.", text_color="gray", anchor="w"
        )
        self.load_status.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        for column in range(4):
            cards.grid_columnconfigure(column, weight=1)
        self.summary_values = {}
        for column, title in enumerate(("Format", "Rows", "Columns", "% Missing")):
            self.summary_values[title] = self._summary_card(cards, title, column)

        self.profile_preview = ctk.CTkTextbox(tab, font=("Consolas", 12))
        self.profile_preview.grid(
            row=3, column=0, sticky="nsew", padx=14, pady=(10, 12)
        )
        self._set_text(self.profile_preview, "Load a dataset to see its profile.")

        self.load_next_button = ctk.CTkButton(
            tab,
            text="Continue to Context",
            command=lambda: self.tabs.set(CONTEXT_TAB),
            state="disabled",
        )
        self.load_next_button.grid(row=4, column=0, sticky="e", padx=14, pady=(0, 12))

    def _summary_card(self, parent, title, column):
        card = ctk.CTkFrame(parent)
        card.grid(row=0, column=column, sticky="ew", padx=6)
        ctk.CTkLabel(card, text=title, text_color="gray").pack(pady=(10, 0))
        value = ctk.CTkLabel(card, text="-", font=ctk.CTkFont(size=22, weight="bold"))
        value.pack(pady=(0, 10))
        return value

    def _build_context_tab(self):
        tab = self.tabs.tab(CONTEXT_TAB)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(tab)
        form.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        form.grid_columnconfigure(0, weight=3)
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(2, weight=1)

        self.goal_entry = self._form_field(form, "Project goal", 0)
        ctk.CTkLabel(form, text="Task type", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(8, 2)
        )
        self.task_menu = ctk.CTkOptionMenu(
            form, values=["classification", "regression", "other"]
        )
        self.task_menu.set("other")
        self.task_menu.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 10))

        ctk.CTkLabel(form, text="Target column", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=8, pady=(8, 2)
        )
        self.target_menu = ttk.Combobox(
            form,
            values=[NO_TARGET],
            state="readonly",
            height=12,
        )
        self.target_menu.set(NO_TARGET)
        self.target_menu.grid(row=1, column=2, sticky="ew", padx=8, pady=(0, 10))

        checklists = ctk.CTkFrame(tab, fg_color="transparent")
        checklists.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        for column in range(3):
            checklists.grid_columnconfigure(column, weight=1)
        checklists.grid_rowconfigure(0, weight=1)

        self.important_frame = ctk.CTkScrollableFrame(
            checklists, label_text="Important columns", height=220
        )
        self.important_frame.grid(row=0, column=0, sticky="nsew", padx=6)
        self.documentation_frame = ctk.CTkScrollableFrame(
            checklists, label_text="Documentation", height=220
        )
        self.documentation_frame.grid(row=0, column=1, sticky="nsew", padx=6)
        self.provenance_frame = ctk.CTkScrollableFrame(
            checklists, label_text="Provenance", height=220
        )
        self.provenance_frame.grid(row=0, column=2, sticky="nsew", padx=6)
        self._build_checklist(
            self.documentation_frame, DOCUMENTATION_ITEMS, self.documentation_vars
        )
        self._build_checklist(
            self.provenance_frame, PROVENANCE_ITEMS, self.provenance_vars
        )

        notes_frame = ctk.CTkFrame(tab)
        notes_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=8)
        ctk.CTkLabel(notes_frame, text="Notes", anchor="w").pack(
            fill="x", padx=10, pady=(8, 2)
        )
        self.notes_textbox = ctk.CTkTextbox(notes_frame, height=70)
        self.notes_textbox.pack(fill="x", padx=10, pady=(0, 10))

        footer = ctk.CTkFrame(tab, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 12))
        self.context_status = ctk.CTkLabel(
            footer, text="Load a dataset before setting the context.", text_color="gray"
        )
        self.context_status.pack(side="left")
        ctk.CTkButton(
            footer, text="Save and Continue", command=self._save_context
        ).pack(side="right")

    def _form_field(self, parent, title, column):
        ctk.CTkLabel(parent, text=title, anchor="w").grid(
            row=0, column=column, sticky="ew", padx=8, pady=(8, 2)
        )
        entry = ctk.CTkEntry(parent)
        entry.grid(row=1, column=column, sticky="ew", padx=8, pady=(0, 10))
        return entry

    def _build_checklist(self, parent, items, variables):
        for row, item in enumerate(items):
            variable = BooleanVar(value=False)
            variables[item] = variable
            ctk.CTkCheckBox(
                parent,
                text=item.replace("_", " ").capitalize(),
                variable=variable,
            ).grid(row=row, column=0, sticky="w", padx=8, pady=5)

    def _build_evaluate_tab(self):
        tab = self.tabs.tab(EVALUATE_TAB)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        panel = ctk.CTkFrame(tab)
        panel.grid(row=0, column=0, padx=140, pady=100, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(
            panel,
            text="Evaluate Data Readiness",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(45, 10))
        self.evaluation_status = ctk.CTkLabel(
            panel,
            text="Load a dataset and save its usage context first.",
            text_color="gray",
        )
        self.evaluation_status.grid(row=1, column=0, padx=20, pady=10)
        self.evaluate_button = ctk.CTkButton(
            panel,
            text="Evaluate",
            command=self._evaluate,
            state="disabled",
            width=220,
            height=42,
        )
        self.evaluate_button.grid(row=2, column=0, padx=20, pady=(10, 45))

    def _build_results_tab(self):
        tab = self.tabs.tab(RESULTS_TAB)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        summary = ctk.CTkFrame(tab)
        summary.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        self.score_label = ctk.CTkLabel(
            summary, text="-", font=ctk.CTkFont(size=34, weight="bold")
        )
        self.score_label.pack(side="left", padx=(20, 12), pady=14)
        self.classification_label = ctk.CTkLabel(
            summary, text="Run an evaluation to see results.", text_color="gray"
        )
        self.classification_label.pack(side="left", pady=14)
        self.export_button = ctk.CTkButton(
            summary,
            text="Export Report",
            command=self._export_report,
            state="disabled",
        )
        self.export_button.pack(side="right", padx=20, pady=14)

        self.dimension_frame = ctk.CTkScrollableFrame(
            tab, label_text="Dimension scores", height=190
        )
        self.dimension_frame.grid(
            row=1, column=0, sticky="nsew", padx=14, pady=8
        )
        for column in range(3):
            self.dimension_frame.grid_columnconfigure(column, weight=1)

        details = ctk.CTkFrame(tab, fg_color="transparent")
        details.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        details.grid_columnconfigure(0, weight=1)
        details.grid_columnconfigure(1, weight=1)
        details.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(details, text="Problems", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=6
        )
        ctk.CTkLabel(
            details, text="Recommendations", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=1, sticky="w", padx=6)
        self.problems_textbox = ctk.CTkTextbox(details)
        self.problems_textbox.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self.recommendations_textbox = ctk.CTkTextbox(details)
        self.recommendations_textbox.grid(
            row=1, column=1, sticky="nsew", padx=6, pady=4
        )
        self._set_text(self.problems_textbox, "No evaluation yet.")
        self._set_text(self.recommendations_textbox, "No evaluation yet.")

        self.export_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self.export_status.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 8))

    def _load_dataset(self):
        selected = filedialog.askopenfilename(
            filetypes=[
                ("Supported datasets", "*.csv *.CSV *.xlsx *.XLSX"),
                ("CSV files", "*.csv *.CSV"),
                ("Excel files", "*.xlsx *.XLSX"),
            ]
        )
        if not selected:
            return

        try:
            df, info = load(selected)
            dataset_profile = profile(df)
        except Exception as error:
            self.load_status.configure(text=f"Error: {error}", text_color="#ff6b6b")
            return

        self.df = df
        self.info = info
        self.dataset_profile = dataset_profile
        self.context = None
        self.result = None
        self.load_status.configure(
            text=f"Dataset loaded: {Path(selected).name}", text_color="#67d391"
        )
        summary = dataset_profile["dataset"]
        values = {
            "Format": info["format"].upper(),
            "Rows": info["rows"],
            "Columns": info["columns"],
            "% Missing": f"{summary['missing_percentage']:.2f}%",
        }
        for name, value in values.items():
            self.summary_values[name].configure(text=str(value))
        self._set_text(self.profile_preview, self._profile_text())
        self.load_next_button.configure(state="normal")
        self.evaluate_button.configure(state="normal")
        self._reset_context_controls()
        self._reset_results()

    def _profile_text(self):
        lines = ["COLUMN PROFILE", ""]
        for name, values in self.dataset_profile["columns"].items():
            lines.append(
                f"{name}: type={values['type']}, missing={values['missing_percentage']}%, "
                f"unique={values['unique_count']}"
            )
        return "\n".join(lines)

    def _reset_context_controls(self):
        self.goal_entry.delete(0, "end")
        self.task_menu.set("other")
        self.column_lookup = {str(name): name for name in self.df.columns}
        self.target_menu.configure(values=[NO_TARGET, *self.column_lookup])
        self.target_menu.set(NO_TARGET)
        for widget in self.important_frame.winfo_children():
            widget.destroy()
        self.important_vars = {}
        for row, name in enumerate(self.df.columns):
            variable = BooleanVar(value=False)
            self.important_vars[name] = variable
            ctk.CTkCheckBox(
                self.important_frame, text=str(name), variable=variable
            ).grid(row=row, column=0, sticky="w", padx=8, pady=5)
        for variable in (*self.documentation_vars.values(), *self.provenance_vars.values()):
            variable.set(False)
        self.notes_textbox.delete("1.0", "end")
        self.context_status.configure(
            text="Set the usage context, then continue.", text_color="gray"
        )
        self.evaluation_status.configure(
            text=f"Ready to evaluate {self.info['file']} after saving the context.",
            text_color="gray",
        )

    def _save_context(self, navigate=True):
        if self.df is None:
            self.context_status.configure(
                text="Load a dataset first.", text_color="#ff6b6b"
            )
            return False
        goal = self.goal_entry.get().strip()
        if not goal:
            self.context_status.configure(
                text="Enter a project goal.", text_color="#ff6b6b"
            )
            return False

        target_name = self.target_menu.get()
        target = None if target_name == NO_TARGET else self.column_lookup[target_name]
        self.context = UsageContext(
            project_goal=goal,
            task_type=self.task_menu.get(),
            target_column=target,
            important_columns=[
                name for name, variable in self.important_vars.items() if variable.get()
            ],
            notes=self.notes_textbox.get("1.0", "end").strip(),
            documentation={
                name: bool(variable.get())
                for name, variable in self.documentation_vars.items()
            },
            provenance={
                name: bool(variable.get())
                for name, variable in self.provenance_vars.items()
            },
        )
        self.context_status.configure(text="Context saved.", text_color="#67d391")
        self.evaluation_status.configure(
            text=f"{self.info['file']} is ready to evaluate.", text_color="gray"
        )
        if navigate:
            self.tabs.set(EVALUATE_TAB)
        return True

    def _evaluate(self):
        if not self._save_context(navigate=False):
            self.tabs.set(CONTEXT_TAB)
            return
        self.evaluation_status.configure(text="Evaluating...", text_color="gray")
        self.update_idletasks()
        try:
            self.result = evaluate_dataset(self.df, self.context, self.dataset_profile)
        except Exception as error:
            self.evaluation_status.configure(
                text=f"Evaluation failed: {error}", text_color="#ff6b6b"
            )
            return

        self.evaluation_status.configure(text="Evaluation complete.", text_color="#67d391")
        self._show_results()
        self.tabs.set(RESULTS_TAB)

    def _show_results(self):
        colors = {
            "Not ready": "#dc5a5a",
            "Requires preparation": "#e0a93b",
            "Almost ready": "#4ea3d8",
            "Ready": "#4caf75",
        }
        color = colors[self.result["classification"]]
        self.score_label.configure(text=f"{self.result['score']:.2f}", text_color=color)
        self.classification_label.configure(
            text=self.result["classification"], text_color=color
        )
        self.export_button.configure(state="normal")
        self.export_status.configure(text="")

        for widget in self.dimension_frame.winfo_children():
            widget.destroy()
        problems = []
        recommendations = []
        for index, dimension in enumerate(self.result["dimensions"]):
            card = ctk.CTkFrame(self.dimension_frame)
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=6,
                pady=6,
            )
            ctk.CTkLabel(card, text=dimension["dimension"], text_color="gray").pack(
                pady=(8, 0)
            )
            score = dimension["score"]
            text = "N/A" if score is None else f"{score:.2f}"
            ctk.CTkLabel(
                card, text=text, font=ctk.CTkFont(size=20, weight="bold")
            ).pack(pady=2)
            progress = ctk.CTkProgressBar(card, progress_color=color)
            progress.pack(fill="x", padx=12, pady=(2, 10))
            progress.set(0 if score is None else score / 100)
            problems.extend(
                f"[{dimension['dimension']}] {item}"
                for item in dimension["problems"]
            )
            recommendations.extend(
                f"[{dimension['dimension']}] {item}"
                for item in dimension["recommendations"]
            )

        self._set_text(
            self.problems_textbox,
            "\n\n".join(problems) if problems else "No problems found.",
        )
        self._set_text(
            self.recommendations_textbox,
            "\n\n".join(recommendations) if recommendations else "No recommendations.",
        )

    def _reset_results(self):
        self.score_label.configure(text="-", text_color=("black", "white"))
        self.classification_label.configure(
            text="Run an evaluation to see results.", text_color="gray"
        )
        self.export_button.configure(state="disabled")
        self.export_status.configure(text="")
        for widget in self.dimension_frame.winfo_children():
            widget.destroy()
        self._set_text(self.problems_textbox, "No evaluation yet.")
        self._set_text(self.recommendations_textbox, "No evaluation yet.")

    def _export_report(self):
        directory = filedialog.askdirectory(title="Choose report folder")
        if not directory:
            return
        try:
            report = generate_report(
                self.info, self.dataset_profile, self.context, self.result
            )
            base = Path(directory) / f"{Path(self.info['file']).stem}_report"
            json_path = export_json(report, base.with_suffix(".json"))
            html_path = export_html(report, base.with_suffix(".html"))
        except Exception as error:
            self.export_status.configure(
                text=f"Export failed: {error}", text_color="#ff6b6b"
            )
            return
        self.export_status.configure(
            text=f"Saved {json_path.name} and {html_path.name}",
            text_color="#67d391",
        )

    @staticmethod
    def _set_text(textbox, text):
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")
