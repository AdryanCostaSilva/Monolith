"""Offline report charts built from HTML and inline SVG, with visible data labels."""

from html import escape

from src.config import SCORE_BANDS


def _number(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _band(score):
    return sum(score >= minimum for minimum, _ in SCORE_BANDS) - 1


def score_gauge(score):
    label = f"Overall readiness: {_number(score)} out of 100"
    return (
        f'<svg class="score-gauge band-{_band(score)}" viewBox="0 0 120 120" '
        f'role="img" aria-label="{escape(label)}">'
        f'<title>{escape(label)}</title>'
        '<circle class="gauge-track" cx="60" cy="60" r="50" />'
        '<circle class="gauge-fill" cx="60" cy="60" r="50" pathLength="100" '
        f'stroke-dasharray="{score} 100" transform="rotate(-90 60 60)" />'
        f'<text x="60" y="61" class="gauge-value">{_number(score)}</text>'
        '<text x="60" y="80" class="gauge-unit">out of 100</text></svg>'
    )


def _bar(label, value, display, *, color="accent"):
    # The text remains readable in print, without styles, and with assistive tools.
    width = min(100, max(0, value))
    return (
        '<div class="chart-row">'
        f'<div class="bar-label"><span>{escape(str(label))}</span>'
        f'<strong>{escape(display)}</strong></div>'
        '<div class="bar-track" aria-hidden="true">'
        f'<span class="bar-fill {color}" style="width: {width:.4f}%"></span>'
        '</div></div>'
    )


def _dimension_chart(dimensions):
    rows = []
    for item in dimensions:
        if item["applicable"]:
            score = item["score"]
            rows.append(_bar(item["dimension"], score, f"{_number(score)} / 100",
                             color=f"band-{_band(score)}"))
        else:
            rows.append(_bar(item["dimension"], 0, "Not applicable", color="inactive"))
    legend = "".join(
        f'<span><i class="band-{index}" aria-hidden="true"></i>{escape(label)}</span>'
        for index, (_, label) in enumerate(SCORE_BANDS)
    )
    return (
        '<article class="chart-card"><h3>Readiness by dimension</h3>'
        '<p class="chart-note">Scores use the same 0–100 scale; higher is better. '
        'Non-applicable dimensions are excluded from the overall score.</p>'
        f'{"".join(rows)}<div class="chart-legend">{legend}</div></article>'
    )


def _missing_chart(profile):
    columns = profile.get("columns", {})
    affected = sorted(
        ((name, item["missing_percentage"]) for name, item in columns.items()
         if item.get("missing_percentage", 0) > 0),
        key=lambda item: item[1], reverse=True,
    )
    if affected:
        content = "".join(
            _bar(name, percentage, f"{_number(percentage)}%", color="missing")
            for name, percentage in affected[:10]
        )
        note = (f"Showing {min(10, len(affected))} of {len(affected)} columns with missing "
                "values, highest first. Scale: 0–100% of rows; lower is better.")
    elif not profile.get("dataset", {}).get("rows"):
        content = '<p class="chart-empty">No rows to assess.</p>'
        note = "Missing-value rates need a non-empty dataset."
    elif columns:
        content = '<p class="chart-empty">No missing values in any column.</p>'
        note = f"All {len(columns):,} profiled columns have 0% missing values."
    else:
        content = '<p class="chart-empty">Column profiles are unavailable.</p>'
        note = "Re-export the report with column profiling data to see this chart."
    return (
        '<article class="chart-card"><h3>Missing values by column</h3>'
        f'<p class="chart-note">{note}</p>{content}</article>'
    )


def _class_chart(report):
    context = report["context"]
    target = context.get("target_column")
    if context.get("task_type") != "classification" or not target:
        return ""
    balance = next((item for item in report["result"]["dimensions"]
                    if item["dimension"] == "Class Balance"), {})
    distribution = balance.get("class_distribution")
    if distribution is None:
        # Older reports already contain full counts for low-cardinality text/bool targets.
        column = report["profile"].get("columns", {}).get(target, {})
        top = column.get("top_values", [])
        if not top or column.get("unique_count") != len(top):
            return (
                '<article class="chart-card"><h3>Target class distribution</h3>'
                '<p class="chart-empty">Class counts are unavailable in this saved report. '
                'Run the evaluation again to include this chart.</p></article>'
            )
        classes = [{"label": str(item["value"]), "count": item["count"]} for item in top]
        distribution = {
            "classes": classes, "other_count": 0,
            "missing_count": report["profile"]["dataset"]["rows"]
            - sum(item["count"] for item in classes),
        }
    classes = list(distribution["classes"])
    other = distribution["other_count"]
    total = sum(item["count"] for item in classes) + other
    rows = "".join(
        _bar(item["label"], item["count"] / total * 100,
             f'{item["count"]:,} ({_number(item["count"] / total * 100)}%)')
        for item in classes if item["count"] and total
    )
    if other and total:
        rows += _bar("Remaining classes (combined)", other / total * 100,
                     f"{other:,} ({_number(other / total * 100)}%)", color="inactive")
    return (
        '<article class="chart-card"><h3>Target class distribution</h3>'
        f'<p class="chart-note">Target: <strong>{escape(str(target))}</strong>. '
        f'Share of {total:,} non-missing labels on a 0–100% scale. '
        f'{distribution["missing_count"]:,} missing labels excluded. '
        'Up to eight classes shown individually; remaining classes are combined.</p>'
        f'{rows or "<p class=chart-empty>No non-missing target labels.</p>"}</article>'
    )


def charts_html(report):
    return (
        '<section aria-labelledby="charts-heading"><h2 id="charts-heading">Visual overview</h2>'
        '<div class="chart-grid">'
        f'{_dimension_chart(report["result"]["dimensions"])}'
        f'{_missing_chart(report["profile"])}{_class_chart(report)}'
        '</div></section>'
    )
