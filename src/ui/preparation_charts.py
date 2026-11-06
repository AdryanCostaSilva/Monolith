"""Focused charts for each preparation decision; figures never own Tk widgets."""

import textwrap

import numpy as np
from matplotlib.figure import Figure
from matplotlib.text import Text
from matplotlib.ticker import MaxNLocator

from src.ui.theme import FAMILY, colors


CHART_VIEWS = ("Distribution", "Box plot", "Missing values", "Filled / missing", "Category share", "Target balance")


def _figure(figure, palette, height=3.2):
    if figure is None:
        return Figure(figsize=(8, height), layout="constrained", facecolor=palette["surface"])
    figure.clear()
    figure.set_facecolor(palette["surface"])
    return figure


def _empty(ax, text, palette):
    ax.text(.5, .5, text, transform=ax.transAxes, ha="center", va="center",
            color=palette["muted"], wrap=True, fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])


def _finish(figure, palette):
    for ax in figure.axes:
        ax.set_facecolor(palette["surface"])
        ax.tick_params(colors=palette["muted"], labelsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["bottom", "left"]].set_color(palette["line_strong"])
        ax.set_axisbelow(True)
    for artist in figure.findobj(match=Text):
        artist.set_parse_math(False)
        artist.set_usetex(False)
        artist.set_fontfamily([FAMILY, "DejaVu Sans"])
    return figure


def _numeric(ax, data, view, color, palette, *, bins=24):
    values = np.asarray(data["values"], dtype=float)
    if not data["numeric"] or not len(values):
        _empty(ax, "Choose a numerical feature with finite values.", palette)
        return
    maximum = float(np.abs(values).max())
    scale = maximum if maximum > 1e100 or 0 < maximum < 1e-100 else 1.0
    if view == "Box plot":
        stats = dict(data["box"])
        for key in ("q1", "med", "q3", "whislo", "whishi"):
            stats[key] /= scale
        stats["fliers"] = [value / scale for value in stats["fliers"]]
        ax.bxp([stats], orientation="horizontal", patch_artist=True,
               boxprops={"facecolor": color, "edgecolor": palette["body"]},
               whiskerprops={"color": palette["body"]}, capprops={"color": palette["body"]},
               medianprops={"color": palette["surface"]},
               flierprops={"marker": "o", "markersize": 4, "markeredgecolor": palette["accent"], "markerfacecolor": palette["accent"]})
        ax.set_yticks([])
        ax.text(.02, .93, f"{data['outliers']:,} potential outliers", transform=ax.transAxes,
                color=palette["muted"], fontsize=9, va="top")
    else:
        counts, edges, bars = ax.hist(values / scale, bins=bins, color=color)
        for count, bar in zip(counts, bars):
            if count > 0:
                ax.annotate(f"{int(count):,}", (bar.get_x() + bar.get_width() / 2, count),
                            ha="center", xytext=(0, 4), textcoords="offset points",
                            color=palette["body"], fontsize=8)
        ax.set_ylabel("Sampled rows", color=palette["muted"], fontsize=9)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.margins(y=.18)
    ax.set_xlabel("Value" if scale == 1 else f"Value / {scale:.3g}", color=palette["muted"], fontsize=9)
    ax.grid(axis="x" if view == "Box plot" else "y", color=palette["line"], linewidth=.5)


def _bars(ax, data, key, color, palette):
    counts = data[key]
    labels = list(counts)[:12]
    if not labels or not any(counts[label] for label in labels):
        message = "No missing values." if key == "missing_columns" else (
            "Select a target in Context to see its counts." if key == "target" else "No category values to display.")
        _empty(ax, message, palette)
        return
    values = [counts[label] for label in labels]
    bars = ax.barh(range(len(labels)), values, color=color, height=.6)
    ax.set_yticks(range(len(labels)), [label[:40] for label in labels])
    ax.invert_yaxis()
    ax.bar_label(bars, labels=[f"{value:,}" for value in values], padding=5, color=palette["body"], fontsize=9)
    ax.set_xlim(0, max(values) * 1.28)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Rows", color=palette["muted"], fontsize=9)
    ax.grid(axis="x", color=palette["line"], linewidth=.5)


