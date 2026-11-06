"""Guided preparation UI. Transformations and inspection live in src.preparation."""

from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, ttk

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from src.metadata import METADATA_ATTR
from src.preparation import Operation, PreparationSession
from src.ui.preparation_charts import CHART_VIEWS, preparation_figure, readiness_figure
from src.ui.theme import INK, MUTED, SURFACE, combobox, font
from src.ui.widgets import NavBar, button, emphasize


STEPS = ("1. Inspect", "2. Clean", "3. Normalize", "4. Compare & export")
ACTIONS = {
    "Outliers": {"Cap at IQR limits": "clip_outliers", "Remove flagged rows": "drop_outliers"},
    "Missing values": {"Fill with median": "fill_median", "Fill with most frequent value": "fill_mode",
                       "Remove rows missing this value": "drop_missing"},
    "Duplicates": {"Remove exact duplicates (keep first)": "duplicates"},
    "Text cleanup": {"Trim surrounding spaces": "trim", "Trim and standardize case": "casefold"},
    "Normalization": {"Min-max scaling (0-1)": "minmax", "Standardization (z-score)": "standardize"},
}
HELP = {
    "Outliers": "IQR flags unusual values, which may be valid. Capping replaces extremes with the displayed IQR limits; removal deletes the flagged rows.",
    "Missing values": "The chosen treatment affects one feature. Filling uses its median or most frequent value; removal deletes rows missing this feature.",
    "Duplicates": "Compare all columns and keep the first occurrence of each identical row. Repeated observations can be legitimate.",
    "Text cleanup": "Trim surrounding spaces, or also standardize case. Review the preview because distinct categories may merge.",
    "Normalization": "Choose measurements, excluding IDs and category codes. Min-max maps training values to 0-1; z-scores center at zero. Fit on training data only and reuse the exported parameters for test data.",
}
STEP_HINTS = (
    "Explore a feature before choosing a treatment.",
    "Review one cleanup at a time. Apply it only after checking the preview.",
    "Rescale a numerical measurement and review its before and after values.",
    "Compare the two versions, then export a separate prepared dataset.",
)


