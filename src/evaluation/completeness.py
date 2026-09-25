from src.evaluation.base import add_problem, indicator, percentage, result


def evaluate(df, context):
    row_count, column_count = df.shape
    total_cells = row_count * column_count
    missing_by_column = df.isna().sum()
    important = list(dict.fromkeys(context.important_columns))
    missing_columns = [name for name in important if name not in df.columns]
    if missing_columns:
        names = ", ".join(str(name) for name in missing_columns)
        raise ValueError(f"Important columns not found: {names}")

    filled_cells = total_cells - int(missing_by_column.sum())
    acceptable_columns = (
        int((missing_by_column / row_count < 0.2).sum()) if row_count else 0
    )
    complete_rows = int(df.notna().all(axis=1).sum())
    total_important = row_count * len(important)
    filled_important = int(df[important].notna().sum().sum()) if important else 0

    indicators = [
        indicator("% filled cells", percentage(filled_cells, total_cells, 0.0)),
        indicator(
            "% columns with less than 20% missing",
            percentage(acceptable_columns, column_count),
        ),
        indicator("% complete rows", percentage(complete_rows, row_count, 0.0)),
        indicator(
            "% filled in important columns",
            percentage(filled_important, total_important),
        ),
    ]

    problems = []
    recommendations = []
    for name, count in missing_by_column.items():
        if count:
            missing = percentage(count, row_count, 0.0)
            add_problem(
                problems,
                recommendations,
                f"Column '{name}' has {missing}% missing values",
                f"Remove or impute the missing values in column '{name}'",
            )

    return result("Completeness", indicators, problems, recommendations)
