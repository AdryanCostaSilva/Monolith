"""Shared IQR fences with tolerance for floating-point boundary rounding."""

import numpy as np


def outside_bounds(values, bounds):
    tolerance = bounds.get("tolerance", 0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        below = (values < bounds["lower"]) & ~np.isclose(
            values, bounds["lower"], rtol=16 * np.finfo(float).eps, atol=tolerance)
        above = (values > bounds["upper"]) & ~np.isclose(
            values, bounds["upper"], rtol=16 * np.finfo(float).eps, atol=tolerance)
    return below | above


def iqr_details(values):
    """Use all finite observations; rescaling intermediates prevents overflow."""
    finite = values[np.isfinite(values)]
    if not len(finite):
        return np.isinf(values), {"lower": 0.0, "upper": 0.0, "tolerance": 0.0}
    magnitude = float(np.abs(finite).max()) or 1.0
    q1, q3 = np.quantile(finite / magnitude, [.25, .75])
    iqr = q3 - q1
    limit = np.finfo(float).max / max(magnitude, 1.0)
    # The tolerance follows the fitted quartiles, never future input extremes.
    tolerance = float(16 * np.finfo(float).eps * max(abs(q1), abs(q3), abs(iqr)) * magnitude)
    bounds = {
        "lower": float(max(q1 - 1.5 * iqr, -limit) * magnitude),
        "upper": float(min(q3 + 1.5 * iqr, limit) * magnitude),
        "tolerance": tolerance,
    }
    return outside_bounds(values, bounds), bounds
