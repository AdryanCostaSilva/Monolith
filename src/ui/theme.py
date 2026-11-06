"""Monochrome design tokens shared by every screen.

Widgets never hold a hex value of their own: they use these roles. Each role is a
(light, dark) pair that CustomTkinter resolves for the current appearance mode.
"""

import sys
import tkinter as tk
import weakref
from tkinter import ttk

import customtkinter as ctk


# Surfaces step up in even shades: page, then cards, then wells and fills.
PAGE = ("#F5F5F5", "#0C0C0C")
SURFACE = ("#FFFFFF", "#161616")
SURFACE_2 = ("#FAFAFA", "#1C1C1C")
SURFACE_3 = ("#E8E8E8", "#2A2A2A")
CONTROL_FILL = ("#EBEBEB", "#1F1F1F")
CONTROL_HOVER = ("#E0E0E0", "#2A2A2A")
SCROLL = ("#DDDDDD", "#262626")
LINE = ("#E8E8E8", "#222222")
LINE_STRONG = ("#D6D6D6", "#333333")
CONTROL = ("#949494", "#646464")
# Text is a ladder of whites (dark) or inks (light): titles, body, labels, captions, off.
INK = ("#0F0F0F", "#FAFAFA")
BODY = ("#2E2E2E", "#D9D9D9")
TEXT_2 = ("#525252", "#ABABAB")
MUTED = ("#6E6E6E", "#8A8A8A")
DISABLED = ("#ABABAB", "#555555")
CONTEXT = ("#8C8C8C", "#6B6B6B")
ACCENT = ("#111111", "#EDEDED")
ACCENT_HOVER = ("#383838", "#FFFFFF")
ON_ACCENT = ("#FFFFFF", "#111111")

if sys.platform == "win32":
    FAMILY, STRONG_FAMILY, MONO_FAMILY = "Segoe UI", "Segoe UI Semibold", "Consolas"
elif sys.platform == "darwin":
    FAMILY = STRONG_FAMILY = "Helvetica Neue"
    MONO_FAMILY = "Menlo"
else:
    FAMILY = STRONG_FAMILY = "DejaVu Sans"
    MONO_FAMILY = "DejaVu Sans Mono"

ROLES = {
    "page": PAGE, "surface": SURFACE, "surface_2": SURFACE_2, "surface_3": SURFACE_3,
    "control_fill": CONTROL_FILL, "control_hover": CONTROL_HOVER, "line": LINE,
    "line_strong": LINE_STRONG, "control": CONTROL, "ink": INK, "body": BODY, "text_2": TEXT_2,
    "muted": MUTED, "disabled": DISABLED, "context": CONTEXT, "accent": ACCENT,
    "on_accent": ON_ACCENT, "scroll": SCROLL,
}


def colors(dark=False):
    """Resolve every role for one mode, for matplotlib and ttk which cannot take pairs."""
    index = int(dark)
    return {name: value[index] for name, value in ROLES.items()}


def is_dark():
    return ctk.get_appearance_mode() == "Dark"


def font(size=13, weight="normal"):
    """weight is normal, semibold (titles) or bold (one hero number per screen)."""
    if weight == "semibold" and STRONG_FAMILY != FAMILY:
        return ctk.CTkFont(family=STRONG_FAMILY, size=size)
    return ctk.CTkFont(family=FAMILY, size=size, weight="normal" if weight == "normal" else "bold")


def mono(size=12):
    return ctk.CTkFont(family=MONO_FAMILY, size=size)


