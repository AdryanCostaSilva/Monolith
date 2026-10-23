import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from html import escape
from pathlib import Path

from src.reporting.charts import charts_html, score_gauge
from src.reporting.dataset_plots import dataset_plots_html


def generate_report(info, profile, context, result):
    if is_dataclass(context):
        context = asdict(context)
    elif isinstance(context, dict):
        context = deepcopy(context)
    else:
        raise TypeError("context must be a dataclass or dictionary")

    return {
        "dataset": deepcopy(info),
        "profile": deepcopy(profile),
        "context": context,
        "result": deepcopy(result),
    }


def export_json(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _table(mapping):
    rows = []
    for name, value in mapping.items():
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value) or "None"
        rows.append(f"<tr><th>{escape(str(name))}</th><td>{escape(str(value))}</td></tr>")
    return f"<table>{''.join(rows)}</table>"


def _list(items):
    if not items:
        return "<p>None</p>"
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def _dimension_html(dimension):
    score = dimension["score"] if dimension["applicable"] else "Not applicable"
    indicator_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['name']))}</td>"
        f"<td>{escape(str(item['value']))}</td>"
        f"<td>{escape(str(item['weight']))}</td>"
        "</tr>"
        for item in dimension["indicators"]
    )
    indicators = (
        "<table><thead><tr><th>Indicator</th><th>Value</th><th>Weight</th></tr></thead>"
        f"<tbody>{indicator_rows}</tbody></table>"
        if indicator_rows
        else "<p>Not applicable</p>"
    )
    return (
        "<section>"
        f"<h2>{escape(str(dimension['dimension']))}: {escape(str(score))}</h2>"
        "<h3>Indicators</h3>"
        f"{indicators}"
        "<h3>Problems</h3>"
        f"{_list(dimension['problems'])}"
        "<h3>Recommendations</h3>"
        f"{_list(dimension['recommendations'])}"
        "</section>"
    )


