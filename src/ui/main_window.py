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
from src.ui import theme
from src.ui.dimension_card import DimensionCard
from src.ui.preparation_page import PreparationPage
from src.ui.theme import CONTROL, DISABLED, INK, MUTED, combobox, font, style_ttk
from src.ui.widgets import BusyLine, CheckBox, LevelMeter, Tabs, animate, button, emphasize


LOAD_TAB = "1. Load"
CONTEXT_TAB = "2. Context"
EVALUATE_TAB = "3. Evaluate"
RESULTS_TAB = "4. Results"
PREPARATION_TAB = "5. Preparation"
NO_TARGET = "No target"
WEIGHT_HELP = (
    "Defaults informed by our studies. Adjust relative importance; "
    "0 leaves a dimension out of the overall score."
)
READINESS_LEVELS = {"Not ready": 1, "Requires preparation": 2, "Almost ready": 3, "Ready": 4}


class DataReadinessApp(ctk.CTk):
    def __init__(self):
        theme.install()
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
        self._busy_job = None
        self._shown_score = 0.0
        self.dimension_weights = None
        self.weight_task_type = None
        self.weights_expanded = False
        self.dimension_cards = {}
        self._loaded_path = None

        self._build_interface()
        style_ttk(self)

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "tabs"):
            style_ttk(self)

    def destroy(self):
        # Pending animation frames would otherwise fire after their widgets are gone. Cancel the
        # timers only; each widget still deletes its own callback commands as it is destroyed.
        try:
            for job in self.tk.call("after", "info"):
                self.tk.call("after", "cancel", job)
        except Exception:
            pass
        super().destroy()

    def _build_interface(self):
        header = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        header.pack(fill="x", padx=32, pady=(12, 0))
        header.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(header, text="Data Readiness Framework", font=font(15, "semibold")).grid(
            row=0, column=0, sticky="w"
        )
        # The divider under the header doubles as the busy indicator.
        self.busy_bar = BusyLine(self)
        self.busy_bar.pack(fill="x")

        self.tabs = Tabs(
            self, header, (LOAD_TAB, CONTEXT_TAB, EVALUATE_TAB, RESULTS_TAB, PREPARATION_TAB),
            command=self._tab_changed,
        )
        self.tabs.nav.grid(row=0, column=1, sticky="sw", padx=(40, 0))
        self.tabs.pack(fill="both", expand=True, padx=32, pady=(28, 24))

        self._build_load_tab()
        self._build_context_tab()
        self._build_evaluate_tab()
        self._build_results_tab()
        self.preparation_page = PreparationPage(self.tabs.tab(PREPARATION_TAB), self._run_background)
        self.preparation_page.pack(fill="both", expand=True)
        self.tabs.set(LOAD_TAB)

    def _tab_changed(self):
        if self.tabs.get() == PREPARATION_TAB:
            self.preparation_page.activate()

    def _open_preparation(self):
        self.tabs.set(PREPARATION_TAB)
        self.preparation_page.activate()

    @staticmethod
    def _title(parent, text, size=20):
        return ctk.CTkLabel(parent, text=text, font=font(size, "semibold"), text_color=INK, anchor="w")

    @staticmethod
    def _caption(parent, text="", **kwargs):
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("justify", "left")
        return ctk.CTkLabel(parent, text=text, text_color=MUTED, font=font(12), **kwargs)

    def _stat(self, parent, title, column):
        stat = ctk.CTkFrame(parent, fg_color="transparent")
        stat.grid(row=0, column=column, sticky="w", padx=(0, 48))
        self._caption(stat, title).pack(anchor="w")
        value = ctk.CTkLabel(stat, text="-", font=font(24, "semibold"), text_color=DISABLED, anchor="w")
        value.pack(anchor="w")
        return value

    @staticmethod
    def _set_stat(label, value):
        """An empty value stays dim so the page reads calm until data arrives."""
        label.configure(text=value, text_color=DISABLED if value == "-" else INK)

    def _build_load_tab(self):
        tab = self.tabs.tab(LOAD_TAB)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=1)

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        self._title(top, "Load a dataset").grid(row=0, column=0, sticky="w")
        self.load_status = ctk.CTkLabel(
            top, text="CSV, XLSX or Parquet.", text_color=MUTED, anchor="w"
        )
        self.load_status.grid(row=1, column=0, sticky="ew")
        self.load_button = button(top, "Choose file", self._load_dataset, "primary", width=140, height=36)
        self.load_button.grid(row=0, column=1, rowspan=2, sticky="e")

        stats = ctk.CTkFrame(tab, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(32, 32))
        self.summary_values = {}
        for column, title in enumerate(("Format", "Rows", "Columns", "Missing")):
            self.summary_values[title] = self._stat(stats, title, column)

        self._title(tab, "Column profile", 15).grid(row=2, column=0, sticky="w", pady=(0, 12))
        self.profile_empty = self._caption(tab, "Load a dataset to see its columns.")
        self.profile_empty.grid(row=3, column=0, sticky="ew")
        self.profile_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.profile_frame.grid(row=4, column=0, sticky="nsew")
        self.profile_frame.grid_columnconfigure(0, weight=1)
        self.profile_frame.grid_rowconfigure(0, weight=1)
        self.profile_table = ttk.Treeview(
            self.profile_frame, columns=("column", "type", "missing", "unique"),
            show="headings", style="Monolith.Treeview",
        )
        for name, title, width in (
            ("column", "Column", 260), ("type", "Type", 160),
            ("missing", "Missing", 120), ("unique", "Unique values", 120),
        ):
            self.profile_table.heading(name, text=title, anchor="w" if name in ("column", "type") else "e")
            self.profile_table.column(
                name, width=width, minwidth=60, anchor="w" if name in ("column", "type") else "e"
            )
        self.profile_table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            self.profile_frame, orient="vertical", command=self.profile_table.yview,
            style="Monolith.Vertical.TScrollbar",
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.profile_table.configure(yscrollcommand=scroll.set)
        self.profile_frame.grid_remove()

        self.load_next_button = button(
            tab, "Continue to context", lambda: self.tabs.set(CONTEXT_TAB), "secondary", width=170, height=36,
        )
        self.load_next_button.configure(state="disabled")
        self.load_next_button.grid(row=5, column=0, sticky="e", pady=(24, 0))

    def _show_profile(self, message=None):
        self.profile_table.delete(*self.profile_table.get_children())
        if message is not None:
            self.profile_frame.grid_remove()
            self.profile_empty.configure(text=message)
            self.profile_empty.grid()
            return
        for name, values in self.dataset_profile["columns"].items():
            self.profile_table.insert("", "end", values=(
                name, values["type"], f"{values['missing_percentage']:.2f}%", f"{values['unique_count']:,}",
            ))
        self.profile_empty.grid_remove()
        self.profile_frame.grid()

    def _build_context_tab(self):
        tab = self.tabs.tab(CONTEXT_TAB)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(tab, fg_color="transparent")
        form.grid(row=0, column=0, sticky="ew")
        form.grid_columnconfigure(0, weight=3)
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(2, weight=1)

        self.goal_entry = self._form_field(form, "Project goal", 0)
        self._caption(form, "Task type").grid(row=0, column=1, sticky="ew", padx=(16, 0), pady=(0, 4))
        self.task_menu = ctk.CTkOptionMenu(
            form, values=["classification", "regression", "other"], height=36, font=font(13),
            dropdown_font=font(13),
        )
        self.task_menu.set("other")
        self.task_menu.grid(row=1, column=1, sticky="ew", padx=(16, 0))

        self._caption(form, "Target column").grid(row=0, column=2, sticky="ew", padx=(16, 0), pady=(0, 4))
        self.target_menu = combobox(form, values=[NO_TARGET], state="readonly", height=12)
        self.target_menu.set(NO_TARGET)
        self.target_menu.grid(row=1, column=2, sticky="ew", padx=(16, 0))
        self.target_menu.bind("<<ComboboxSelected>>", self._context_evidence_changed)

        metadata_controls = ctk.CTkFrame(tab, fg_color="transparent")
        metadata_controls.grid(row=1, column=0, sticky="ew", pady=(20, 0))
        metadata_controls.grid_columnconfigure(0, weight=1)
        self.metadata_status = self._caption(
            metadata_controls, "No metadata selected. Checked items take priority over JSON.",
            wraplength=600,
        )
        self.metadata_status.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        self.metadata_button = button(
            metadata_controls, "Choose metadata JSON", self._load_metadata, "secondary", width=170,
        )
        self.metadata_button.configure(state="disabled")
        self.metadata_button.grid(row=0, column=1)
        self.remove_metadata_button = button(
            metadata_controls, "Remove", self._remove_metadata, "ghost", width=80,
        )
        self.remove_metadata_button.configure(state="disabled")
        self.remove_metadata_button.grid(row=0, column=2, padx=(8, 0))

        checklists = ctk.CTkFrame(tab, fg_color="transparent")
        checklists.grid(row=2, column=0, sticky="nsew", pady=(32, 0))
        for column in range(3):
            checklists.grid_columnconfigure(column, weight=1, uniform="checklist")
        checklists.grid_rowconfigure(2, weight=1)

        titles = ("Important columns", "Documentation", "Provenance")
        captions = (
            "Columns that matter most for the project goal.",
            DIMENSION_HELP["Documentation"],
            DIMENSION_HELP["Provenance"],
        )
        for column, (title, text) in enumerate(zip(titles, captions)):
            padx = (0 if column == 0 else 24, 0)
            self._title(checklists, title, 15).grid(row=0, column=column, sticky="ew", padx=padx)
            caption = self._caption(checklists, text, wraplength=300)
            caption.grid(row=1, column=column, sticky="new", padx=padx, pady=(4, 8))
            if column == 1:
                self.documentation_caption = caption
            elif column == 2:
                self.provenance_caption = caption

        frames = []
        for column in range(3):
            frame = ctk.CTkScrollableFrame(checklists, fg_color="transparent", corner_radius=0, height=200)
            frame.grid(row=2, column=column, sticky="nsew", padx=(0 if column == 0 else 24, 0))
            frames.append(frame)
        self.important_frame, self.documentation_frame, self.provenance_frame = frames
        self._build_checklist(
            self.documentation_frame, DOCUMENTATION_ITEMS, self.documentation_vars
        )
        self._build_checklist(
            self.provenance_frame, PROVENANCE_ITEMS, self.provenance_vars
        )

        notes_frame = ctk.CTkFrame(tab, fg_color="transparent")
        notes_frame.grid(row=3, column=0, sticky="ew", pady=(24, 0))
        self._caption(notes_frame, "Notes").pack(fill="x", pady=(0, 4))
        self.notes_textbox = ctk.CTkTextbox(
            notes_frame, height=64, border_width=1, border_color=CONTROL, corner_radius=6, font=font(13)
        )
        self.notes_textbox.pack(fill="x")

        footer = ctk.CTkFrame(tab, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", pady=(24, 0))
        self.context_status = ctk.CTkLabel(
            footer, text="Load a dataset before setting the context.", text_color=MUTED
        )
        self.context_status.pack(side="left")
        button(
            footer, "Save and continue", self._save_context, "primary", width=160, height=36
        ).pack(side="right")

    def _form_field(self, parent, title, column):
        self._caption(parent, title).grid(row=0, column=column, sticky="ew", pady=(0, 4))
        entry = ctk.CTkEntry(parent, height=36, font=font(13))
        entry.grid(row=1, column=column, sticky="ew")
        return entry

    def _build_checklist(self, parent, items, variables):
        parent.grid_columnconfigure(0, weight=1)
        for row, item in enumerate(items):
            variable = BooleanVar(value=False)
            variables[item] = variable
            CheckBox(
                parent,
                text=item.replace("_", " ").capitalize(),
                variable=variable,
                command=self._context_evidence_changed,
            ).grid(row=row * 2, column=0, sticky="w", pady=(8, 0))
            label = self._caption(parent, "Evidence missing, 0%", wraplength=250)
            label.grid(row=row * 2 + 1, column=0, sticky="ew", padx=(26, 0), pady=(0, 4))
            self.evidence_labels[item] = label

    def _refresh_metadata_evidence(self, context):
        for evaluate in (evaluate_documentation, evaluate_provenance):
            dimension = evaluate(context, self.df)
            for item in (*dimension["indicators"], *dimension["excluded_indicators"]):
                text = (
                    "Not applicable" if item["status"] == "not_applicable" else
                    f"{item['status'].replace('_', ' ').capitalize()}, {item['value']:g}%"
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
        self.preparation_page.evidence_changed()
        self._reset_results()
        self._refresh_metadata_status()
        self._refresh_metadata_evidence(self._context_from_controls())
        self.evaluation_status.configure(text="Metadata changed. Run the evaluation again.", text_color=MUTED)

    def _remove_metadata(self):
        if self._busy or self.df is None:
            return
        self._metadata_loaded(read_metadata(None, dataset_sha256=self.info.get("sha256")))

    def _build_evaluate_tab(self):
        tab = self.tabs.tab(EVALUATE_TAB)
        tab.grid_columnconfigure(0, weight=1)

        self._title(tab, "Evaluate readiness").grid(row=0, column=0, sticky="w")
        self.evaluation_status = ctk.CTkLabel(
            tab, text="Load a dataset and save its usage context first.", text_color=MUTED, anchor="w",
        )
        self.evaluation_status.grid(row=1, column=0, sticky="ew")

        review = ctk.CTkFrame(tab, fg_color="transparent")
        review.grid(row=2, column=0, sticky="ew", pady=(32, 32))
        self.review_values = {}
        for column, title in enumerate(("Dataset", "Task", "Target", "Important columns")):
            self.review_values[title] = self._stat(review, title, column)
            self.review_values[title].configure(font=font(17, "semibold"))

        self.evaluate_button = button(tab, "Evaluate", self._evaluate, "primary", width=160, height=36)
        self.evaluate_button.configure(state="disabled")
        self.evaluate_button.grid(row=3, column=0, sticky="w")

    def _refresh_review(self):
        context = self.context
        values = {
            "Dataset": self.info["file"] if self.info else "-",
            "Task": context.task_type.capitalize() if context else "-",
            "Target": "-" if context is None else (
                NO_TARGET if context.target_column is None else str(context.target_column)
            ),
            "Important columns": f"{len(context.important_columns):,}" if context else "-",
        }
        for name, value in values.items():
            self._set_stat(self.review_values[name], value)

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

        summary = ctk.CTkFrame(tab, fg_color="transparent")
        summary.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        summary.grid_columnconfigure(1, weight=1)
        self.score_label = ctk.CTkLabel(
            summary, text="-", font=font(44, "bold"), text_color=DISABLED, anchor="w"
        )
        self.score_label.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 20))
        self.classification_label = ctk.CTkLabel(
            summary, text="Run an evaluation to see results.", text_color=MUTED,
            font=font(15, "semibold"), anchor="w",
        )
        self.classification_label.grid(row=0, column=1, sticky="sw")
        self.level_meter = LevelMeter(summary)
        self.level_meter.grid(row=1, column=1, sticky="nw", pady=(6, 0))
        self.prepare_button = button(summary, "Prepare dataset", self._open_preparation, "primary", width=150)
        self.prepare_button.configure(state="disabled")
        self.prepare_button.grid(row=0, column=2, rowspan=2, padx=(0, 8))
        self.export_button = button(summary, "Export report", self._export_report, "secondary", width=130)
        self.export_button.configure(state="disabled")
        self.export_button.grid(row=0, column=3, rowspan=2)

        weights_header = ctk.CTkFrame(tab, fg_color="transparent")
        weights_header.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(40, 12))
        weights_header.grid_columnconfigure(1, weight=1)
        self.weights_title = self._title(weights_header, "Dimension weights", 15)
        self.weights_title.grid(row=0, column=0, sticky="w")
        self.weight_source_label = self._caption(
            weights_header, "Choose how much each dimension counts in the overall score."
        )
        self.weight_source_label.grid(row=0, column=1, sticky="w", padx=12)
        self.reset_weights_button = button(
            weights_header, "Reset to defaults", self._reset_weights, "ghost", width=130,
        )
        self.reset_weights_button.configure(state="disabled")
        self.reset_weights_button.grid(row=0, column=2, sticky="e", padx=(0, 8))
        self.reset_weights_button.grid_remove()
        self.weight_toggle = button(
            weights_header, "Adjust weights", self._toggle_weights, "secondary", width=130,
        )
        self.weight_toggle.configure(state="disabled")
        self.weight_toggle.grid(row=0, column=3, sticky="e")
        self.weight_help = self._caption(weights_header, WEIGHT_HELP, wraplength=740)
        self.weight_help.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        self.weight_help.grid_remove()

        self.dimension_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.dimension_frame.grid(row=2, column=0, sticky="ew", padx=(0, 12))
        # Cards sit in even columns; the odd columns are fixed gutters so every card is the same width.
        for column in range(5):
            if column % 2:
                self.dimension_frame.grid_columnconfigure(column, minsize=12)
            else:
                self.dimension_frame.grid_columnconfigure(column, weight=1, uniform="dimension")

        details = ctk.CTkFrame(tab, fg_color="transparent")
        details.grid(row=3, column=0, sticky="nsew", padx=(0, 12), pady=(40, 0))
        details.grid_columnconfigure(0, weight=1, uniform="details")
        details.grid_columnconfigure(1, weight=1, uniform="details")
        details.grid_rowconfigure(1, weight=1)
        self._title(details, "Problems", 15).grid(row=0, column=0, sticky="w", pady=(0, 12))
        self._title(details, "Recommendations", 15).grid(
            row=0, column=1, sticky="w", padx=(24, 0), pady=(0, 12)
        )
        self.problems_textbox = ctk.CTkTextbox(details, height=160, wrap="word", font=font(13))
        self.problems_textbox.grid(row=1, column=0, sticky="nsew")
        self.recommendations_textbox = ctk.CTkTextbox(details, height=160, wrap="word", font=font(13))
        self.recommendations_textbox.grid(row=1, column=1, sticky="nsew", padx=(24, 0))
        self._set_text(self.problems_textbox, "No evaluation yet.")
        self._set_text(self.recommendations_textbox, "No evaluation yet.")

        self.export_status = ctk.CTkLabel(tab, text="", text_color=MUTED, anchor="w")
        self.export_status.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        self._caption(
            tab, "Assessment of the original dataset. Use Preparation to preview changes and compare a working copy.",
        ).grid(row=5, column=0, sticky="ew", pady=(0, 8))

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

        self._loaded_path = selected
        self.preparation_page.set_dataset()
        # Release the previous dataset before allocating a replacement.
        self.df = self.info = self.dataset_profile = self.context = self.result = None
        self._reset_results()
        self._refresh_metadata_status()
        self._refresh_metadata_evidence(UsageContext(""))
        for value in self.summary_values.values():
            self._set_stat(value, "-")
        self._show_profile("Loading and profiling dataset...")
        self._refresh_review()
        self.load_status.configure(text="Loading dataset...", text_color=MUTED)

        def work(progress):
            df, info = load(selected, progress=progress)
            return df, info, profile(df, progress=progress)

        self._run_background(
            work,
            self._dataset_loaded,
            lambda error: self.load_status.configure(text=f"Error: {error}", text_color=INK),
            lambda message: self.load_status.configure(text=message, text_color=MUTED),
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
        self.preparation_page.set_dataset(df, info, self._loaded_path)
        self.load_status.configure(
            text=f"Loaded {info['file']}", text_color=MUTED
        )
        summary = dataset_profile["dataset"]
        values = {
            "Format": info["format"].upper(),
            "Rows": f"{info['rows']:,}",
            "Columns": f"{info['columns']:,}",
            "Missing": f"{summary['missing_percentage']:.2f}%",
        }
        for name, value in values.items():
            self._set_stat(self.summary_values[name], str(value))
        self._show_profile()
        self.load_next_button.configure(state="normal")
        emphasize(self.load_button, False)
        emphasize(self.load_next_button, True)
        self.evaluate_button.configure(state="normal")
        self._reset_context_controls()
        self._reset_results()

    def _run_background(self, work, on_success, on_error, on_progress=None):
        """Run one operation off the Tk thread; deliver all UI changes via after()."""
        self._busy = True
        self._show_busy(True)
        self.preparation_page.set_busy(True)
        buttons = (
            self.load_button, self.load_next_button, self.evaluate_button,
            self.export_button, self.metadata_button, self.remove_metadata_button,
            self.prepare_button,
        )
        for widget in buttons:
            widget.configure(state="disabled")
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
                self._show_busy(False)
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
                    self.prepare_button.configure(state="normal" if self.result is not None else "disabled")
                    self.preparation_page.set_busy(False)
                return

        Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _show_busy(self, busy):
        """Run the header line only for work slow enough to notice, and stop it the moment it ends."""
        if self._busy_job is not None:
            self.after_cancel(self._busy_job)
            self._busy_job = None
        if busy:
            self._busy_job = self.after(150, self._start_busy_bar)
        else:
            self.busy_bar.stop()

    def _start_busy_bar(self):
        self._busy_job = None
        self.busy_bar.start()

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
            CheckBox(
                self.important_frame, text=str(name), variable=variable
            ).grid(row=row, column=0, sticky="w", pady=(8, 0))
        for variable in (*self.documentation_vars.values(), *self.provenance_vars.values()):
            variable.set(False)
        self.notes_textbox.delete("1.0", "end")
        self._refresh_metadata_status()
        self._refresh_metadata_evidence(UsageContext(""))
        self.context_status.configure(
            text="Set the usage context, then continue.", text_color=MUTED
        )
        self.evaluation_status.configure(
            text=f"Save the context to evaluate {self.info['file']}.",
            text_color=MUTED,
        )
        self._refresh_review()

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
                text="Load a dataset first.", text_color=INK
            )
            return False
        context = self._context_from_controls()
        if not context.project_goal:
            self.context_status.configure(
                text="Enter a project goal to continue.", text_color=INK
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
        self.preparation_page.set_context(context, self.dimension_weights)
        self.context_status.configure(text="Context saved.", text_color=INK)
        self.evaluation_status.configure(
            text=f"{self.info['file']} is ready to evaluate.", text_color=MUTED
        )
        self._refresh_review()
        if navigate:
            self.tabs.set(EVALUATE_TAB)
        return True

    def _evaluate(self):
        if self._busy:
            return
        if not self._save_context(navigate=False):
            self.tabs.set(CONTEXT_TAB)
            return
        self.evaluation_status.configure(text="Evaluating...", text_color=MUTED)
        df, context, dataset_profile = self.df, self.context, self.dataset_profile
        dimension_weights = self.dimension_weights
        self._run_background(
            lambda progress: evaluate_dataset(
                df, context, dataset_profile, dimension_weights=dimension_weights
            ),
            self._evaluation_complete,
            lambda error: self.evaluation_status.configure(
                text=f"Evaluation failed: {error}", text_color=INK
            ),
        )

    def _evaluation_complete(self, result):
        self.result = result
        self.evaluation_status.configure(text="Evaluation complete.", text_color=MUTED)
        self._show_results()
        self.tabs.set(RESULTS_TAB)

    def _show_results(self):
        self._refresh_score_summary(duration=600, start=0.0)
        self.weight_toggle.configure(state="normal")
        self.prepare_button.configure(state="normal")
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
                lambda value, name=name: self._change_dimension_weight(name, value),
                help_text=DIMENSION_HELP.get(name),
            )
            card.grid(row=index // 3, column=index % 3 * 2, sticky="nsew", pady=(0, 12))
            card.set_controls_visible(self.weights_expanded)
            card.reveal()
            self.dimension_cards[name] = card
            problems.extend(
                f"{name}: {item}" for item in dimension["problems"]
            )
            recommendations.extend(
                f"{name}: {item}" for item in dimension["recommendations"]
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

    def _refresh_score_summary(self, duration=220, start=None):
        score = self.result["score"]
        origin = self._shown_score if start is None else start

        def step(t):
            self._shown_score = origin + (score - origin) * t
            self.score_label.configure(text=f"{self._shown_score:.2f}", text_color=INK)

        animate(self.score_label, "score", duration, step)
        self.classification_label.configure(text=self.result["classification"], text_color=INK)
        self.level_meter.set(READINESS_LEVELS.get(self.result["classification"], 0))
        self.export_button.configure(state="normal")
        self.export_status.configure(text="")
        custom = self.result["weight_source"] == "custom"
        source = "Custom weights" if custom else "Study defaults"
        self.weight_source_label.configure(
            text=f"{source} for {self.context.task_type}"
        )
        self.reset_weights_button.configure(state="normal" if custom else "disabled")

    def _toggle_weights(self):
        self._set_weights_expanded(not self.weights_expanded)

    def _set_weights_expanded(self, expanded):
        self.weights_expanded = expanded
        self.weight_toggle.configure(
            text="Hide weights" if expanded else "Adjust weights"
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
        if self._busy:
            return
        try:
            evaluation = aggregate(self.result["dimensions"], self.context.task_type, weights)
        except ValueError as error:
            self.weight_help.configure(text=str(error), text_color=INK)
            for dimension in self.result["dimensions"]:
                self.dimension_cards[dimension["dimension"]].update_weight(
                    dimension, sync_slider=True
                )
            return

        self.result = evaluation
        self.dimension_weights = weights if evaluation["weight_source"] == "custom" else None
        self.preparation_page.set_context(self.context, self.dimension_weights)
        self.weight_help.configure(text=WEIGHT_HELP, text_color=MUTED)
        self._refresh_score_summary()
        for dimension in evaluation["dimensions"]:
            self.dimension_cards[dimension["dimension"]].update_weight(
                dimension, sync_slider=sync_sliders
            )

    def _reset_results(self):
        self.result = None
        self._set_weights_expanded(False)
        self.weight_toggle.configure(state="disabled")
        self.weight_source_label.configure(text="Available after evaluation")
        self.weight_help.configure(text=WEIGHT_HELP, text_color=MUTED)
        self.reset_weights_button.configure(state="disabled")
        animate(self.score_label, "score", 0, lambda t: self._set_stat(self.score_label, "-"))
        self._shown_score = 0.0
        self.classification_label.configure(
            text="Run an evaluation to see results.", text_color=MUTED
        )
        self.level_meter.set(0)
        self.export_button.configure(state="disabled")
        self.prepare_button.configure(state="disabled")
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
                text=f"Export failed: {error}", text_color=INK
            )
            return
        self.export_status.configure(
            text=f"Saved {json_path.name} and {html_path.name}",
            text_color=INK,
        )

    @staticmethod
    def _set_text(textbox, text):
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")