def install():
    """Point CustomTkinter's defaults at the monochrome roles. Call before creating the root."""
    ctk.ThemeManager.load_theme("blue")
    theme = ctk.ThemeManager.theme
    theme["CTk"]["fg_color"] = PAGE
    theme["CTkToplevel"]["fg_color"] = PAGE
    theme["CTkFrame"].update(corner_radius=8, border_width=0, fg_color=SURFACE,
                             top_fg_color=SURFACE_2, border_color=LINE)
    theme["CTkButton"].update(corner_radius=6, border_width=0, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                              border_color=CONTROL, text_color=ON_ACCENT, text_color_disabled=DISABLED)
    # Body text is the softer white; titles and numbers ask for INK explicitly.
    theme["CTkLabel"].update(text_color=BODY)
    theme["CTkEntry"].update(corner_radius=6, border_width=1, fg_color=SURFACE, border_color=CONTROL,
                             text_color=INK, placeholder_text_color=MUTED)
    theme["CTkCheckBox"].update(corner_radius=4, border_width=1, fg_color=ACCENT, border_color=CONTROL,
                                hover_color=ACCENT_HOVER, checkmark_color=ON_ACCENT, text_color=BODY,
                                text_color_disabled=DISABLED)
    theme["CTkSwitch"].update(fg_color=SURFACE_3, progress_color=ACCENT, button_color=INK,
                              button_hover_color=TEXT_2, text_color=BODY, text_color_disabled=DISABLED)
    theme["CTkRadioButton"].update(fg_color=ACCENT, border_color=CONTROL, hover_color=ACCENT_HOVER,
                                   text_color=BODY, text_color_disabled=DISABLED)
    theme["CTkProgressBar"].update(fg_color=SURFACE_3, progress_color=ACCENT, border_color=LINE)
    theme["CTkSlider"].update(fg_color=SURFACE_3, progress_color=TEXT_2, button_color=INK,
                              button_hover_color=TEXT_2)
    theme["CTkOptionMenu"].update(corner_radius=6, fg_color=CONTROL_FILL, button_color=CONTROL_FILL,
                                  button_hover_color=CONTROL_HOVER, text_color=INK, text_color_disabled=DISABLED)
    theme["CTkComboBox"].update(corner_radius=6, border_width=1, fg_color=SURFACE, border_color=CONTROL,
                                button_color=CONTROL_FILL, button_hover_color=CONTROL_HOVER,
                                text_color=INK, text_color_disabled=DISABLED)
    # Scrollbars stay quiet until hovered.
    theme["CTkScrollbar"].update(fg_color="transparent", button_color=SCROLL, button_hover_color=CONTROL)
    theme["CTkSegmentedButton"].update(corner_radius=6, border_width=2, fg_color=CONTROL_FILL,
                                       selected_color=(SURFACE[0], "#333333"),
                                       selected_hover_color=(SURFACE[0], "#333333"),
                                       unselected_color=CONTROL_FILL, unselected_hover_color=CONTROL_HOVER,
                                       text_color=INK, text_color_disabled=DISABLED)
    # Read-only text areas are a plain shaded well; only inputs carry an edge.
    theme["CTkTextbox"].update(corner_radius=8, border_width=0, fg_color=SURFACE, border_color=LINE,
                               text_color=BODY, scrollbar_button_color=SCROLL,
                               scrollbar_button_hover_color=CONTROL)
    theme["CTkScrollableFrame"]["label_fg_color"] = PAGE
    theme["DropdownMenu"].update(fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=BODY)
    theme["CTkFont"].update(family=FAMILY, size=13, weight="normal")


_comboboxes = weakref.WeakSet()
_arrows = {}


def _paint_chevron(image, color):
    """Draw a small open chevron, like the CTk dropdowns, centered in a transparent image."""
    image.blank()
    width, height = image.width(), image.height()
    span = max(3, round(height * 0.22))
    stroke = max(1, round(height * 0.13))
    left, top = width // 2 - span, (height - span) // 2
    for step in range(span + 1):
        for offset in range(stroke + 1):
            for x in (left + step, left + 2 * span - step):
                image.put(color, (x, top + step + offset))


def _chevron_element(root, style, palette, scale):
    """ttk's built-in arrows always draw a 3D box, so the combobox arrow is an image element."""
    # Elements and images belong to one Tk interpreter, so a new root needs its own.
    if "Monolith.chevron" not in style.element_names():
        size = (round(28 * scale), round(18 * scale))
        _arrows["normal"] = tk.PhotoImage(master=root, width=size[0], height=size[1])
        _arrows["disabled"] = tk.PhotoImage(master=root, width=size[0], height=size[1])
        style.element_create("Monolith.chevron", "image", _arrows["normal"],
                             ("disabled", _arrows["disabled"]), sticky="")
    _paint_chevron(_arrows["normal"], palette["ink"])
    _paint_chevron(_arrows["disabled"], palette["disabled"])


class Combobox(ttk.Combobox):
    """A ttk combobox (it scrolls long column lists) inside a rounded CTk frame.

    The frame gives it the same filled, rounded shape as the CTk dropdowns; layout calls
    (grid) go to the frame, everything else is the plain ttk combobox.
    """

    def __init__(self, parent, **kwargs):
        self.frame = ctk.CTkFrame(parent, height=36, corner_radius=6, border_width=1,
                                  fg_color=CONTROL_FILL, border_color=CONTROL_FILL)
        self.frame.pack_propagate(False)
        super().__init__(self.frame, style="Monolith.TCombobox", **kwargs)
        inset = max(3, round(4 * ctk.ScalingTracker.get_widget_scaling(self.frame)))
        self.pack(fill="both", expand=True, padx=inset, pady=inset)
        self._hover = self._focus = False
        self.bind("<Enter>", lambda _event: self._edge(hover=True), add="+")
        self.bind("<Leave>", lambda _event: self._edge(hover=False), add="+")
        self.bind("<FocusIn>", lambda _event: self._edge(focus=True), add="+")
        self.bind("<FocusOut>", lambda _event: self._edge(focus=False), add="+")
        _comboboxes.add(self)

    def _edge(self, hover=None, focus=None):
        self._hover = self._hover if hover is None else hover
        self._focus = self._focus if focus is None else focus
        disabled = self.instate(["disabled"])
        fill = CONTROL_HOVER if self._hover and not disabled else CONTROL_FILL
        self.frame.configure(fg_color=fill, border_color=INK if self._focus and not disabled else fill)

    def grid(self, **kwargs):
        self.frame.grid(**kwargs)

    grid_configure = grid

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if "state" in kwargs:
            self._edge()
        return result

    config = configure


