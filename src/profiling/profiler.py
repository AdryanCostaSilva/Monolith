import math

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype, is_object_dtype, is_string_dtype

from src.profiling.values import factorize_column, is_nested, release_pages


def _percentage(part, total):
    return round(float(part) / total * 100, 2) if total else 0.0


def _value(value):
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
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


def _numbers_stored_as_text(series, codes, values):
    if not _is_text(series):
        return False
    present = ~pd.isna(values)
    if not present.any():
        return False
    # Parse each distinct string once, weighting by its frequency in the column.
    counts = np.bincount(codes, minlength=len(values))[present]
    numeric = pd.to_numeric(pd.Series(values[present]), errors="coerce").notna().to_numpy()
    return bool(counts[numeric].sum() / counts.sum() >= 0.9)


def _profile_column(series, codes, values, missing):
    nested = is_nested(series)
    non_null_values = (
        values.is_valid().to_numpy(zero_copy_only=False)
        if nested else ~pd.isna(values)
    )
    profile = {
        "type": str(series.dtype),
        "missing_percentage": _percentage(missing, len(series)),
        "unique_count": int(non_null_values.sum()),
        "numbers_stored_as_text": _numbers_stored_as_text(series, codes, values),
    }

    if is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype):
        profile["statistics"] = {
            str(name): _value(value) for name, value in series.describe().items()
        }
    else:
        if nested:
            counts = np.bincount(codes, minlength=len(values))
            counts = pd.Series(counts[non_null_values], index=np.flatnonzero(non_null_values))
            top = counts.nlargest(5, keep="first")
        else:
            top = series.value_counts().head(5)
        profile["top_values"] = [
            {
                "value": _value(values[value].as_py() if nested else value),
                "count": int(count),
            }
            for value, count in top.items()
        ]

    return profile


def profile(df, *, progress=None):
    """Return dataset and column-level profiling data without changing the dataframe."""
    rows, column_count = df.shape
    total_cells = rows * column_count
    columns = {}
    missing_cells = 0
    # Refine row equivalence per column, avoiding a rows-by-columns code matrix.
    row_groups = np.zeros(rows, dtype=np.int64)
    group_count = 1
    for index, name in enumerate(df.columns, 1):
        if progress:
            progress(f"Profiling column {index} / {column_count}: {name}")
        series = df[name]
        missing = int(series.isna().sum())
        missing_cells += missing
        codes, values = factorize_column(series)
        columns[name] = _profile_column(series, codes, values, missing)
        if rows and group_count < rows:
            keys = row_groups * len(values) + codes
            row_groups, groups = pd.factorize(keys)
            group_count = len(groups)
        release_pages(df)

    return {
        "dataset": {
            "rows": rows,
            "columns": column_count,
            "missing_percentage": _percentage(missing_cells, total_cells),
            "duplicate_rows": rows - group_count if rows else 0,
        },
        "columns": columns,
    }
