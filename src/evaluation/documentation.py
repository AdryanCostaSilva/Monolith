from src.evaluation.base import add_problem, indicator, result


LABELS = {
    "variable_descriptions": "Variable descriptions",
    "target_definition": "Target definition",
    "data_collection": "Data collection method",
    "collection_period": "Collection period",
    "units_and_categories": "Units and categories",
    "known_limitations": "Known limitations",
}


def evaluate(context):
    indicators = []
    problems = []
    recommendations = []

    for item, answer in context.documentation.items():
        label = LABELS[item]
        indicators.append(indicator(label, 100 if answer else 0))
        if not answer:
            add_problem(
                problems,
                recommendations,
                f"Missing documentation: {label.lower()}",
                f"Document the {label.lower()}",
            )

    return result("Documentation", indicators, problems, recommendations)
