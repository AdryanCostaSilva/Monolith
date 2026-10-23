import customtkinter as ctk


MUTED_TEXT = ("#6B7280", "#A0A6AF")


class DimensionCard(ctk.CTkFrame):
    def __init__(self, parent, dimension, default_weight, color, on_weight_change):
        super().__init__(
            parent,
            corner_radius=10,
            border_width=1,
            border_color=("#E1E5E9", "#3A3D42"),
            fg_color=("#FAFBFC", "#292B2F"),
        )
        self.default_weight = default_weight
        self.applicable = dimension["applicable"]
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=dimension["dimension"], text_color=MUTED_TEXT, anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
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