class PreparationPage(ctk.CTkFrame):
    def __init__(self, parent, run_background):
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self.run_background = run_background
        self.session = self.context = self.info = self.source_path = None
        self.dimension_weights = self.comparison = self._metadata_snapshot = None
        self.before = self.after_data = self.preview_change = None
        self.canvas = self.review_canvas = None
        self.column_lookup = {}
        self._duplicate_examples = []
        self.busy = self.details_open = self.history_open = False
        self.step = 0
        self.clean_category = "Outliers"
        self._build()
        self.bind("<Configure>", self._resize)
        self._configure_step()
        self.set_busy(False)

    @staticmethod
    def _button(parent, text, command, *, primary=False, kind=None, width=140):
        return button(parent, text, command, kind or ("primary" if primary else "secondary"), width=width)

    @staticmethod
    def _emphasize(widget, primary):
        emphasize(widget, primary)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Prepare dataset", font=font(20, "semibold"),
                     text_color=INK, anchor="w").grid(row=0, column=0, sticky="ew")
        self.summary = ctk.CTkLabel(header, text="Load a dataset to begin.", text_color=MUTED, anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew")
        self.undo_button = self._button(header, "Undo", self._undo, kind="ghost", width=64)
        self.undo_button.grid(row=0, column=1, rowspan=2, padx=(0, 4))
        self.reset_button = self._button(header, "Reset copy", self._reset, kind="ghost", width=96)
        self.reset_button.grid(row=0, column=2, rowspan=2)
        self.step_nav = NavBar(self, list(STEPS), command=self._choose_step, baseline=True)
        self.step_nav.set(STEPS[0])
        self.step_nav.grid(row=1, column=0, sticky="ew", pady=(20, 20))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.scroll.grid(row=2, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(self.scroll, text="Load a dataset and save its context to start.",
                                   text_color=MUTED, anchor="w", justify="left", wraplength=850)
        self.status.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 16))
        self._build_workspace()
        self._build_records()
        self._build_review()
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        footer.grid_columnconfigure(1, weight=1)
        self.back_button = self._button(footer, "Back", self._previous_step, kind="ghost", width=0)
        self.back_button.grid(row=0, column=0, sticky="w")
        self.step_count = ctk.CTkLabel(footer, text="0 applied changes", text_color=MUTED, font=font(12))
        self.step_count.grid(row=0, column=1)
        self.next_button = self._button(footer, "Continue to clean", self._next_step, primary=True, width=180)
        self.next_button.grid(row=0, column=2, sticky="e")
        self.preview_button = self._button(footer, "Preview change", self._preview, primary=True, width=190)
        self.preview_button.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.apply_button = self._button(footer, "Apply to working copy", self._apply, primary=True, width=190)
        self.apply_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

    def _build_workspace(self):
        self.workspace = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.workspace.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        self.workspace.grid_columnconfigure(1, weight=1)
        self.workspace.grid_columnconfigure(0, minsize=round(self._apply_widget_scaling(228)))
        controls = ctk.CTkFrame(self.workspace, fg_color="transparent", width=228)
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 24))
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(controls, text="Feature column", text_color=MUTED, font=font(12), anchor="w").grid(
            row=0, column=0, sticky="ew")
        self.column_menu = combobox(controls, state="readonly", width=25, height=12)
        self.column_menu.grid(row=1, column=0, sticky="ew", pady=(4, 20))
        self.column_menu.bind("<<ComboboxSelected>>", self._selection_changed)
        self.category_label = ctk.CTkLabel(controls, text="Issue", text_color=MUTED, font=font(12), anchor="w")
        self.category_label.grid(row=2, column=0, sticky="ew")
        self.category_menu = ctk.CTkOptionMenu(
            controls, values=list(ACTIONS)[:-1], command=self._choose_category,
            width=228, height=34, font=font(13), dropdown_font=font(13), dynamic_resizing=False,
        )
        self.category_menu.grid(row=3, column=0, sticky="ew", pady=(4, 20))
        self.method_label = ctk.CTkLabel(controls, text="Treatment", text_color=MUTED, font=font(12), anchor="w")
        self.method_label.grid(row=4, column=0, sticky="ew")
        self.method_menu = ctk.CTkOptionMenu(
            controls, values=list(ACTIONS["Outliers"]), command=self._selection_changed,
            width=228, height=34, font=font(13), dropdown_font=font(13), dynamic_resizing=False,
        )
        self.method_menu.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        self.details_button = self._button(controls, "Method details", self._toggle_details,
                                           width=120)
        self.details_button.grid(row=6, column=0, sticky="w", pady=(0, 8))
        self.help_label = ctk.CTkLabel(controls, text=HELP["Outliers"], text_color=MUTED,
                                       wraplength=228, justify="left", anchor="w", font=font(12))
        self.help_label.grid(row=7, column=0, sticky="ew", pady=(0, 16))
        self.inspect_button = self._button(controls, "Refresh view", self._inspect, width=120)
        self.inspect_button.grid(row=8, column=0, sticky="w", pady=(12, 0))
        inspector = ctk.CTkFrame(self.workspace, fg_color="transparent")
        inspector.grid(row=0, column=1, sticky="nsew")
        inspector.grid_columnconfigure(0, weight=1)
        self.chart_view = ctk.CTkOptionMenu(
            inspector, values=list(CHART_VIEWS), command=lambda _: self._draw_chart(), width=180,
            height=34, font=font(13), dropdown_font=font(13),
        )
        self.chart_view.set("Distribution")
        self.chart_view.grid(row=0, column=0, sticky="e", pady=(0, 8))
        self.chart_frame = ctk.CTkFrame(inspector, fg_color=SURFACE, corner_radius=8)
        self.chart_frame.grid(row=1, column=0, sticky="ew")
        self.chart_placeholder = ctk.CTkLabel(
            self.chart_frame, text="Load a dataset and save its context to inspect a feature.",
            text_color=MUTED, wraplength=400,
        )
        self.chart_placeholder.pack(fill="both", expand=True, padx=16, pady=100)
        self.chart_note = ctk.CTkLabel(inspector, text="", text_color=MUTED, wraplength=550,
                                       font=font(12), justify="left", anchor="w")
        self.chart_note.grid(row=2, column=0, sticky="ew", pady=(8, 0))

    def _build_records(self):
        self.records_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.records_frame.grid(row=2, column=0, sticky="ew", padx=(0, 12), pady=(32, 12))
        self.records_frame.grid_columnconfigure(0, weight=1)
        self.preview_label = ctk.CTkLabel(self.records_frame, text="Flagged records", text_color=INK,
                                          anchor="w", justify="left", font=font(15, "semibold"))
        self.preview_label.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.record_hint = ctk.CTkLabel(self.records_frame, text="Source rows include the header as row 1.",
                                        text_color=MUTED, anchor="w", justify="left", wraplength=850, font=font(12))
        self.record_hint.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.table = ttk.Treeview(self.records_frame, columns=("row", "before", "after"),
                                  show="headings", height=4, style="Monolith.Treeview")
        for name, title, width in (("row", "Source row", 110), ("before", "Current value", 260), ("after", "Preview / finding", 280)):
            self.table.heading(name, text=title, anchor="w" if name == "after" else "e")
            self.table.column(name, width=width, minwidth=60, stretch=name != "row", anchor="w" if name == "after" else "e")
        self.table.grid(row=2, column=0, sticky="ew")
        self.table.bind("<<TreeviewSelect>>", self._duplicate_selected)
        self.record_scroll = ttk.Scrollbar(self.records_frame, orient="vertical", command=self.table.yview,
                                           style="Monolith.Vertical.TScrollbar")
        self.record_scroll.grid(row=2, column=1, sticky="ns")
        self.table.configure(yscrollcommand=self.record_scroll.set)
        self.record_empty = ctk.CTkLabel(self.records_frame, text="No flagged records in this view.", text_color=MUTED, anchor="w")
        self.record_empty.grid(row=3, column=0, sticky="ew")
        self.pair_frame = ctk.CTkFrame(self.records_frame, fg_color="transparent")
        self.pair_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(24, 0))
        self.pair_frame.grid_columnconfigure(0, weight=1)
        self.pair_title = ctk.CTkLabel(self.pair_frame, text="", text_color=INK,
                                       anchor="w", font=font(15, "semibold"))
        self.pair_title.grid(row=0, column=0, sticky="ew")
        self.pair_note = ctk.CTkLabel(self.pair_frame, text="", text_color=MUTED,
                                      anchor="w", justify="left", wraplength=850, font=font(12))
        self.pair_note.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.pair_mode = ctk.CTkSegmentedButton(self.pair_frame, values=["Working copy", "Original file"],
                                                command=self._duplicate_selected, font=font(13))
        self.pair_mode.set("Working copy")
        self.pair_mode.grid(row=2, column=0, sticky="w", pady=(0, 12))
        self.duplicate_values = ttk.Treeview(self.pair_frame, columns=("column", "kept", "removed"),
                                             show="headings", height=4, style="Monolith.Treeview")
        for name, title in (("column", "Column"), ("kept", "Keep"), ("removed", "Remove")):
            self.duplicate_values.heading(name, text=title)
            self.duplicate_values.column(name, width=220, minwidth=70, stretch=True, anchor="w")
        self.duplicate_values.grid(row=3, column=0, sticky="ew")
        detail_scroll = ttk.Scrollbar(self.pair_frame, orient="vertical", command=self.duplicate_values.yview,
                                       style="Monolith.Vertical.TScrollbar")
        detail_scroll.grid(row=3, column=1, sticky="ns")
        self.duplicate_values.configure(yscrollcommand=detail_scroll.set)
        self.pair_frame.grid_remove()

    def _build_review(self):
        self.review_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.review_frame.grid(row=3, column=0, sticky="ew", padx=(0, 12))
        self.review_frame.grid_columnconfigure(0, weight=1)
        self.comparison_text = ctk.CTkLabel(
            self.review_frame, text="Run the comparison using the same saved context, metadata, and weights.",
            text_color=INK, anchor="w", justify="left", wraplength=850, font=font(15, "semibold"),
        )
        self.comparison_text.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        actions = ctk.CTkFrame(self.review_frame, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.compare_button = self._button(actions, "Compare readiness", self._compare, primary=True, width=180)
        self.compare_button.pack(side="left")
        self.export_button = self._button(actions, "Export prepared dataset", self._export, width=190)
        self.export_button.pack(side="left", padx=8)
        self.review_mode = ctk.CTkSegmentedButton(
            actions, values=["Chart", "Table"], command=lambda _: self._draw_review(), font=font(13),
        )
        self.review_mode.set("Chart")
        self.review_mode.pack(side="right")
        self.review_chart_frame = ctk.CTkFrame(self.review_frame, fg_color=SURFACE, corner_radius=8)
        self.review_chart_frame.grid(row=2, column=0, sticky="ew")
        self.comparison_table = ttk.Treeview(
            self.review_frame, columns=("dimension", "original", "prepared"), show="headings",
            height=6, style="Monolith.Treeview",
        )
        for name, label in (("dimension", "Dimension"), ("original", "Original / 100"), ("prepared", "Prepared / 100")):
            self.comparison_table.heading(name, text=label, anchor="w" if name == "dimension" else "e")
            self.comparison_table.column(name, width=180, minwidth=80, anchor="w" if name == "dimension" else "e")
        self.comparison_table.grid(row=3, column=0, sticky="ew")
        self.history_button = self._button(self.review_frame, "View applied changes", self._toggle_history,
                                           kind="ghost", width=0)
        self.history_button.grid(row=4, column=0, sticky="w", pady=(16, 0))
        self.history_text = ctk.CTkLabel(self.review_frame, text="No preparation steps applied.", text_color=MUTED,
                                        anchor="w", justify="left", wraplength=850)
        self.history_text.grid(row=5, column=0, sticky="ew", pady=(8, 16))
        self.history_text.grid_remove()

    def set_dataset(self, df=None, info=None, source_path=None):
        self.session = PreparationSession(df) if df is not None else None
        self.info, self.source_path = info, source_path
        self.context = self.dimension_weights = self._metadata_snapshot = None
        self.column_lookup = {} if df is None else {str(name): name for name in df.columns}
        self.column_menu.configure(values=list(self.column_lookup))
        self.column_menu.set(next(iter(self.column_lookup), ""))
        self.step = 0
        self.step_nav.set(STEPS[0])
        self.before = None
        self._invalidate()
        self._configure_step()
        self._refresh()
        self._draw_chart()
        self.status.configure(text="Save the usage context to prepare this dataset." if df is not None
                              else "Load a dataset and save its context to start.", text_color=MUTED)

    def activate(self):
        if self.before is None and self.session and self.context and not self.busy and self.step != 3:
            self._inspect()

    def set_context(self, context, weights):
        evidence = self.session.original.attrs.get(METADATA_ATTR, {}) if self.session else {}
        if context == self.context and weights == self.dimension_weights and evidence == self._metadata_snapshot:
            return
        had_steps = bool(self.session and self.session.history)
        old_target = self.session.target if self.session else None
        self.context = context
        self.dimension_weights = dict(weights) if weights is not None else None
        self._metadata_snapshot = deepcopy(evidence)
        if self.session:
            self.session.set_target(context.target_column)
        self._invalidate()
        if old_target != context.target_column:
            self.before = None
        self._refresh()
        self._draw_chart()
        self._draw_review()
        self.status.configure(text="Target changed: the working copy was reset to protect the new target."
                              if had_steps and old_target != context.target_column else STEP_HINTS[self.step], text_color=MUTED)

    def evidence_changed(self):
        if self.context is not None:
            self.set_context(self.context, self.dimension_weights)

    def _choose_step(self, name):
        if self.busy:
            return
        pending = self.preview_change is not None and self.preview_change.affected_rows > 0
        self.step = STEPS.index(name)
        self.step_nav.set(name)
        self._discard_preview()
        self._configure_step()
        self.set_busy(False)
        if self.step == 3:
            self._draw_review()
        elif self.session and self.context:
            self._inspect()
        self.status.configure(text="Unapplied preview discarded. The working copy is unchanged. " + STEP_HINTS[self.step]
                              if pending else STEP_HINTS[self.step], text_color=MUTED)
        self.scroll._parent_canvas.yview_moveto(0)

    def _configure_step(self):
        review, editing = self.step == 3, self.step in (1, 2)
        for widget in (self.workspace, self.records_frame):
            widget.grid_remove() if review else widget.grid()
        self.review_frame.grid() if review else self.review_frame.grid_remove()
        for widget in (self.category_label, self.category_menu):
            widget.grid() if self.step == 1 else widget.grid_remove()
        for widget in (self.method_label, self.method_menu, self.details_button):
            widget.grid() if editing else widget.grid_remove()
        self.help_label.grid() if editing and self.details_open else self.help_label.grid_remove()
        category = "Normalization" if self.step == 2 else self.clean_category
        self.category_menu.set(category)
        methods = list(ACTIONS[category])
        self.method_menu.configure(values=methods)
        self.method_menu.set(methods[0])
        self.help_label.configure(text=HELP[category])
        self.chart_view.set("Box plot" if self.step == 1 and category == "Outliers" else
                            "Missing values" if self.step == 1 and category == "Missing values" else "Distribution")
        self.back_button.configure(state="normal" if self.step else "disabled")
        if review:
            self.next_button.grid_remove()
        else:
            self.next_button.grid()
            self.next_button.grid_configure(column=3 if self.step == 0 else 2)
            self.next_button.configure(text=("Continue to clean", "Continue to normalize", "Continue to compare")[self.step])
            self._emphasize(self.next_button, self.step == 0)

    def _next_step(self):
        if self.step < 3:
            self._choose_step(STEPS[self.step + 1])

    def _previous_step(self):
        if self.step:
            self._choose_step(STEPS[self.step - 1])

    def _choose_category(self, category):
        if self.busy:
            return
        self.clean_category = category if category != "Normalization" else self.clean_category
        self.step = 2 if category == "Normalization" else 1
        self.step_nav.set(STEPS[self.step])
        self._configure_step()
        self._selection_changed()

    def _toggle_details(self):
        self.details_open = not self.details_open
        self.help_label.grid() if self.details_open else self.help_label.grid_remove()
        self.details_button.configure(text="Hide method details" if self.details_open else "Method details")

    def _toggle_history(self):
        self.history_open = not self.history_open
        self.history_text.grid() if self.history_open else self.history_text.grid_remove()
        self.history_button.configure(text="Hide applied changes" if self.history_open else "View applied changes")

    def set_busy(self, busy):
        self.busy = busy
        ready = self.session is not None and self.context is not None and not busy
        editing = ready and self.step in (1, 2)
        for widget in (self.step_nav, self.inspect_button, self.chart_view, self.review_mode):
            widget.configure(state="normal" if ready else "disabled")
        self.category_menu.configure(state="normal" if ready and self.step == 1 else "disabled")
        self.method_menu.configure(state="normal" if editing else "disabled")
        self.column_menu.configure(state="readonly" if ready and (self.step == 0 or self.category_menu.get() != "Duplicates") else "disabled")
        can_preview = editing and (self.category_menu.get() == "Duplicates" or self._column() != self.context.target_column)
        self.preview_button.configure(state="normal" if can_preview else "disabled")
        pending = self.preview_change is not None and self.preview_change.affected_rows > 0
        self.apply_button.configure(state="normal" if editing and pending else "disabled")
        self.preview_button.grid() if self.step in (1, 2) and not pending else self.preview_button.grid_remove()
        self.apply_button.grid() if self.step in (1, 2) and pending else self.apply_button.grid_remove()
        has_steps = ready and bool(self.session.history)
        for widget in (self.undo_button, self.reset_button, self.compare_button, self.export_button):
            widget.configure(state="normal" if has_steps else "disabled")
        self.back_button.configure(state="normal" if ready and self.step else "disabled")
        self.next_button.configure(state="normal" if ready and not pending else "disabled")

    def _column(self):
        return self.column_lookup.get(self.column_menu.get())

    def _discard_preview(self):
        self.preview_change = self.after_data = None
        self._duplicate_examples = []
        self.pair_frame.grid_remove()
        if self.session:
            self.session.discard_preview()

    def _invalidate(self):
        self._discard_preview()
        self.comparison = None
        self.preview_label.configure(text="Flagged records")
        self._records([])
        self.comparison_text.configure(text="Compare both versions using the same saved context, metadata, and weights.")
        self.comparison_table.delete(*self.comparison_table.get_children())
        self._emphasize(self.compare_button, True)
        self._emphasize(self.export_button, False)

    def _refresh(self):
        history = self.session.history if self.session else []
        self.summary.configure(text=f"{self.info['file']} ({len(self.session.original):,} original rows, {len(self.session.working):,} working rows)"
                               if self.session else "Load a dataset to begin.")
        self.step_count.configure(text=f"{len(history)} applied changes")
        lines = [f"{index}. {step['action'].replace('_', ' ').capitalize()}"
                 f"{': ' + str(step['column']) if step['column'] is not None else ''}"
                 f" — {step['changed_cells']:,} cells changed, {step['removed_rows']:,} rows removed"
                 for index, step in enumerate(history, 1)]
        self.history_text.configure(text="\n".join(lines) or "No preparation steps applied.")
        self.set_busy(self.busy)

    def _selection_changed(self, _event=None):
        if not self.busy:
            self._discard_preview()
            self.set_busy(False)
            self._inspect()

    def _run(self, work, success, message, on_error=None):
        if self.busy or self.session is None or self.context is None:
            return
        self.status.configure(text=message, text_color=MUTED)
        self.run_background(lambda progress: work(), success, on_error or self._error)

    def _error(self, error):
        if self.preview_change is None:
            self.after_data = None
            self._draw_chart()
        self.status.configure(text=str(error), text_color=INK)

    def _inspect(self):
        if not self.session or not self.context:
            return
        self._discard_preview()
        column = self._column()
        self._run(lambda: self.session.inspect(column), self._inspected, "Inspecting working copy...")

    def _inspected(self, data):
        self.before, self.after_data = data, None
        self._draw_chart()
        if self.step == 1 and self.category_menu.get() == "Missing values":
            self.preview_label.configure(text=f"{data['column']}: {data['column_missing']:,} missing values (first eight)")
            self._records([(row["source_row"], row["value"], "Missing value") for row in data["missing_records"]])
        elif data["numeric"] and (self.step == 0 or self.category_menu.get() == "Outliers"):
            self.preview_label.configure(text=f"{data['column']}: {data['outliers']:,} potential outliers (first eight)")
            self._records([(row["source_row"], row["value"], "Potential outlier (IQR)") for row in data["records"]])
        else:
            self.preview_label.configure(text="Records and change preview")
            self._records([])
        message = STEP_HINTS[self.step]
        if self.step in (1, 2) and self._column() == self.context.target_column:
            message = "This is the saved target. Choose an input feature to enable preparation."
        self.status.configure(text=message, text_color=MUTED)

    def _preview(self):
        if not self.session or not self.context or self.step not in (1, 2) or self.busy:
            return
        category = self.category_menu.get()
        operation = Operation(ACTIONS[category][self.method_menu.get()], None if category == "Duplicates" else self._column())
        column = self._column()
        self._discard_preview()

        def work():
            change = self.session.preview(operation)
            return change, self.session.inspect(column), self.session.inspect(column, preview=True)

        self._run(work, self._previewed, "Preparing preview. No changes have been applied...")

    def _previewed(self, result):
        self.preview_change, self.before, self.after_data = result
        change = self.preview_change
        self._draw_chart()
        self.preview_label.configure(text=f"Preview: {change.affected_rows:,} affected rows, {change.changed_cells:,} cells changed, {change.removed_rows:,} rows removed")
        if change.operation.action == "duplicates":
            self._records([(row["source_row"], row["matched_source_row"], row["before"]) for row in change.examples],
                          duplicate_examples=change.examples)
        else:
            self._records([(row["source_row"], row["before"], row["after"]) for row in change.examples])
        self.status.configure(text="Review the chart and records, then apply to the working copy." if change.affected_rows
                              else "No values would change. Choose another method or continue to the next step.", text_color=MUTED)
        self.set_busy(False)
        if change.operation.action == "duplicates" and change.examples:
            self._duplicate_selected()
            self.scroll._parent_canvas.yview_moveto(1)

    def _apply(self):
        if self.session:
            self._change_copy(self.session.apply, "Applying preview...")

    def _undo(self):
        if self.session:
            self._change_copy(self.session.undo, "Rebuilding the previous working copy...")

    def _reset(self):
        if self.session:
            self._change_copy(self.session.reset, "Restoring original data...")

    def _change_copy(self, action, message):
        if not self.context:
            return
        column = self._column()

        def work():
            action()
            return self.session.inspect(column)

        def done(data):
            self._invalidate()
            self._refresh()
            self._inspected(data)
            self._draw_review()

        def failed(error):
            self.before = None
            self._invalidate()
            self._refresh()
            self._error(error)

        self._run(work, done, message, on_error=failed)

    def _compare(self):
        self._run(lambda: self.session.compare(self.context, self.dimension_weights), self._compared,
                  "Evaluating both versions with the same context, metadata, and weights...")

    def _compared(self, comparison):
        self.comparison = comparison
        original, prepared = comparison["original"], comparison["prepared"]
        self.comparison_text.configure(text=f"Original: {original['score']:.2f} ({original['classification']})\nPrepared: {prepared['score']:.2f} ({prepared['classification']})")
        self.comparison_table.delete(*self.comparison_table.get_children())
        for old, new in zip(original["dimensions"], prepared["dimensions"]):
            self.comparison_table.insert("", "end", values=(old["dimension"],
                f"{old['score']:.2f}" if old["applicable"] else "Not applicable",
                f"{new['score']:.2f}" if new["applicable"] else "Not applicable"))
        self._emphasize(self.compare_button, False)
        self._emphasize(self.export_button, True)
        self._draw_review()
        self.status.configure(text="Review the changes alongside the scores. A higher score alone does not prove a treatment is appropriate.", text_color=MUTED)

    def _export(self):
        if self.busy or not self.session or not self.context:
            return
        path = filedialog.asksaveasfilename(title="Export prepared dataset", defaultextension=".csv",
                initialfile=f"{Path(self.info['file']).stem}_prepared.csv",
                filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx"), ("Parquet", "*.parquet")])
        if not path:
            return
        output = Path(path).resolve()
        if self.source_path and Path(self.source_path).resolve() in {
            output, output.with_name(f"{output.stem}_preparation.json")
        }:
            self._error("Choose a different filename to preserve the original dataset.")
            return
        self._run(lambda: self.session.export(output, source=self.info["file"], context=self.context, comparison=self.comparison),
                  lambda paths: self.status.configure(text=f"Saved {paths[0].name} and {paths[1].name}.", text_color=INK),
                  "Exporting the prepared dataset and change history...")

    def _records(self, rows, *, duplicate_examples=None):
        self._duplicate_examples = list(duplicate_examples or [])
        self.pair_frame.grid_remove()
        duplicate_mode = duplicate_examples is not None
        headings = ("Remove source row", "Keep source row", "Matching values") if duplicate_mode else (
            "Source row", "Current value", "Preview / finding")
        widths = (160, 160, 360) if duplicate_mode else (110, 260, 280)
        for name, title, width in zip(("row", "before", "after"), headings, widths):
            self.table.heading(name, text=title, anchor="w")
            self.table.column(name, width=width, minwidth=80, stretch=name == "after" if duplicate_mode else name != "row",
                              anchor="e" if name != "after" else "w")
        self.record_hint.configure(text=(
            f"Matched across all columns in the working copy. Source rows include the header as row 1. "
            f"Select a pair below to compare every column. Showing {len(rows)} of {self.preview_change.removed_rows:,} pairs."
            if duplicate_mode else "Source row numbers refer to the original table with its header on row 1, before any sorting in Excel."
        ))
        self.table.delete(*self.table.get_children())
        for index, row in enumerate(rows):
            self.table.insert("", "end", iid=str(index), values=row)
        if rows:
            self.table.grid()
            self.record_scroll.grid()
            self.record_empty.grid_remove()
        else:
            self.table.grid_remove()
            self.record_scroll.grid_remove()
            self.record_empty.grid()
        if duplicate_mode and rows:
            self.pair_mode.set("Working copy")
            self.table.selection_set("0")

    def _duplicate_selected(self, _event=None):
        selection = self.table.selection()
        if self.busy or not selection or not self._duplicate_examples or self.preview_change is None:
            return
        details = self.session.duplicate_details(int(selection[0]), original=self.pair_mode.get() == "Original file")
        kept, removed = details["kept_source_row"], details["removed_source_row"]
        self.pair_title.configure(text=f"Keep source row {kept}; remove its duplicate at source row {removed}")
        self.pair_note.configure(text=(
            f"Working positions: keep {details['kept_working_row']}, remove {details['removed_working_row']}. "
            + ("Original values may differ if earlier preparation made the records identical."
               if self.pair_mode.get() == "Original file" else
               f"All {len(details['columns'])} columns match in the current working copy.")
        ))
        self.duplicate_values.heading("kept", text=f"Keep: source row {kept}")
        self.duplicate_values.heading("removed", text=f"Remove: source row {removed}")
        self.duplicate_values.configure(height=min(6, max(1, len(details["columns"]))))
        self.duplicate_values.delete(*self.duplicate_values.get_children())
        for column in details["columns"]:
            self.duplicate_values.insert("", "end", values=(column["column"], column["kept"], column["removed"]))
        self.pair_frame.grid()

    def _draw_chart(self):
        if not self.before:
            if self.canvas:
                self.canvas.get_tk_widget().pack_forget()
                self.canvas.figure.clear()
            if not self.chart_placeholder.winfo_manager():
                self.chart_placeholder.pack(fill="both", expand=True, padx=16, pady=100)
            self.chart_note.configure(text="")
            return
        self.chart_placeholder.pack_forget()
        figure = preparation_figure(self.before, self.after_data, view=self.chart_view.get(),
                                     dark=ctk.get_appearance_mode() == "Dark",
                                     figure=self.canvas.figure if self.canvas else None)
        if self.canvas is None:
            self.canvas = FigureCanvasTkAgg(figure, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().configure(width=1, height=270)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        view = self.chart_view.get()
        note = self.before["note"]
        if view == "Missing values":
            note = "Up to 12 columns by current missing count; counts use all rows."
        elif view == "Filled / missing":
            note = "All rows in the selected feature, including missing values."
        elif view == "Category share":
            note = self.before["category_share_note"] or "All rows shown, including missing values; at most five categories."
        elif view == "Target balance":
            note = "Up to eight target categories per version; counts use all rows."
        self.chart_note.configure(text=note)

    def _draw_review(self):
        if self.review_mode.get() == "Table":
            self.review_chart_frame.grid_remove()
            self.comparison_table.grid()
            return
        self.comparison_table.grid_remove()
        self.review_chart_frame.grid()
        if self.step != 3:
            return
        figure = readiness_figure(self.comparison, dark=ctk.get_appearance_mode() == "Dark",
                                  figure=self.review_canvas.figure if self.review_canvas else None)
        if self.review_canvas is None:
            self.review_canvas = FigureCanvasTkAgg(figure, master=self.review_chart_frame)
        self.review_canvas.draw()
        self.review_canvas.get_tk_widget().configure(width=1, height=280)
        self.review_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _resize(self, event):
        width = self._reverse_widget_scaling(event.width)
        for label in (self.status, self.comparison_text, self.history_text, self.summary, self.preview_label, self.record_hint, self.pair_note):
            label.configure(wraplength=max(260, width - 80))
        self.chart_note.configure(wraplength=max(220, width - 330))


    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        if hasattr(self, "table"):
            self._draw_chart()
            self._draw_review()
