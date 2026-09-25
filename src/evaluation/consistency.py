from numbers import Number

from pandas.api.types import is_numeric_dtype

from src.evaluation.base import add_problem, indicator, percentage, result
from src.profiling.profiler import profile


def _value_type(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Number):
        return "number"
    if isinstance(value, str):
        return "text"
    return type(value).__name__


def _has_mixed_types(series):
    return len({_value_type(value) for value in series.dropna()}) > 1


def _has_text_variants(series):
    groups = {}
    for value in series.dropna().unique():
        if isinstance(value, str):
            groups.setdefault(value.strip().casefold(), set()).add(value)
    return any(len(variants) > 1 for variants in groups.values())


def evaluate(df, dataset_profile=None):
    dataset_profile = dataset_profile or profile(df)
    row_count, column_count = df.shape
    duplicate_count = int(df.duplicated().sum())
    inconsistent = []
    variant_columns = []

    for name in df.columns:
        mixed_types = _has_mixed_types(df[name])
        numeric_text = dataset_profile["columns"][name]["numbers_stored_as_text"]
        if mixed_types or numeric_text:
            inconsistent.append((name, mixed_types, numeric_text))
        if not is_numeric_dtype(df[name].dtype) and _has_text_variants(df[name]):
            variant_columns.append(name)

    categorical = [
        name for name in df.columns if not is_numeric_dtype(df[name].dtype)
    ]
    indicators = [
        indicator(
            "% non-duplicate rows",
            percentage(row_count - duplicate_count, row_count, 0.0),
        ),
        indicator(
            "% columns with consistent types",
            percentage(column_count - len(inconsistent), column_count),
        ),
        indicator(
            "% categorical columns without text variants",
            percentage(len(categorical) - len(variant_columns), len(categorical)),
        ),
    ]

    problems = []
    recommendations = []
    if duplicate_count:
        add_problem(
            problems,
            recommendations,
            f"Dataset has {duplicate_count} duplicate row(s)",
            "Review and remove duplicate rows",
        )

    for name, mixed_types, numeric_text in inconsistent:
        reasons = []
        if mixed_types:
            reasons.append("mixed types")
        if numeric_text:
            reasons.append("numbers stored as text")
        add_problem(
            problems,
            recommendations,
            f"Column '{name}' contains {' and '.join(reasons)}",
            f"Convert column '{name}' to a consistent type",
        )

    for name in variant_columns:
        add_problem(
            problems,
            recommendations,
            f"Column '{name}' has case or whitespace variants",
            f"Standardize the text values in column '{name}'",
        )

    return result("Consistency", indicators, problems, recommendations)