def _render_html(report):
    context = report["context"]
    context_summary = {
        key: value
        for key, value in context.items()
        if key not in {"documentation", "provenance"}
    }
    result = report["result"]
    dimensions = "".join(_dimension_html(item) for item in result["dimensions"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Readiness Report</title>
<style>
body {{
  color: #243247; background: #f5f7fb; font-family: system-ui, sans-serif; line-height: 1.5;
  margin: 2rem auto; max-width: 1100px; padding: 0 1.25rem;
}}
h1, h2, h3 {{ line-height: 1.25; color: #14233c; }}
h1 {{ margin-bottom: .5rem; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; background: white; }}
th, td {{ border: 1px solid #d9e1ec; padding: .65rem; text-align: left; overflow-wrap: anywhere; }}
th {{ background: #edf2f8; }}
section {{ border-top: 1px solid #d9e1ec; margin-top: 2rem; padding-top: 1rem; }}
.score-summary {{ display: flex; align-items: center; gap: 1.5rem; padding: 1.5rem;
  background: white; border: 1px solid #d9e1ec; border-radius: 1rem; }}
.score-summary h2 {{ margin: 0 0 .5rem; }}
.score-summary p {{ margin: 0; }}
.score-gauge {{ width: 150px; height: 150px; flex-shrink: 0; }}
.score-gauge circle {{ fill: none; stroke-width: 9; }}
.gauge-track {{ stroke: #e8edf5; }}
.gauge-fill {{ stroke: currentColor; }}
.score-gauge text {{ fill: #14233c; text-anchor: middle; }}
.gauge-value {{ font-size: 23px; font-weight: 750; }}
.gauge-unit {{ font-size: 10px; }}
.chart-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }}
.chart-card {{ background: white; border: 1px solid #d9e1ec; border-radius: 1rem; padding: 1.25rem; min-width: 0; }}
.chart-card:first-child {{ grid-column: 1 / -1; }}
.chart-card h3 {{ margin: 0; }}
.chart-note {{ color: #526278; font-size: .875rem; margin: .6rem 0 1.25rem; }}
.chart-row {{ margin: 0 0 1rem; }}
.bar-label {{ display: flex; justify-content: space-between; gap: 1rem; font-size: .875rem; margin-bottom: .35rem; }}
.bar-label span {{ overflow-wrap: anywhere; min-width: 0; }}
.bar-label strong {{ flex-shrink: 0; font-variant-numeric: tabular-nums; }}
.bar-track {{ height: .65rem; background: #e8edf5; border-radius: .25rem; overflow: hidden; }}
.bar-fill {{ display: block; height: 100%; background: currentColor; }}
.accent {{ color: #4263d8; }}
.missing, .band-0 {{ color: #b83e52; }}
.band-1 {{ color: #986000; }}
.band-2 {{ color: #216eb0; }}
.band-3 {{ color: #12816a; }}
.inactive {{ color: #78869b; }}
.chart-legend {{ display: flex; flex-wrap: wrap; gap: .5rem 1rem; font-size: .8rem; color: #526278; }}
.chart-legend i {{ display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; background: currentColor; margin-right: .35rem; }}
.chart-empty {{ padding: 1rem; background: #f5f7fb; border-radius: .5rem; color: #526278; }}
.plot-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }}
.plot-card {{ margin: 0 0 1rem; padding: 1rem; background: white; border: 1px solid #d9e1ec; border-radius: 1rem; min-width: 0; }}
.plot-card h4 {{ margin: 0; overflow-wrap: anywhere; font-size: 1rem; }}
.plot-card p {{ font-size: .875rem; color: #526278; overflow-wrap: anywhere; }}
.plot-card img {{ width: 100%; min-width: 400px; height: auto; display: block; }}
.plot-scroll {{ overflow-x: auto; }}
.plot-wide img {{ min-width: 800px; }}
.plot-data {{ font-size: .8rem; margin-top: .5rem; }}
.plot-data summary {{ cursor: pointer; color: #3453b5; padding: .5rem 0; }}
@media (max-width: 650px) {{
  body {{ margin: 1rem auto; padding: 0 .75rem; }}
  .chart-grid {{ grid-template-columns: minmax(0, 1fr); }}
  .plot-grid {{ grid-template-columns: minmax(0, 1fr); }}
  .score-summary {{ flex-direction: column; align-items: flex-start; gap: .75rem; }}
  .bar-label {{ flex-wrap: wrap; gap: .25rem .75rem; }}
}}
@media print {{
  body {{ background: white; max-width: none; margin: 0; padding: 0; font-size: 10pt; }}
  .chart-grid {{ display: block; }}
  .chart-card {{ margin-bottom: 1rem; break-inside: avoid; }}
  .plot-grid {{ display: block; }}
  .plot-card {{ break-inside: avoid; }}
  .plot-card img {{ min-width: 0; }}
  .score-summary {{ break-inside: avoid; }}
  .bar-track, .bar-fill, .chart-legend i {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
  h2, h3 {{ break-after: avoid; }}
}}
</style>
</head>
<body>
<h1>Data Readiness Report</h1>
<div class="score-summary">
{score_gauge(result['score'])}
<div><h2>Overall score: {escape(str(result['score']))} — {escape(str(result['classification']))}</h2>
<p>{escape(str(report['dataset'].get('file', 'Dataset')))} · Higher scores indicate greater readiness.</p></div>
</div>
{charts_html(report)}
<section><h2>Dataset</h2>{_table(report['dataset'])}</section>
<section><h2>Profile summary</h2>{_table(report['profile']['dataset'])}</section>
{dataset_plots_html(report)}
<section><h2>Usage context</h2>{_table(context_summary)}</section>
<section><h2>Documentation checklist</h2>{_table(context['documentation'])}</section>
<section><h2>Provenance checklist</h2>{_table(context['provenance'])}</section>
{dimensions}
</body>
</html>
"""


def export_html(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_html(report), encoding="utf-8")
    return path
