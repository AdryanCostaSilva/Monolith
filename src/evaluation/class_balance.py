from src.evaluation.base import add_problem, indicator, percentage, result


def evaluate(df, context):
    if context.task_type != "classification" or not context.target_column:
        return result("Class Balance", [], applicable=False)
    if context.target_column not in df.columns:
        raise ValueError(f"Target column not found: {context.target_column}")

    counts = df[context.target_column].value_counts(dropna=True)
    problems = []
    recommendations = []

    if len(counts) < 2:
        ratio = 0.0
        add_problem(
            problems,
            recommendations,
            f"Target column '{context.target_column}' has fewer than two classes",
            "Collect examples from at least two target classes",
        )
    else:
        ratio = percentage(counts.min(), counts.max(), 0.0)

    rare_classes = [
        class_value
        for class_value, count in counts.items()
        if percentage(count, len(df), 0.0) < 5
    ]
    if rare_classes:
        names = ", ".join(repr(class_value) for class_value in rare_classes)
        add_problem(
            problems,
            recommendations,
            f"Classes with fewer than 5% of rows: {names}",
            "Collect more examples or apply a class-balancing technique",
        )

    indicators = [indicator("Minority-to-majority class ratio", ratio)]
    return result("Class Balance", indicators, problems, recommendations)
