"""Matplotlib figures embedded as PNGs in a portable, offline HTML report."""

import base64
import math
import re
import textwrap
from html import escape
from io import BytesIO

import numpy as np
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter, MaxNLocator


BLUE = "#4263d8"
TEAL = "#12816a"
INK = "#243247"
MAX_HISTOGRAMS = 6
MAX_CATEGORIES = 4
MAX_CORRELATIONS = 12


def _figure(width=4.8, height=3.5):
    figure = Figure(figsize=(width, height), layout="constrained", facecolor="white")
    FigureCanvasAgg(figure)
    ax = figure.add_subplot()
    ax.tick_params(colors=INK, labelsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["bottom", "left"]].set_color("#d9e1ec")
    ax.set_axisbelow(True)
    return figure, ax


def _image(figure, alt):
    # Dataset labels are literal text, including dollar signs or TeX-like strings.
    for artist in figure.findobj(match=Text):
        artist.set_parse_math(False)
        artist.set_usetex(False)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=140, metadata={"Software": "Monolith"})
    payload = base64.b64encode(output.getvalue()).decode("ascii")
    width, height = (round(size * 140) for size in figure.get_size_inches())
    return (f'<img src="data:image/png;base64,{payload}" alt="{escape(alt)}" '
            f'width="{width}" height="{height}">')


def _short(value, length=46):
    value = str(value)
    return value if len(value) <= length else value[:length - 1] + "…"


def _format(value):
    return f"{value:,.4g}"


def _data_table(headers, rows):
    return (
        '<details class="plot-data"><summary>View plot data</summary><div class="plot-scroll">'
        '<table><thead><tr>' + "".join(f"<th>{escape(str(item))}</th>" for item in headers)
        + '</tr></thead><tbody>' + "".join(
            '<tr>' + "".join(f"<td>{escape(str(value))}</td>" for value in row) + '</tr>'
            for row in rows
        ) + '</tbody></table></div></details>'
    )


def _card(title, description, figure, data="", *, wide=False):
    return (
        f'<figure class="plot-card{" plot-wide" if wide else ""}">'
        f'<figcaption><h4>{escape(str(title))}</h4><p>{escape(description)}</p></figcaption>'
        f'<div class="plot-scroll">{_image(figure, description)}</div>{data}</figure>'
    )


def _ordered(names, context):
    preferred = [context.get("target_column"), *context.get("important_columns", [])]
    return list(dict.fromkeys(name for name in [*preferred, *names] if name in names))


def _is_identifier(name):
    return bool(re.search(r"(^id$|_id$|^id_)", str(name), re.IGNORECASE))


