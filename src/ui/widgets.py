"""Small shared widgets and the one animation helper. Motion only answers an action."""

import sys
import time
import tkinter as tk

import customtkinter as ctk

from src.ui.theme import (
    ACCENT, BODY, CONTROL_FILL, CONTROL_HOVER, DISABLED, INK, LINE, MUTED, ON_ACCENT, SURFACE_3, font,
)


FRAME_MS = 16


def _motion_enabled():
    """Follow the Windows 'Show animations' setting; other platforms keep motion on."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        enabled = ctypes.c_bool(True)
        # SPI_GETCLIENTAREAANIMATION
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except (AttributeError, OSError):
        pass
    return True


MOTION = _motion_enabled()


def ease_out(t):
    return 1 - (1 - t) ** 3


def animate(widget, name, duration, step):
    """Call step(progress) with eased progress up to 1.0; a new call with the same name replaces the old."""
    jobs = widget.__dict__.setdefault("_monolith_tweens", {})
    job = jobs.pop(name, None)
    if job is not None:
        widget.after_cancel(job)
    if not MOTION or duration <= 0:
        step(1.0)
        return
    start = []

    def frame():
        jobs.pop(name, None)
        # The clock starts at the first idle frame, after any layout work that came with the change.
        if not start:
            start.append(time.perf_counter())
        t = min(1.0, (time.perf_counter() - start[0]) * 1000 / duration)
        try:
            step(ease_out(t))
            if t < 1:
                jobs[name] = widget.after(FRAME_MS, frame)
        except tk.TclError:
            pass  # the widget was destroyed mid-animation

    def begin():
        # A timer queued from idle fires only after pending redraws, so a heavy screen paints first.
        try:
            jobs[name] = widget.after(FRAME_MS, frame)
        except tk.TclError:
            jobs.pop(name, None)

    jobs[name] = widget.after_idle(begin)


def mix(widget, first, second, t):
    """Blend two Tk colors; t=0 gives first, t=1 gives second."""
    a = [value // 257 for value in widget.winfo_rgb(first)]
    b = [value // 257 for value in widget.winfo_rgb(second)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class Button(ctk.CTkButton):
    """CTkButton whose hover color eases in over 120ms instead of snapping."""

    _shown = None

    def _rest_color(self):
        if self._fg_color == "transparent":
            return self._bg_color
        # A disabled primary keeps no ink fill, so it never reads as the action to take.
        return CONTROL_FILL if self._state == tk.DISABLED else self._fg_color

    def _fade(self, role):
        start = self._shown or self._apply_appearance_mode(self._rest_color())

        def step(t):
            target = self._hover_color if role == "hover" and self._hover_color else self._rest_color()
            color = mix(self, start, self._apply_appearance_mode(target), t)
            self._shown = color
            self._canvas.itemconfig("inner_parts", outline=color, fill=color)
            if self._text_label is not None:
                self._text_label.configure(bg=color)

        animate(self, "hover", 120, step)

    def _on_enter(self, event=None):
        self._mouse_inside = True
        if self._hover is True and self._state == "normal":
            self._fade("hover")

    def _on_leave(self, event=None):
        self._mouse_inside = False
        self._click_animation_running = False
        self._fade("rest")

    def _draw(self, no_color_updates=False):
        jobs = self.__dict__.get("_monolith_tweens", {})
        if "hover" in jobs:
            self.after_cancel(jobs.pop("hover"))
        self._shown = None
        super()._draw(no_color_updates)
        if self._state == tk.DISABLED and self._fg_color != "transparent":
            color = self._apply_appearance_mode(CONTROL_FILL)
            self._canvas.itemconfig("inner_parts", outline=color, fill=color)
            if self._text_label is not None:
                self._text_label.configure(bg=color)


BUTTON_KINDS = {
    "primary": {"fg_color": ACCENT, "text_color": ON_ACCENT, "hover_color": ("#3A3A3A", "#FFFFFF")},
    "secondary": {"fg_color": CONTROL_FILL, "text_color": INK, "hover_color": CONTROL_HOVER},
    "ghost": {"fg_color": "transparent", "text_color": INK, "hover_color": CONTROL_FILL},
}


def button(parent, text, command, kind="secondary", width=120, height=32, **kwargs):
    return Button(parent, text=text, command=command, width=width, height=height, corner_radius=6,
                  border_width=0, font=font(13), **BUTTON_KINDS[kind], **kwargs)


def emphasize(widget, primary):
    """Swap a button between the one primary action and a quiet secondary one."""
    widget.configure(**BUTTON_KINDS["primary" if primary else "secondary"])


class CheckBox(ctk.CTkCheckBox):
    """Hover strengthens the box edge instead of filling it, so it never looks checked."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("checkbox_width", 18)
        kwargs.setdefault("checkbox_height", 18)
        kwargs.setdefault("font", font(13))
        super().__init__(master, **kwargs)

    def _on_enter(self, event=0):
        if self._hover is True and self._state == tk.NORMAL and self._check_state is not True:
            color = self._apply_appearance_mode(INK)
            self._canvas.itemconfig("border_parts", fill=color, outline=color)


