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


def aggregate(dimensions):
    normalized = []
    weighted_score = 0.0
    total_weight = 0.0

    for dimension in dimensions:
        name = dimension["dimension"]
        if name not in DIMENSION_WEIGHTS:
            raise ValueError(f"No weight configured for dimension '{name}'")

        item = dict(dimension)
        if item["applicable"]:
            item["score"] = _dimension_score(item)
            weight = DIMENSION_WEIGHTS[name]
            if weight <= 0:
                raise ValueError(f"Dimension '{name}' must have a positive weight")
            weighted_score += item["score"] * weight
            total_weight += weight
        else:
            item["score"] = None
        normalized.append(item)

    if not total_weight:
        raise ValueError("At least one applicable dimension is required")

    score = round(weighted_score / total_weight, 2)
    return {
        "score": score,
        "classification": _classification(score),
        "dimensions": normalized,
    }
