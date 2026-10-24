from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import BooleanVar, filedialog, ttk

import customtkinter as ctk

from src.aggregation import aggregate
from src.config import DIMENSION_HELP, DIMENSION_WEIGHTS
from src.context import DOCUMENTATION_ITEMS, PROVENANCE_ITEMS, UsageContext
from src.engine import evaluate_dataset
from src.evaluation import evaluate_documentation, evaluate_provenance
from src.loading import load
from src.metadata import METADATA_ATTR, read_metadata
from src.profiling import profile
from src.reporting import export_html, export_json, generate_report
from src.ui.dimension_card import MUTED_TEXT, DimensionCard


LOAD_TAB = "1. Load"
CONTEXT_TAB = "2. Context"
EVALUATE_TAB = "3. Evaluate"
RESULTS_TAB = "4. Results"
NO_TARGET = "No target"
WEIGHT_HELP = (
    "Defaults informed by our studies. Adjust relative importance; "
    "0 leaves a dimension out of the overall score."
)


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
        self.evidence_labels = {}
        self._busy = False
        self.dimension_weights = None
        self.weight_task_type = None
        self.weights_expanded = False
        self.dimension_cards = {}

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
        self.load_button = ctk.CTkButton(
            top,
            text="Choose CSV, XLSX or Parquet",
            command=self._load_dataset,
            width=230,
        )
        self.load_button.pack(side="right")

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
        self.target_menu.bind("<<ComboboxSelected>>", self._context_evidence_changed)

        metadata_controls = ctk.CTkFrame(tab, fg_color="transparent")
        metadata_controls.grid(row=1, column=0, sticky="ew", padx=14)
        metadata_controls.grid_columnconfigure(0, weight=1)
        self.metadata_status = ctk.CTkLabel(
            metadata_controls, text="No metadata selected. Checked items take priority over JSON.",
            anchor="w", justify="left", wraplength=550, text_color=MUTED_TEXT,
        )
        self.metadata_status.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.metadata_button = ctk.CTkButton(
            metadata_controls, text="Choose metadata JSON", command=self._load_metadata,
            state="disabled", width=165,
        )
        self.metadata_button.grid(row=0, column=1, padx=4)
        self.remove_metadata_button = ctk.CTkButton(
            metadata_controls, text="Remove", command=self._remove_metadata,
            state="disabled", width=80,
        )
        self.remove_metadata_button.grid(row=0, column=2, padx=4)

        checklists = ctk.CTkFrame(tab, fg_color="transparent")
        checklists.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        for column in range(3):
            checklists.grid_columnconfigure(column, weight=1)
        checklists.grid_rowconfigure(1, weight=1)

        captions = {
            1: DIMENSION_HELP["Documentation"],
            2: DIMENSION_HELP["Provenance"],
        }
        for column, text in captions.items():
            caption = ctk.CTkLabel(
                checklists,
                text=text,
                text_color=MUTED_TEXT,
                font=ctk.CTkFont(size=11),
                justify="left",
                anchor="w",
                wraplength=300,
            )
            caption.grid(row=0, column=column, sticky="ew", padx=6, pady=(0, 6))
            if column == 1:
                self.documentation_caption = caption
            else:
                self.provenance_caption = caption

        self.important_frame = ctk.CTkScrollableFrame(
            checklists, label_text="Important columns", height=220
        )
        self.important_frame.grid(row=1, column=0, sticky="nsew", padx=6)
        self.documentation_frame = ctk.CTkScrollableFrame(
            checklists, label_text="Documentation · self-reported claims", height=220
        )
        self.documentation_frame.grid(row=1, column=1, sticky="nsew", padx=6)
        self.provenance_frame = ctk.CTkScrollableFrame(
            checklists, label_text="Provenance · self-reported claims", height=220
        )
        self.provenance_frame.grid(row=1, column=2, sticky="nsew", padx=6)
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
        parent.grid_columnconfigure(0, weight=1)
        for row, item in enumerate(items):
            variable = BooleanVar(value=False)
            variables[item] = variable
            ctk.CTkCheckBox(
                parent,
                text=item.replace("_", " ").capitalize(),
                variable=variable,
                command=self._context_evidence_changed,
            ).grid(row=row * 2, column=0, sticky="w", padx=8, pady=(5, 0))
            label = ctk.CTkLabel(
                parent, text="Evidence missing · 0%", anchor="w", justify="left",
                font=ctk.CTkFont(size=11), text_color=MUTED_TEXT, wraplength=250,
            )
            label.grid(row=row * 2 + 1, column=0, sticky="ew", padx=8, pady=(0, 5))
            self.evidence_labels[item] = label

    def _refresh_metadata_evidence(self, context):
        for evaluate in (evaluate_documentation, evaluate_provenance):
            dimension = evaluate(context, self.df)
            for item in (*dimension["indicators"], *dimension["excluded_indicators"]):
                text = (
                    "Not applicable" if item["status"] == "not_applicable" else
                    f"{item['status'].replace('_', ' ').capitalize()} · {item['value']:g}%"
                )
                self.evidence_labels[item["item"]].configure(text=text)

    def _context_evidence_changed(self, _event=None):
        if self._busy or self.df is None:
            return
        self._reset_results()
        self._refresh_metadata_evidence(self._context_from_controls())

    def _refresh_metadata_controls(self):
        enabled = self.df is not None and not self._busy
        self.metadata_button.configure(state="normal" if enabled else "disabled")
        bundle = self.df.attrs.get(METADATA_ATTR, {}) if self.df is not None else {}
        self.remove_metadata_button.configure(
            state="normal" if enabled and bundle.get("source") else "disabled"
        )

    def _refresh_metadata_status(self):
        bundle = self.df.attrs.get(METADATA_ATTR, {}) if self.df is not None else {}
        source = bundle.get("source")
        message = f"Metadata: {source}." if source else "No metadata selected."
        warnings = bundle.get("warnings", [])
        self.metadata_status.configure(
            text=message + " Checked items take priority; unchecked items use JSON."
            + ("\n" + "\n".join(warnings) if warnings else "")
        )
        self._refresh_metadata_controls()

    def _load_metadata(self):
        if self._busy or self.df is None:
            return
        selected = filedialog.askopenfilename(
            title="Choose dataset metadata", filetypes=[("JSON metadata", "*.json *.JSON")]
        )
        if not selected:
            return
        dataset_sha256 = self.info.get("sha256")
        self._run_background(
            lambda progress: read_metadata(selected, dataset_sha256=dataset_sha256),
            self._metadata_loaded,
            lambda error: self.metadata_status.configure(text=f"Metadata error: {error}"),
        )

    def _metadata_loaded(self, evidence):
        self.df.attrs[METADATA_ATTR] = evidence
        self.info["metadata_file"] = evidence["source"]
        self.info["metadata_warnings"] = list(evidence["warnings"])
        self._reset_results()
        self._refresh_metadata_status()
        self._refresh_metadata_evidence(self._context_from_controls())
        self.evaluation_status.configure(text="Metadata changed. Run the evaluation again.", text_color="gray")

    def _remove_metadata(self):
        if self._busy or self.df is None:
            return
        self._metadata_loaded(read_metadata(None, dataset_sha256=self.info.get("sha256")))

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
        outer = self.tabs.tab(RESULTS_TAB)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=1)
        self.results_scroll = ctk.CTkScrollableFrame(
            outer, fg_color="transparent", corner_radius=0
        )
        self.results_scroll.grid(row=0, column=0, sticky="nsew")
        tab = self.results_scroll
        tab.grid_columnconfigure(0, weight=1)

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

        weights_header = ctk.CTkFrame(tab, fg_color=("#F7F9FC", "#2D3237"))
        weights_header.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        weights_header.grid_columnconfigure(1, weight=1)
        self.weights_title = ctk.CTkLabel(
            weights_header,
            text="Dimension weights",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.weights_title.grid(row=0, column=0, sticky="w", padx=(16, 0), pady=10)
        self.weight_source_label = ctk.CTkLabel(
            weights_header,
            text="Choose how much each dimension counts in the overall score.",
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.weight_source_label.grid(row=0, column=1, sticky="w", padx=12)
        self.weight_toggle = ctk.CTkButton(
            weights_header,
            text="Adjust weights",
            command=self._toggle_weights,
            width=130,
            height=32,
            state="disabled",
        )
        self.weight_toggle.grid(row=0, column=2, sticky="e", padx=(0, 8))
        self.reset_weights_button = ctk.CTkButton(
            weights_header,
            text="Reset to defaults",
            command=self._reset_weights,
            fg_color="transparent",
            hover_color=("#E5E9ED", "#34383E"),
            text_color=("#51697D", "#B1C1CE"),
            border_width=1,
            border_color=("#D3DAE1", "#494F57"),
            width=126,
            height=30,
            state="disabled",
        )
        self.reset_weights_button.grid(row=0, column=3, sticky="e", padx=(0, 12))
        self.reset_weights_button.grid_remove()
        self.weight_help = ctk.CTkLabel(
            weights_header,
            text=WEIGHT_HELP,
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=12),
            anchor="w",
            justify="left",
            wraplength=740,
        )
        self.weight_help.grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 10)
        )
        self.weight_help.grid_remove()

        self.dimension_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.dimension_frame.grid(
            row=2, column=0, sticky="ew", padx=8, pady=8
        )
        for column in range(3):
            self.dimension_frame.grid_columnconfigure(column, weight=1, uniform="dimension")

        details = ctk.CTkFrame(tab, fg_color="transparent")
        details.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        details.grid_columnconfigure(0, weight=1)
        details.grid_columnconfigure(1, weight=1)
        details.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(details, text="Problems", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=6
        )
        ctk.CTkLabel(
            details, text="Recommendations", font=ctk.CTkFont(weight="bold")
        ).grid(row=0, column=1, sticky="w", padx=6)
        self.problems_textbox = ctk.CTkTextbox(details, height=140, wrap="word")
        self.problems_textbox.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)
        self.recommendations_textbox = ctk.CTkTextbox(details, height=140, wrap="word")
        self.recommendations_textbox.grid(
            row=1, column=1, sticky="nsew", padx=6, pady=4
        )
        self._set_text(self.problems_textbox, "No evaluation yet.")
        self._set_text(self.recommendations_textbox, "No evaluation yet.")

        self.export_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self.export_status.grid(row=4, column=0, sticky="w", padx=14, pady=(0, 8))

    def _load_dataset(self):
        if self._busy:
            return
        selected = filedialog.askopenfilename(
            filetypes=[
                ("Supported datasets", "*.csv *.CSV *.xlsx *.XLSX *.parquet *.PARQUET"),
                ("CSV files", "*.csv *.CSV"),
                ("Excel files", "*.xlsx *.XLSX"),
                ("Parquet files", "*.parquet *.PARQUET"),
            ]
        )
        if not selected:
            return

        # Release the previous dataset before allocating a replacement.
        self.df = self.info = self.dataset_profile = self.context = self.result = None
        self._reset_results()
        self._refresh_metadata_status()
        self._refresh_metadata_evidence(UsageContext(""))
        for value in self.summary_values.values():
            value.configure(text="-")
        self._set_text(self.profile_preview, "Loading and profiling dataset...")
        self.load_status.configure(text="Loading dataset...", text_color="gray")

        def work(progress):
            df, info = load(selected, progress=progress)
            return df, info, profile(df, progress=progress)

        self._run_background(
            work,
            self._dataset_loaded,
            lambda error: self.load_status.configure(text=f"Error: {error}", text_color="#ff6b6b"),
            lambda message: self.load_status.configure(text=message, text_color="gray"),
        )

    def _dataset_loaded(self, loaded):
        df, info, dataset_profile = loaded

        self.df = df
        self.info = info
        self.dataset_profile = dataset_profile
        self.context = None
        self.result = None
        self.dimension_weights = None
        self.weight_task_type = None
        self.load_status.configure(
            text=f"Dataset loaded: {info['file']}", text_color="#67d391"
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

    def _run_background(self, work, on_success, on_error, on_progress=None):
        """Run one operation off the Tk thread; deliver all UI changes via after()."""
        self._busy = True
        buttons = (
            self.load_button, self.load_next_button, self.evaluate_button,
            self.export_button, self.metadata_button, self.remove_metadata_button,
        )
        for button in buttons:
            button.configure(state="disabled")
        messages = Queue()

        def worker():
            try:
                result = work(lambda message: messages.put(("progress", message)))
                messages.put(("success", result))
            except Exception as error:
                messages.put(("error", str(error) or type(error).__name__))

        def poll():
            progress = None
            while True:
                try:
                    kind, value = messages.get_nowait()
                except Empty:
                    if progress is not None and on_progress:
                        on_progress(progress)
                    self.after(100, poll)
                    return
                if kind == "progress":
                    progress = value
                    continue
                self._busy = False
                try:
                    if kind == "success":
                        on_success(value)
                    else:
                        on_error(value)
                finally:
                    self.load_button.configure(state="normal")
                    state = "normal" if self.df is not None else "disabled"
                    self.load_next_button.configure(state=state)
                    self.evaluate_button.configure(state=state)
                    self.export_button.configure(
                        state="normal" if self.result is not None else "disabled"
                    )
                    self._refresh_metadata_controls()
                return

        Thread(target=worker, daemon=True).start()
        self.after(100, poll)

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
        self._refresh_metadata_status()
        self._refresh_metadata_evidence(UsageContext(""))
        self.context_status.configure(
            text="Set the usage context, then continue.", text_color="gray"
        )
        self.evaluation_status.configure(
            text=f"Ready to evaluate {self.info['file']} after saving the context.",
            text_color="gray",
        )

    def _context_from_controls(self):
        target_name = self.target_menu.get()
        target = None if target_name == NO_TARGET else self.column_lookup[target_name]
        return UsageContext(
            project_goal=self.goal_entry.get().strip(),
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

    def _save_context(self, navigate=True):
        if self._busy:
            return False
        if self.df is None:
            self.context_status.configure(
                text="Load a dataset first.", text_color="#ff6b6b"
            )
            return False
        context = self._context_from_controls()
        if not context.project_goal:
            self.context_status.configure(
                text="Enter a project goal.", text_color="#ff6b6b"
            )
            return False
        if context != self.context:
            self._reset_results()
        if context.task_type != self.weight_task_type or (
            self.context is not None and context.target_column != self.context.target_column
        ):
            self.dimension_weights = None
            self.weight_task_type = context.task_type
        self.context = context
        self._refresh_metadata_evidence(context)
        self.context_status.configure(text="Context saved.", text_color="#67d391")
        self.evaluation_status.configure(
            text=f"{self.info['file']} is ready to evaluate.", text_color="gray"
        )
        if navigate:
            self.tabs.set(EVALUATE_TAB)
        return True

    def _evaluate(self):
        if self._busy:
            return
        if not self._save_context(navigate=False):
            self.tabs.set(CONTEXT_TAB)
            return
        self.evaluation_status.configure(text="Evaluating...", text_color="gray")
        df, context, dataset_profile = self.df, self.context, self.dataset_profile
        dimension_weights = self.dimension_weights
        self._run_background(
            lambda progress: evaluate_dataset(
                df, context, dataset_profile, dimension_weights=dimension_weights
            ),
            self._evaluation_complete,
            lambda error: self.evaluation_status.configure(
                text=f"Evaluation failed: {error}", text_color="#ff6b6b"
            ),
        )

    def _evaluation_complete(self, result):
        self.result = result
        self.evaluation_status.configure(text="Evaluation complete.", text_color="#67d391")
        self._show_results()
        self.tabs.set(RESULTS_TAB)

    def _show_results(self):
        color = self._refresh_score_summary()
        self.weight_toggle.configure(state="normal")
        for widget in self.dimension_frame.winfo_children():
            widget.destroy()
        self.dimension_cards = {}
        problems = []
        recommendations = []
        defaults = DIMENSION_WEIGHTS[self.context.task_type]
        for index, dimension in enumerate(self.result["dimensions"]):
            name = dimension["dimension"]
            card = DimensionCard(
                self.dimension_frame,
                dimension,
                defaults.get(name),
                color,
                lambda value, name=name: self._change_dimension_weight(name, value),
                help_text=DIMENSION_HELP.get(name),
            )
            card.grid(
                row=index // 3, column=index % 3, sticky="nsew", padx=6, pady=6
            )
            card.set_controls_visible(self.weights_expanded)
            self.dimension_cards[name] = card
            problems.extend(
                f"[{name}] {item}" for item in dimension["problems"]
            )
            recommendations.extend(
                f"[{name}] {item}" for item in dimension["recommendations"]
            )

        self._set_text(
            self.problems_textbox,
            "\n\n".join(problems) if problems else "No problems found.",
        )
        self._set_text(
            self.recommendations_textbox,
            "\n\n".join(recommendations) if recommendations else "No recommendations.",
        )
        self.results_scroll._parent_canvas.yview_moveto(0)

    def _refresh_score_summary(self):
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
        custom = self.result["weight_source"] == "custom"
        source = "Custom weights" if custom else "Study defaults"
        self.weight_source_label.configure(
            text=f"{source} · {self.context.task_type.capitalize()}"
        )
        self.reset_weights_button.configure(state="normal" if custom else "disabled")
        return color

    def _toggle_weights(self):
        self._set_weights_expanded(not self.weights_expanded)

    def _set_weights_expanded(self, expanded):
        self.weights_expanded = expanded
        self.weight_toggle.configure(
            text="Collapse weights" if expanded else "Adjust weights"
        )
        if expanded:
            self.weight_help.grid()
            self.reset_weights_button.grid()
        else:
            self.weight_help.grid_remove()
            self.reset_weights_button.grid_remove()
        for card in self.dimension_cards.values():
            card.set_controls_visible(expanded)

    def _change_dimension_weight(self, name, value):
        weights = dict(
            DIMENSION_WEIGHTS[self.context.task_type]
            if self.dimension_weights is None else self.dimension_weights
        )
        weights[name] = round(value, 1)
        self._apply_dimension_weights(weights)

    def _reset_weights(self):
        self._apply_dimension_weights(None, sync_sliders=True)

    def _apply_dimension_weights(self, weights, *, sync_sliders=False):
        try:
            evaluation = aggregate(self.result["dimensions"], self.context.task_type, weights)
        except ValueError as error:
            self.weight_help.configure(text=str(error), text_color=("#996723", "#DBB677"))
            for dimension in self.result["dimensions"]:
                self.dimension_cards[dimension["dimension"]].update_weight(
                    dimension, sync_slider=True
                )
            return

        self.result = evaluation
        self.dimension_weights = weights if evaluation["weight_source"] == "custom" else None
        self.weight_help.configure(text=WEIGHT_HELP, text_color=MUTED_TEXT)
        color = self._refresh_score_summary()
        for dimension in evaluation["dimensions"]:
            card = self.dimension_cards[dimension["dimension"]]
            card.progress.configure(progress_color=color)
            card.update_weight(dimension, sync_slider=sync_sliders)

    def _reset_results(self):
        self.result = None
        self._set_weights_expanded(False)
        self.weight_toggle.configure(state="disabled")
        self.weight_source_label.configure(text="Available after evaluation")
        self.weight_help.configure(text=WEIGHT_HELP, text_color=MUTED_TEXT)
        self.reset_weights_button.configure(state="disabled")
        self.score_label.configure(text="-", text_color=("black", "white"))
        self.classification_label.configure(
            text="Run an evaluation to see results.", text_color="gray"
        )
        self.export_button.configure(state="disabled")
        self.export_status.configure(text="")
        for widget in self.dimension_frame.winfo_children():
            widget.destroy()
        self.dimension_cards = {}
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