def combobox(parent, **kwargs):
    return Combobox(parent, **kwargs)


def style_ttk(root):
    """Restyle the few ttk widgets for the current mode; call again after a mode switch."""
    palette = colors(is_dark())
    try:
        scale = ctk.ScalingTracker.get_widget_scaling(root)
    except (AttributeError, KeyError):
        scale = 1.0
    # Negative sizes are pixels, so ttk text matches the CTk text beside it.
    body, small = (FAMILY, -round(13 * scale)), (FAMILY, -round(12 * scale))
    style = ttk.Style(root)
    if style.theme_use() != "clam":
        style.theme_use("clam")
    _chevron_element(root, style, palette, scale)
    style.layout("Monolith.TCombobox", [("Combobox.field", {"sticky": "nswe", "children": [
        ("Monolith.chevron", {"side": "right", "sticky": ""}),
        ("Combobox.padding", {"sticky": "nswe", "children": [("Combobox.textarea", {"sticky": "nswe"})]}),
    ]})])

    # The wrapping CTk frame draws the shape, so the ttk field is borderless and shares its fill.
    fill, hover = palette["control_fill"], palette["control_hover"]
    by_state = [("disabled", fill), ("active", hover), ("readonly", fill)]
    style.configure("Monolith.TCombobox", fieldbackground=fill, background=fill, foreground=palette["ink"],
                    insertcolor=palette["ink"], selectbackground=fill, selectforeground=palette["ink"],
                    lightcolor=fill, darkcolor=fill, bordercolor=fill,
                    padding=(round(4 * scale), round(2 * scale), 0, round(2 * scale)))
    style.map("Monolith.TCombobox", fieldbackground=by_state, background=by_state, selectbackground=by_state,
              lightcolor=by_state, darkcolor=by_state, bordercolor=by_state,
              foreground=[("disabled", palette["disabled"]), ("readonly", palette["ink"])],
              selectforeground=[("disabled", palette["disabled"]), ("readonly", palette["ink"])])
    for widget in list(_comboboxes):
        try:
            widget.configure(font=body)
            popdown = widget.tk.call("ttk::combobox::PopdownWindow", widget)
            widget.tk.call(f"{popdown}.f.l", "configure", "-background", palette["surface_2"],
                           "-foreground", palette["body"], "-selectbackground", palette["surface_3"],
                           "-selectforeground", palette["ink"], "-font", body,
                           "-borderwidth", 0, "-highlightthickness", 0, "-activestyle", "none")
            widget.tk.call(f"{popdown}.f", "configure", "-background", palette["line_strong"])
        except Exception:
            pass

    # Tables sit straight on the page: no box, a quiet header, selection by shade.
    page = {"lightcolor": palette["page"], "darkcolor": palette["page"], "bordercolor": palette["page"]}
    style.configure("Monolith.Treeview", background=palette["page"], fieldbackground=palette["page"],
                    foreground=palette["body"], rowheight=round(32 * scale), font=body, borderwidth=0, **page)
    style.map("Monolith.Treeview", background=[("selected", palette["surface_3"])],
              foreground=[("selected", palette["ink"])])
    style.configure("Monolith.Treeview.Heading", background=palette["page"], foreground=palette["muted"],
                    relief="flat", font=small, borderwidth=0,
                    padding=(round(2 * scale), round(4 * scale), round(2 * scale), round(8 * scale)), **page)
    style.map("Monolith.Treeview.Heading", background=[("active", palette["page"])],
              foreground=[("active", palette["text_2"])])

    style.layout("Monolith.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Monolith.Vertical.TScrollbar", troughcolor=palette["page"], background=palette["scroll"],
                    bordercolor=palette["page"], lightcolor=palette["scroll"],
                    darkcolor=palette["scroll"], gripcount=0, arrowsize=round(8 * scale))
    style.map("Monolith.Vertical.TScrollbar", background=[("active", palette["control"])])