def _numeric_plots(report):
    profile = report["profile"]
    columns = profile.get("columns", {})
    histograms = profile.get("visualizations", {}).get("histograms", {})
    candidates = [name for name, column in columns.items()
                  if column.get("statistics") and column.get("unique_count", 0) > 1
                  and not _is_identifier(name)]
    names = _ordered(candidates, report["context"])[:MAX_HISTOGRAMS]
    cards = []
    for name in names:
        stats = columns[name]["statistics"]
        figure, ax = _figure()
        histogram = histograms.get(name)
        if histogram and histogram["finite_count"]:
            edges = np.asarray(histogram["edges"])
            # Large magnitudes remain readable without overflowing axis calculations.
            magnitude = max(float(np.abs(edges).max()), 1.0)
            scale = magnitude if magnitude > 1e100 else 1.0
            ax.stairs(histogram["counts"], edges / scale, fill=True, color=BLUE, alpha=.85)
            ax.set_xlabel("Value" if scale == 1 else f"Value × {_format(scale)}", color=INK)
            positive = [count for count in histogram["counts"] if count > 0]
            log_counts = max(positive) / min(positive) >= 100
            if log_counts:
                ax.set_yscale("log")
                ax.set_ylim(.8, max(positive) * 1.4)
                ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
            else:
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.set_ylabel("Rows in plot sample" + (" (log scale)" if log_counts else ""), color=INK)
            ax.grid(axis="y", alpha=.18)
            description = (
                f'Distribution of {name}: {histogram["finite_count"]:,} finite sampled values. '
                'Taller bars show more frequent ranges. Missing and infinite values are excluded.'
            )
            if log_counts:
                description += ' A logarithmic row scale makes rare ranges visible; empty bins are omitted.'
            quartiles = [stats.get(key) for key in ("25%", "50%", "75%")]
            if all(isinstance(value, (float, int)) and math.isfinite(value) for value in quartiles):
                q1, median, q3 = quartiles
                description += (f' Full-dataset median: {_format(median)}; '
                                f'middle 50%: {_format(q1)} to {_format(q3)}.')
            data = _data_table(
                ["Range start", "Range end", "Rows"],
                [(_format(low), _format(high), f"{count:,}") for low, high, count in
                 zip(histogram["edges"][:-1], histogram["edges"][1:], histogram["counts"])],
            )
        else:
            # Old JSON reports contain quartiles, but cannot supply histogram bin counts.
            points = [stats.get(key) for key in ("min", "25%", "50%", "75%", "max")]
            if not all(isinstance(value, (float, int)) and math.isfinite(value) for value in points):
                continue
            low, q1, median, q3, high = points
            ax.bxp([{"whislo": low, "q1": q1, "med": median, "q3": q3, "whishi": high}],
                   orientation="horizontal", showfliers=False, patch_artist=True,
                   boxprops={"facecolor": "#dce4ff", "edgecolor": BLUE},
                   medianprops={"color": TEAL, "linewidth": 2})
            ax.set_yticks([])
            ax.set_xlabel("Value", color=INK)
            ax.grid(axis="x", alpha=.18)
            description = (f"Range and quartiles of {name}. The box contains the middle 50%; "
                           "the green line is the median. Whiskers show minimum and maximum.")
            data = _data_table(["Minimum", "25%", "Median", "75%", "Maximum"],
                               [[_format(value) for value in points]])
        cards.append(_card(name, description, figure, data))
    title = "Numeric distributions" if histograms else "Numeric ranges and quartiles"
    return (
        f'<h3>{title}</h3><p class="chart-note">Showing up to {MAX_HISTOGRAMS} varying numeric '
        'columns, with the target and important columns first. Each plot has its own value scale.</p>'
        f'<div class="plot-grid">{"".join(cards)}</div>'
    ) if cards else '<p class="chart-empty">No varying numeric columns available to plot.</p>'


def _category_plots(report):
    columns = report["profile"].get("columns", {})
    rows = report["profile"]["dataset"].get("rows", 0)
    candidates = [
        name for name, column in columns.items()
        if column.get("top_values") and 1 < column.get("unique_count", 0) <= max(rows * .8, 2)
        and not _is_identifier(name)
        and not any(isinstance(item["value"], (dict, list)) for item in column["top_values"])
    ]
    cards = []
    for name in _ordered(candidates, report["context"])[:MAX_CATEGORIES]:
        column = columns[name]
        values = [item for item in column["top_values"] if item["count"] > 0]
        if not values:
            continue
        labels = [str(item["value"]) for item in values]
        counts = [item["count"] for item in values]
        figure, ax = _figure(height=3.8)
        bars = ax.barh(range(len(values)), counts, color=TEAL, height=.65)
        ax.set_yticks(range(len(values)), [textwrap.fill(_short(label), 22) for label in labels])
        ax.invert_yaxis()
        ax.bar_label(bars, labels=[f"{count:,}" for count in counts], padding=5, fontsize=9)
        ax.set_xlim(0, max(counts) * 1.3)
        ax.set_xlabel("Rows in the full dataset", color=INK)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
        ax.grid(axis="x", alpha=.18)
        description = (f'The {len(values)} most frequent values of {name}, out of '
                       f'{column["unique_count"]:,} distinct values. Counts use the full dataset; '
                       'missing values and remaining categories are not shown.')
        data = _data_table(["Value", "Rows"], zip(labels, [f"{count:,}" for count in counts]))
        cards.append(_card(name, description, figure, data))
    return (
        '<h3>Common categories</h3><p class="chart-note">Compare category frequencies to spot '
        'dominant groups and uneven representation. Identifier and nested columns are omitted.</p>'
        f'<div class="plot-grid">{"".join(cards)}</div>'
    ) if cards else ""


