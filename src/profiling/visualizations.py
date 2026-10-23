"""Small, reproducible numeric summaries for plots, without exporting raw rows."""

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype


MAX_SAMPLE_ROWS = 10_000
MAX_NUMERIC_COLUMNS = 24
HISTOGRAM_BINS = 24


def visualization_profile(df):
    """Sample numeric columns once; keep plot data bounded for large datasets."""
    numeric_names = [
        name for name in df.columns
        if (is_numeric_dtype(df[name].dtype) or is_bool_dtype(df[name].dtype))
        and not is_complex_dtype(df[name].dtype)
    ]
    names = numeric_names[:MAX_NUMERIC_COLUMNS]
    size = min(len(df), MAX_SAMPLE_ROWS)
    positions = (
        np.sort(np.random.default_rng(42).choice(len(df), size, replace=False))
        if len(df) > size else np.arange(size)
    )
    sampled = {}
    histograms = {}
    for name in names:
        values = df[name].iloc[positions].to_numpy(dtype=float, na_value=np.nan, copy=True)
        values[~np.isfinite(values)] = np.nan
        finite = values[np.isfinite(values)]
        scale = max(float(np.abs(finite).max()), 1.0) if len(finite) else 1.0
        # Per-column scaling leaves Pearson coefficients unchanged and avoids overflow.
        sampled[name] = values / scale
        if not len(finite) or is_bool_dtype(df[name].dtype):
            continue
        # Normalize before binning to avoid overflow when finite values are extreme.
        normalized = finite / scale
        low, high = float(normalized.min()), float(normalized.max())
        if low == high:
            low, high = max(-1.0, low - .5), min(1.0, high + .5)
        counts, edges = np.histogram(normalized, bins=HISTOGRAM_BINS, range=(low, high))
        histograms[name] = {
            "counts": counts.tolist(),
            "edges": (edges * scale).tolist(),
            "finite_count": len(finite),
        }

    frame = pd.DataFrame(sampled)
    # Constant or empty columns do not have a defined Pearson correlation.
    varying = [name for name in names if frame[name].nunique() > 1]
    frame = frame[varying]
    correlation = frame.corr(min_periods=3)
    present = frame.notna().to_numpy(dtype=np.int64)
    pairs = present.T @ present
    return {
        "sample_rows": size,
        "total_rows": len(df),
        "numeric_columns_total": len(numeric_names),
        "numeric_columns_profiled": names,
        "histograms": histograms,
        "correlation": {
            "columns": varying,
            "values": [
                [float(value) if np.isfinite(value) else None for value in row]
                for row in correlation.to_numpy()
            ],
            "pair_counts": pairs.tolist(),
        },
    }