def _donut(ax, entries, palette):
    entries = [entry for entry in entries if entry["count"] > 0]
    total = sum(entry["count"] for entry in entries)
    if not total:
        _empty(ax, "No rows to display.", palette)
        return
    shades = [palette["context"], palette["accent"], palette["muted"], palette["line_strong"], palette["text_2"]]
    wedges, _ = ax.pie([entry["count"] for entry in entries], colors=shades[:len(entries)],
                      startangle=90, radius=.8,
                      wedgeprops={"width": .24, "edgecolor": palette["surface"], "linewidth": 2})
    anchors = []
    for wedge, entry in zip(wedges, entries):
        angle = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
        label = textwrap.fill(entry["label"][:28], 16)
        anchors.append((np.cos(angle), np.sin(angle), f"{label}\n{entry['count']:,} ({entry['count'] / total:.1%})"))
    # Space direct labels by side so tiny adjacent slices never stack their text.
    for side in (-1, 1):
        group = sorted((item for item in anchors if (1 if item[0] >= 0 else -1) == side),
                       key=lambda item: item[1], reverse=True)
        positions = np.linspace(.75, -.75, len(group)) if len(group) > 1 else [0]
        for (x, y, label), position in zip(group, positions):
            ax.annotate(label, xy=(.8 * x, .8 * y), xytext=(side * 1.05, position),
                        ha="left" if side == 1 else "right", va="center", fontsize=9,
                        color=palette["body"], arrowprops={"arrowstyle": "-", "color": palette["muted"], "lw": .7})
    ax.text(0, 0, f"{total:,}\nrows", ha="center", va="center", color=palette["ink"], fontsize=12)
    ax.set_xlim(-1.9, 1.9)
    ax.set_ylim(-1.1, 1.1)
    ax.set_aspect("equal")


def preparation_figure(before, after=None, *, view="Distribution", dark=False, figure=None):
    palette = colors(dark)
    figure = _figure(figure, palette)
    versions = [("Current", before)] + ([("Preview", after)] if after else [])
    for index, (label, data) in enumerate(versions, 1):
        ax = figure.add_subplot(1, len(versions), index)
        color = palette["accent"] if after and index == 2 else palette["context"]
        ax.set_title(label, color=palette["ink"], fontsize=11, loc="left")
        if view == "Box plot" or (view == "Distribution" and data["numeric"]):
            _numeric(ax, data, view, color, palette, bins=12 if after else 24)
        elif view == "Filled / missing":
            _donut(ax, [{"label": "Filled", "count": data["rows"] - data["column_missing"]},
                        {"label": "Missing", "count": data["column_missing"]}], palette)
        elif view == "Category share":
            if data.get("category_share"):
                _donut(ax, data["category_share"], palette)
            else:
                _empty(ax, "Choose a feature with at most five categories.\nUse Distribution for more values.", palette)
        else:
            key = {"Missing values": "missing_columns", "Target balance": "target"}.get(view, "categories")
            _bars(ax, data, key, color, palette)
    return _finish(figure, palette)


def readiness_figure(comparison, *, dark=False, figure=None):
    palette = colors(dark)
    figure = _figure(figure, palette, height=3.8)
    ax = figure.add_subplot()
    if comparison is None:
        _empty(ax, "Run the comparison to see readiness by dimension.", palette)
        return _finish(figure, palette)
    pairs = [(old, new) for old, new in zip(comparison["original"]["dimensions"], comparison["prepared"]["dimensions"])
             if old["applicable"] and new["applicable"]]
    positions = np.arange(len(pairs))
    for offset, version, color in ((-.18, 0, palette["context"]), (.18, 1, palette["accent"])):
        values = [pair[version]["score"] for pair in pairs]
        bars = ax.barh(positions + offset, values, height=.3, color=color)
        name = "Original" if version == 0 else "Prepared"
        ax.bar_label(bars, labels=[f"{name} {value:.2f}" for value in values], padding=4,
                     color=palette["body"], fontsize=9)
    ax.set_yticks(positions, [old["dimension"] for old, _ in pairs])
    ax.invert_yaxis()
    ax.set_xlim(0, 132)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Score / 100", color=palette["muted"], fontsize=9)
    ax.grid(axis="x", color=palette["line"], linewidth=.5)
    return _finish(figure, palette)
