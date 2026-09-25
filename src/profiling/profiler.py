import math

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype, is_object_dtype, is_string_dtype


def _percentage(part, total):
    return round(float(part) / total * 100, 2) if total else 0.0


def _value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _is_text(series):
    return is_object_dtype(series.dtype) or is_string_dtype(series.dtype)


def _numbers_stored_as_text(series):
    values = series.dropna()
    if values.empty or not _is_text(series):
        return False
    return bool(pd.to_numeric(values, errors="coerce").notna().mean() >= 0.9)


def _profile_column(series):
    non_null = series.dropna()
    profile = {
        "type": str(series.dtype),
        "missing_percentage": _percentage(series.isna().sum(), len(series)),
        "unique_count": int(series.nunique(dropna=True)),
        "numbers_stored_as_text": _numbers_stored_as_text(series),
    }

    if is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype):
        profile["statistics"] = {
            str(name): _value(value) for name, value in series.describe().items()
        }
    else:
        profile["top_values"] = [
            {"value": _value(value), "count": int(count)}
            for value, count in non_null.value_counts().head(5).items()
        ]

    return profile


def perfilar(df):
    """Return dataset and column-level profiling data without changing the dataframe."""
    rows, column_count = df.shape
    total_cells = rows * column_count

    return {
        "dataset": {
            "rows": rows,
            "columns": column_count,
            "missing_percentage": _percentage(df.isna().sum().sum(), total_cells),
            "duplicate_rows": int(df.duplicated().sum()),
        },
        "columns": {name: _profile_column(df[name]) for name in df.columns},
    }
