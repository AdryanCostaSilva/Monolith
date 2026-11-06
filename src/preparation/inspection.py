"""Bounded chart and record data for the Preparation page; no Tk dependencies."""

import numpy as np

from src.preparation.transforms import is_measurement, source_row_numbers
from src.profiling.outliers import iqr_details, outside_bounds
from src.profiling.values import value_counts
from src.profiling.visualizations import MAX_SAMPLE_ROWS


def inspect_frame(df, column, target=None, *, source_rows=None):
    source_rows = source_row_numbers(df, source_rows)
    missing_counts = df.isna().sum()
    missing = missing_counts.sort_values(ascending=False).head(12)
    result = {
        "rows": len(df), "missing": int(missing_counts.sum()),
        "missing_columns": {str(name): int(count) for name, count in missing.items()},
        "target": _counts(df[target]) if target in df.columns else {},
        "column": str(column) if column is not None else "",
        "numeric": False, "values": [], "categories": {}, "outliers": 0,
        "records": [], "missing_records": [], "column_missing": 0, "note": "",
        "category_share": [], "category_share_note": "",
    }
    if column not in df.columns:
        return result
    series = df[column]
    missing_positions = np.flatnonzero(series.isna().to_numpy())
    result["column_missing"] = len(missing_positions)
    result["missing_records"] = [{"row": int(position) + 1, "source_row": int(source_rows[position]), "value": "Missing"}
                                 for position in missing_positions[:8]]
    # A share chart must account for the entire column, including missing rows.
    # Continuous measurements are deliberately not interpreted as categories.
    measurement = is_measurement(series)
    if not measurement or series.head(1000).nunique() <= 5:
        counts = value_counts(series)
        if len(counts) + bool(len(missing_positions)) <= 5:
            result["category_share"] = [
                {"label": _label(value), "count": int(count)} for value, count in counts.items()
            ]
            if len(missing_positions):
                result["category_share"].append({"label": "Missing values", "count": len(missing_positions)})
    if not result["category_share"]:
        result["category_share_note"] = "Category share needs at most five categories, including missing values. Use Distribution for more values."
    if not measurement:
        result["categories"] = _counts(series)
        result["note"] = "Showing up to eight categories; counts use all rows."
        return result
    values = series.to_numpy(dtype=float, na_value=np.nan)
    finite = values[np.isfinite(values)]
    result["numeric"] = True
    result["finite_count"] = len(finite)
    mask, bounds = iqr_details(values)
    result["outliers"] = int(mask.sum())
    result["bounds"] = bounds
    for position in np.flatnonzero(mask)[:8]:
        result["records"].append({"row": int(position) + 1, "source_row": int(source_rows[position]), "value": str(series.iloc[position])})
    if not len(finite):
        result["note"] = "No finite values to plot. Correct infinite values before numerical preparation."
        return result
    sample = (np.random.default_rng(42).choice(finite, MAX_SAMPLE_ROWS, replace=False)
              if len(finite) > MAX_SAMPLE_ROWS else finite)
    result["values"] = sample.tolist()
    magnitude = max(float(np.abs(finite).max()), 1.0)
    q1, median, q3 = np.quantile(finite / magnitude, [.25, .5, .75]) * magnitude
    inside = finite[~outside_bounds(finite, bounds)]
    result["box"] = {
        "q1": float(q1), "med": float(median), "q3": float(q3),
        "whislo": float(inside.min()) if len(inside) else float(q1),
        "whishi": float(inside.max()) if len(inside) else float(q3),
        "fliers": sample[outside_bounds(sample, bounds)][:200].tolist(),
    }
    result["note"] = (f"Histogram: {len(sample):,} of {len(finite):,} finite values. "
                      f"IQR limits: {bounds['lower']:.5g} to {bounds['upper']:.5g}. "
                      "Quartiles use all finite values; up to 200 sampled outliers shown.")
    if np.isinf(values).any():
        result["note"] += " Infinite values are excluded from charts and block numerical preparation."
    return result


def _counts(series):
    return {_label(value): int(count) for value, count in value_counts(series).head(8).items()}


def _label(value):
    # Quote whitespace variants so a cleanup chart can distinguish "SP" and " SP ".
    return repr(value) if isinstance(value, str) and value != value.strip() else str(value)
