from src.config import DEFAULT_INDICATOR_WEIGHT


def percentage(part, total, empty=100.0):
    return round(float(part) / total * 100, 2) if total else empty


def indicator(name, value, weight=DEFAULT_INDICATOR_WEIGHT):
    return {"name": name, "value": round(float(value), 2), "weight": weight}


def add_problem(problems, recommendations, problem, recommendation):
    problems.append(problem)
    recommendations.append(recommendation)


def result(dimension, indicators, problems=None, recommendations=None, applicable=True):
    problems = problems or []
    recommendations = recommendations or []
    if len(problems) != len(recommendations):
        raise ValueError("Every problem must have a recommendation.")

    total_weight = sum(item["weight"] for item in indicators)
    score = None
    if applicable:
        score = round(
            sum(item["value"] * item["weight"] for item in indicators) / total_weight,
            2,
        ) if total_weight else 0.0

    return {
        "dimension": dimension,
        "applicable": applicable,
        "score": score,
        "indicators": indicators,
        "problems": problems,
        "recommendations": recommendations,
    }