def _correlation_plot(report):
    source = report["profile"].get("visualizations", {}).get("correlation", {})
    available = [name for name in source.get("columns", []) if not _is_identifier(name)]
    names = _ordered(available, report["context"])[:MAX_CORRELATIONS]
    if len(names) < 2:
        return '<p class="chart-note">A correlation heatmap needs at least two varying numeric columns with overlapping values.</p>'
    indices = [source["columns"].index(name) for name in names]
    matrix = np.asarray(source["values"], dtype=float)[np.ix_(indices, indices)]
    pairs = np.asarray(source["pair_counts"])[np.ix_(indices, indices)]
    candidates = [(abs(matrix[i, j]), i, j) for i in range(len(names)) for j in range(i)
                  if np.isfinite(matrix[i, j])]
    if not candidates:
        return '<p class="chart-note">There are too few overlapping finite values to estimate numeric correlations.</p>'
    figure, ax = _figure(width=10.5, height=max(5.5, len(names) * .58 + 1.5))
    cmap = colormaps["RdBu_r"].with_extremes(bad="#e8edf5")
    plot = ax.imshow(np.ma.masked_invalid(matrix), vmin=-1, vmax=1, cmap=cmap)
    labels = [_short(name, 28) for name in names]
    ax.set_xticks(range(len(names)), labels, rotation=45, ha="right", rotation_mode="anchor")
    ax.set_yticks(range(len(names)), labels)
    for i in range(len(names)):
        for j in range(len(names)):
            value = matrix[i, j]
            ax.text(j, i, f"{value:.2f}" if np.isfinite(value) else "—", ha="center", va="center",
                    fontsize=8, color="white" if abs(value) > .65 else INK)
    figure.colorbar(plot, ax=ax, shrink=.8, label="Pearson correlation (r)")
    _, i, j = max(candidates)
    description = (
        f'Strongest displayed relationship: {names[i]} and {names[j]} '
        f'(r = {matrix[i, j]:.2f}, {pairs[i, j]:,} paired sample rows). '
        'Red means values tend to rise together; blue means they move in opposite directions. '
        'Gray cells are undefined. Correlation does not establish causation.'
    )
    data = _data_table(
        ["Column A", "Column B", "Pearson r", "Paired sample rows"],
        [(names[i], names[j], f"{matrix[i, j]:.4f}" if np.isfinite(matrix[i, j]) else "Undefined",
          f"{pairs[i, j]:,}") for i in range(len(names)) for j in range(i)],
    )
    return (
        '<h3>Numeric relationships</h3><p class="chart-note">'
        f'Up to {MAX_CORRELATIONS} varying numeric columns, prioritizing the target and important columns. '
        'Each coefficient uses rows where both values are finite, with at least three paired rows.</p>'
        + _card("Correlation heatmap", description, figure, data, wide=True)
    )


def dataset_plots_html(report):
    if not report["profile"].get("columns"):
        return ""
    visualizations = report["profile"].get("visualizations", {})
    if visualizations:
        sampled, total = visualizations["sample_rows"], visualizations["total_rows"]
        note = (f"Numeric histograms and correlations use a reproducible random sample of {sampled:,} "
                f"of {total:,} rows." if sampled < total else
                f"Numeric histograms and correlations use all {total:,} rows.")
        if visualizations["numeric_columns_total"] > len(visualizations["numeric_columns_profiled"]):
            note += f' Numeric plots cover the first {len(visualizations["numeric_columns_profiled"])} numeric columns.'
    else:
        note = ("This saved report contains numeric quartiles and category counts. "
                "Re-evaluate the dataset to also include histograms and correlations.")
    return (
        '<section aria-labelledby="exploration-heading"><h2 id="exploration-heading">Dataset exploration</h2>'
        f'<p>{escape(note)} Category counts and numeric summary statistics use the full dataset.</p>'
        f'{_numeric_plots(report)}{_correlation_plot(report)}{_category_plots(report)}</section>'
    )
