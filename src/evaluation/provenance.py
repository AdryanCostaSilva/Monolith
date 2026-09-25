from src.evaluation.base import add_problem, indicator, result


LABELS = {
    "origin": "Data origin",
    "collector": "Data collector",
    "generation_period": "Generation period",
    "transformations": "Applied transformations",
    "version": "Dataset version",
}


def evaluate(context):
    indicators = []
    problems = []
    recommendations = []

    for item, answer in context.provenance.items():
        label = LABELS[item]
        indicators.append(indicator(label, 100 if answer else 0))
        if not answer:
            add_problem(
                problems,
                recommendations,
                f"Missing provenance: {label.lower()}",
                f"Record the {label.lower()}",
            )

    return result("Provenance", indicators, problems, recommendations)
