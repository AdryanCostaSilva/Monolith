import json
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from html import escape
from pathlib import Path


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
        f"<td>{item['value']}</td>"
        f"<td>{item['weight']}</td>"
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
        f"<h2>{escape(str(dimension['dimension']))}: {score}</h2>"
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
  color: #222; font-family: sans-serif; line-height: 1.5;
  margin: 2rem auto; max-width: 960px;
}}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
th, td {{ border: 1px solid #ccc; padding: .5rem; text-align: left; }}
th {{ background: #f2f2f2; }}
section {{ border-top: 1px solid #ccc; margin-top: 2rem; padding-top: 1rem; }}
</style>
</head>
<body>
<h1>Data Readiness Report</h1>
<h2>Overall score: {result['score']} — {escape(str(result['classification']))}</h2>
<section><h2>Dataset</h2>{_table(report['dataset'])}</section>
<section><h2>Profile summary</h2>{_table(report['profile']['dataset'])}</section>
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
