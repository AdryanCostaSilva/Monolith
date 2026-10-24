"""Score user confirmations first, falling back to uploaded metadata per item."""

from datetime import date

from src.evaluation.base import add_problem, indicator, percentage, result
from src.metadata import METADATA_ATTR


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _period(value):
    if not isinstance(value, dict):
        return False
    try:
        start = date.fromisoformat(value.get("start", ""))
        end = date.fromisoformat(value.get("end", ""))
        return (
            start <= end and start.isoformat() == value.get("start")
            and end.isoformat() == value.get("end")
        )
    except (TypeError, ValueError):
        return False


def _strings(value):
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def evaluate_metadata(context, df, group, labels):
    bundle = df.attrs.get(METADATA_ATTR, {}) if df is not None else {}
    metadata = bundle.get("metadata", {})
    fields = metadata.get("columns", {})
    fields = fields if isinstance(fields, dict) else {}
    section = metadata.get(group, {})
    section = section if isinstance(section, dict) else {}
    columns = [str(column) for column in df.columns] if df is not None else []
    indicators, problems, recommendations, excluded = [], [], [], []

    for item, label in labels.items():
        field = f"{group}.{item}"
        value = section.get(item)
        applicable = True
        detail = "Supply a non-empty text value."
        valid = _text(value)
        matched = []
        if group == "documentation":
            if item in {"variable_descriptions", "units_and_categories"}:
                field = "columns"
                for column in columns:
                    entry = fields.get(column, {})
                    if not isinstance(entry, dict):
                        continue
                    covered = _text(entry.get("description"))
                    if item == "units_and_categories":
                        categories = entry.get("categories")
                        covered = _text(entry.get("unit")) or (
                            isinstance(categories, dict) and bool(categories)
                            and all(_text(description) for description in categories.values())
                        )
                    if covered:
                        matched.append(column)
                valid = bool(columns) and len(matched) == len(columns)
                detail = f"{len(matched)}/{len(columns)} dataset columns covered."
                value = {column: fields[column] for column in matched}
            elif item == "target_definition":
                applicable = context.target_column is not None
                target = section.get(item)
                valid = (
                    applicable and str(context.target_column) in columns
                    and isinstance(target, dict)
                    and target.get("column") == str(context.target_column)
                    and _text(target.get("description"))
                )
                detail = "Define the selected target column and its meaning."
            elif item == "collection_period":
                valid = _period(value)
                detail = "Supply start/end ISO dates (YYYY-MM-DD), with start <= end."
            elif item == "known_limitations":
                valid = _strings(value)
                detail = "Supply a non-empty list of limitations; explicitly state if none are known."
        else:
            if item == "generation_period":
                valid = _period(value)
                detail = "Supply start/end ISO dates (YYYY-MM-DD), with start <= end."
            elif item == "transformations":
                valid = _strings(value)
                detail = "List the transformations; explicitly state if the data is raw."

        score = 100 if valid else 0
        if group == "documentation" and item in {"variable_descriptions", "units_and_categories"}:
            score = percentage(len(matched), len(columns), empty=0)
        claimed = getattr(context, group)[item]
        if claimed and applicable:
            score = 100
            detail = "User confirmed this item; checkbox takes priority over uploaded metadata."
        entry = indicator(label, score)
        entry.update({
            "item": item,
            "status": (
                "not_applicable" if not applicable else
                "self_reported" if claimed else
                "documented" if valid else "partial" if score else
                "missing"
            ),
            "self_reported": claimed,
            "source": "User checkbox" if claimed and applicable else bundle.get("source"),
            "field": f"{group}.{item}" if claimed and applicable else field,
            "evidence": True if claimed and applicable else value,
            "detail": detail if applicable else "No target column selected; excluded from score.",
        })
        # Keep excluded items in the audit trail, outside the weighted indicators.
        if not applicable:
            excluded.append(entry)
            continue
        indicators.append(entry)
        if score < 100:
            add_problem(
                problems, recommendations,
                f"Incomplete {group}: {label.lower()}. {detail}",
                f"Confirm {label.lower()} with its checkbox, or supply {field} in an uploaded metadata file. {detail}",
            )

    dimension = result(group.capitalize(), indicators, problems, recommendations)
    dimension["assessment"] = {
        "method": "checkbox_then_metadata",
        "source": bundle.get("source"),
        "dataset_sha256": bundle.get("dataset_sha256"),
        "warnings": list(bundle.get("warnings", [])),
        "note": (
            "Checked items receive full credit as user confirmations. Unchecked items use "
            "uploaded metadata coverage and structure. Statements are not independently verified."
        ),
    }
    dimension["excluded_indicators"] = excluded
    return dimension