class NavBar(ctk.CTkFrame):
    """Text tabs with an underline that slides to the chosen tab.

    Mirrors the CTkSegmentedButton calls the pages use: set, get and configure(state=...).
    """

    def __init__(self, master, values, command=None, *, gap=24, baseline=False):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._command = command
        self._state = "normal"
        self._current = None
        self._labels = {}
        for column, value in enumerate(values):
            label = ctk.CTkLabel(self, text=value, font=font(13), text_color=MUTED, height=34, cursor="hand2")
            label.grid(row=0, column=column, padx=(0 if column == 0 else gap, 0), pady=(0, 2), sticky="s")
            label.bind("<Button-1>", lambda _event, value=value: self._clicked(value))
            label.bind("<Enter>", lambda _event, value=value: self._hover(value, True))
            label.bind("<Leave>", lambda _event, value=value: self._hover(value, False))
            self._labels[value] = label
        self.grid_columnconfigure(len(values), weight=1)
        self._baseline = None
        if baseline:
            self._baseline = tk.Frame(self, height=1, bd=0, highlightthickness=0)
            self._baseline.place(x=0, rely=1.0, relwidth=1.0, anchor="sw", height=1)
        self._indicator = tk.Frame(self, height=2, bd=0, highlightthickness=0)
        self._paint_lines()
        self._move_job = None
        self.bind("<Configure>", self._schedule_snap, add="+")
        for label in self._labels.values():
            label.bind("<Configure>", self._schedule_snap, add=True)

    def _schedule_snap(self, _event=None):
        """Re-seat the underline without motion once layout settles (first map, resize)."""
        if self._move_job is None:
            self._move_job = self.after_idle(self._snap)

    def _snap(self):
        self._move_job = None
        if "underline" not in self.__dict__.get("_monolith_tweens", {}):
            self._move(animated=False)

    def _paint_lines(self):
        self._indicator.configure(bg=self._apply_appearance_mode(ACCENT if self._state == "normal" else DISABLED))
        if self._baseline is not None:
            self._baseline.configure(bg=self._apply_appearance_mode(LINE))

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        self._paint_lines()

    def _clicked(self, value):
        if self._state != "normal" or value == self._current:
            return
        self.set(value)
        if self._command is not None:
            self._command(value)

    def _hover(self, value, inside):
        if self._state == "normal" and value != self._current:
            self._labels[value].configure(text_color=BODY if inside else MUTED)

    def _paint(self):
        for value, label in self._labels.items():
            if self._state != "normal":
                color = DISABLED
            else:
                color = INK if value == self._current else MUTED
            label.configure(text_color=color, cursor="hand2" if self._state == "normal" else "arrow")
        self._paint_lines()

    def _move(self, animated=True):
        label = self._labels.get(self._current)
        if label is None or not label.winfo_ismapped():
            return
        info = self._indicator.place_info()
        start_x = int(info["x"]) if info else label.winfo_x()
        start_width = int(info["width"]) if info else label.winfo_width()

        def step(t):
            # Read the target every frame so a layout change mid-slide still lands on the label.
            target_x, target_width = label.winfo_x(), label.winfo_width()
            self._indicator.place(x=round(start_x + (target_x - start_x) * t), rely=1.0, anchor="sw",
                                  width=round(start_width + (target_width - start_width) * t), height=2)
            self._indicator.lift()

        animate(self, "underline", 200 if animated and info else 0, step)

    def set(self, value):
        self._current = value
        self._paint()
        self._move()

    def get(self):
        return self._current

    def configure(self, require_redraw=False, **kwargs):
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self._paint()
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        super().configure(require_redraw=require_redraw, **kwargs)


class Tabs(ctk.CTkFrame):
    """Pages switched by a NavBar that lives elsewhere (the header). Keeps the CTkTabview calls."""

    def __init__(self, master, nav_parent, values, command=None):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._command = command
        self._pages = {}
        # Pages share one cell and are raised, not re-gridded, so a switch never re-lays out a page.
        for value in values:
            page = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[value] = page
        self.nav = NavBar(nav_parent, values, command=self._clicked)
        self.set(values[0])

    def _clicked(self, value):
        self.set(value)
        if self._command is not None:
            self._command()

    def tab(self, name):
        return self._pages[name]

    def set(self, name):
        self._pages[name].tkraise()
        self.nav.set(name)

    def get(self):
        return self.nav.get()

    def configure(self, require_redraw=False, **kwargs):
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        super().configure(require_redraw=require_redraw, **kwargs)


class BusyLine(ctk.CTkFrame):
    """A 1px divider that runs a short ink segment while background work is in progress."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent", corner_radius=0, height=2)
        self._line = tk.Frame(self, height=1, bd=0, highlightthickness=0)
        self._line.place(x=0, rely=1.0, relwidth=1.0, anchor="sw", height=1)
        self._segment = tk.Frame(self, height=2, bd=0, highlightthickness=0)
        self._job = None
        self._position = 0.0
        self._paint()

    def _paint(self):
        self._line.configure(bg=self._apply_appearance_mode(LINE))
        self._segment.configure(bg=self._apply_appearance_mode(ACCENT))

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        self._paint()

    def start(self):
        if self._job is None:
            self._position = 0.0
            self._tick()

    def _tick(self):
        # A loop the person started, so linear motion is fine; it stops the moment the work does.
        self._position = (self._position + 0.012) % 1.0
        self._segment.place(relx=self._position * 1.25 - 0.25, rely=1.0, relwidth=0.25, anchor="sw", height=2)
        self._job = self.after(FRAME_MS, self._tick)

    def stop(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._segment.place_forget()


class LevelMeter(ctk.CTkFrame):
    """A row of short bars that shows a level in shape, not color."""

    def __init__(self, master, levels=4):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._bars = []
        for index in range(levels):
            bar = ctk.CTkFrame(self, width=22, height=4, corner_radius=2, fg_color=SURFACE_3)
            bar.grid(row=0, column=index, padx=(0 if index == 0 else 4, 0))
            self._bars.append(bar)

    def set(self, level):
        for index, bar in enumerate(self._bars):
            bar.configure(fg_color=ACCENT if index < level else SURFACE_3)
