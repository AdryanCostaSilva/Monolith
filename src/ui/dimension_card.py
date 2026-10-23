import tkinter as tk

import customtkinter as ctk


MUTED_TEXT = ("#6B7280", "#A0A6AF")
TOOLTIP_DELAY_MS = 350


def _mode_colors(colors_list):
    mode = ctk.get_appearance_mode()
    index = 1 if mode == "Dark" else 0
    return colors_list[index]


class _CardTooltip:
    """Tooltip based on plain-Tk widgets, whose <Enter>/<Leave> are reliable."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self.job = None
        self.hide_job = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._schedule_hide)
        widget.bind("<ButtonPress-1>", self._hide)

    def _schedule(self, _event=None):
        self._cancel_jobs()
        self.job = self.widget.after(TOOLTIP_DELAY_MS, self._show)

    def _cancel_jobs(self):
        for job in (self.job, self.hide_job):
            if job is not None:
                self.widget.after_cancel(job)
        self.job = self.hide_job = None

    def _schedule_hide(self, _event=None):
        self._cancel_jobs()
        self.hide_job = self.widget.after(150, self._hide)

    def _show(self):
        self.job = None
        if self.window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() - 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() - 2
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_attributes("-topmost", True)
        window.wm_geometry(f"+{x}+{y}")
        window.bind("<Enter>", self._on_tooltip_enter)
        window.bind("<Leave>", self._schedule_hide_from_window)
        window.bind("<ButtonPress-1>", self._hide_from_window)
        label = tk.Label(
            window,
            text=self.text,
            wraplength=280,
            justify="left",
            anchor="w",
            bg=_mode_colors(("#F0F4FA", "#33363B")),
            fg=_mode_colors(("#20262E", "#EFF1F4")),
            padx=10,
            pady=8,
        )
        label.pack()
        self.window = window

    def _on_tooltip_enter(self, _event=None):
        if self.hide_job is not None:
            self.widget.after_cancel(self.hide_job)
            self.hide_job = None

    def _schedule_hide_from_window(self, _event=None):
        if self.window is not None:
            self._schedule_hide()

    def _hide_from_window(self, _event=None):
        self._hide()

    def _hide(self, _event=None):
        self._cancel_jobs()
        if self.window is not None:
            window, self.window = self.window, None
            window.destroy()


class DimensionCard(ctk.CTkFrame):
    def __init__(self, parent, dimension, default_weight, color, on_weight_change, help_text=None):
        super().__init__(
            parent,
            corner_radius=10,
            border_width=1,
            border_color=("#E1E5E9", "#3A3D42"),
            fg_color=("#FAFBFC", "#292B2F"),
        )
        self.default_weight = default_weight
        self.applicable = dimension["applicable"]
        self.help_text = help_text
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=dimension["dimension"], text_color=MUTED_TEXT, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        self.info_button = None
        if help_text:
            tooltip_text = help_text
            if not self.applicable:
                tooltip_text = f"{help_text} Not used for this task."
            self.info_button = tk.Label(
                header,
                text="?",
                width=2,
                bd=0,
                bg=_mode_colors(("#E8EDF5", "#3A3E44")),
                fg=_mode_colors(("#3D5A80", "#B7C6D4")),
                font=("", 10, "bold"),
            )
            self.info_button.bind(
                "<Enter>",
                lambda _e: self.info_button.configure(
                    bg=_mode_colors(("#DCE4EF", "#4A4F56"))
                ),
            )
            self.info_button.bind(
                "<Leave>",
                lambda _e: self.info_button.configure(
                    bg=_mode_colors(("#E8EDF5", "#3A3E44"))
                ),
            )
            self.info_button.grid(row=0, column=1, sticky="e")
            self.tooltip = _CardTooltip(self.info_button, tooltip_text)
        score = dimension["score"]
        ctk.CTkLabel(
            self,
            text="N/A" if score is None else f"{score:.2f}",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=MUTED_TEXT if score is None else ("#20262E", "#EFF1F4"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 6))
        self.progress = ctk.CTkProgressBar(self, height=3, progress_color=color)
        self.progress.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.progress.set(0 if score is None else score / 100)

        self.controls = ctk.CTkFrame(self, fg_color="transparent")
        self.controls.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.controls.grid_columnconfigure(0, weight=1)
        self.slider = None
        if self.applicable:
            ctk.CTkLabel(
                self.controls, text="Weight", text_color=MUTED_TEXT, anchor="w"
            ).grid(row=0, column=0, sticky="w")
            self.weight_value = ctk.CTkLabel(self.controls, width=42, anchor="e")
            self.weight_value.grid(row=0, column=1, sticky="e")
            self.slider = ctk.CTkSlider(
                self.controls,
                from_=0,
                to=100,
                number_of_steps=1000,
                height=16,
                button_length=12,
                fg_color=("#DDE2E7", "#42464D"),
                progress_color=("#71869A", "#8197AA"),
                button_color=("#566F85", "#B1C1CE"),
                button_hover_color=("#425B71", "#DAE3EA"),
                command=on_weight_change,
            )
            self.slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 6))
            self.weight_hint = ctk.CTkLabel(
                self.controls,
                text="",
                text_color=MUTED_TEXT,
                font=ctk.CTkFont(size=11),
                anchor="w",
            )
            self.weight_hint.grid(row=2, column=0, columnspan=2, sticky="ew")
            self.update_weight(dimension, sync_slider=True)
        else:
            ctk.CTkLabel(
                self.controls,
                text="Not included in this task.",
                text_color=MUTED_TEXT,
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", pady=(18, 24))
        self.controls.grid_remove()

    def set_controls_visible(self, visible):
        if visible:
            self.controls.grid()
        else:
            self.controls.grid_remove()

    def update_weight(self, dimension, *, sync_slider=False):
        if not self.applicable:
            return
        weight = dimension["weight"]
        self.weight_value.configure(text=f"{weight:.1f}")
        share = (
            f"{dimension['weight_percentage']:.1f}% of score"
            if weight else "Not counted"
        )
        self.weight_hint.configure(text=f"Default {self.default_weight:g}  ·  {share}")
        if sync_slider:
            self.slider.set(weight)
