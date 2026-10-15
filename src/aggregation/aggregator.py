from math import isfinite
from numbers import Real

from src.config import DIMENSION_WEIGHTS, SCORE_BANDS


def _dimension_score(dimension):
    indicators = dimension["indicators"]
    total_weight = sum(item["weight"] for item in indicators)
    if not indicators or total_weight <= 0:
        raise ValueError(f"Dimension '{dimension['dimension']}' has no positive weight")
    if any(not 0 <= item["value"] <= 100 or item["weight"] <= 0 for item in indicators):
        raise ValueError("Indicator values must be from 0 to 100 and weights must be positive")
    return round(
        sum(item["value"] * item["weight"] for item in indicators) / total_weight,
        2,
    )


def _classification(score):
    classification = SCORE_BANDS[0][1]
    for minimum, label in SCORE_BANDS:
        if score < minimum:
            break
        classification = label
    return classification


def aggregate(dimensions, task_type, dimension_weights=None):
    """Average applicable dimensions using the selected task's weights."""
    if task_type not in DIMENSION_WEIGHTS:
        raise ValueError(f"No weights configured for task type '{task_type}'")
    defaults = DIMENSION_WEIGHTS[task_type]
    weights = dict(defaults)
    if dimension_weights is not None:
        for name, weight in dimension_weights.items():
            if name not in defaults:
                raise ValueError(f"No weight configured for dimension '{name}'")
            if (
                isinstance(weight, bool)
                or not isinstance(weight, Real)
                or not isfinite(weight)
                or weight < 0
            ):
                raise ValueError("Dimension weights must be finite, non-negative numbers")
            weights[name] = float(weight)
    normalized = []
    weighted_score = 0.0
    total_weight = 0.0

    for dimension in dimensions:
        name = dimension["dimension"]
        item = dict(dimension)
        if item["applicable"]:
            if name not in weights:
                raise ValueError(f"No weight configured for dimension '{name}'")
            item["score"] = _dimension_score(item)
            weight = weights[name]
            if weight < 0:
                raise ValueError(f"Dimension '{name}' cannot have a negative weight")
            item["weight"] = weight
            weighted_score += item["score"] * weight
            total_weight += weight
        else:
            # N/A contributes neither a score nor a weight to the average.
            item["score"] = None
            item["weight"] = None
        normalized.append(item)

    if not total_weight:
        raise ValueError("At least one applicable dimension must have a positive weight")

    for item in normalized:
        item["weight_percentage"] = (
            round(item["weight"] / total_weight * 100, 2) if item["applicable"] else None
        )

    score = round(weighted_score / total_weight, 2)
    return {
        "score": score,
        "classification": _classification(score),
        "weight_source": (
            "custom"
            if any(
                item["applicable"] and item["weight"] != defaults[item["dimension"]]
                for item in normalized
            )
            else "study_defaults"
        ),
        "dimensions": normalized,
    }
