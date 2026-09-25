from pandas.api.types import is_bool_dtype, is_numeric_dtype

from src.evaluation.base import add_problem, indicator, percentage, result


def _count_outliers(series):
    values = series.dropna()
    if values.empty:
        return 0, 0
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = q3 - q1
    count = int(((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).sum())
    return count, len(values)


def evaluate(df):
    numeric_columns = [
        name
        for name in df.columns
        if is_numeric_dtype(df[name].dtype) and not is_bool_dtype(df[name].dtype)
    ]
    outliers_by_column = {}
    outlier_count = 0
    numeric_value_count = 0
    for name in numeric_columns:
        count, total = _count_outliers(df[name])
        outlier_count += count
        numeric_value_count += total
        if count:
            outliers_by_column[name] = count

    constant_columns = [
        name for name in df.columns if df[name].nunique(dropna=True) <= 1
    ]
    indicators = [
        indicator(
            "% numeric values without outliers",
            percentage(numeric_value_count - outlier_count, numeric_value_count),
        ),
        indicator(
            "% non-constant columns",
            percentage(len(df.columns) - len(constant_columns), len(df.columns)),
        ),
    ]

    problems = []
    recommendations = []
    for name, count in outliers_by_column.items():
        add_problem(
            problems,
            recommendations,
            f"Column '{name}' has {count} outlier(s) under the IQR rule",
            f"Review the outliers in column '{name}' and treat them when appropriate",
        )
    for name in constant_columns:
        add_problem(
            problems,
            recommendations,
            f"Column '{name}' is constant",
            f"Remove column '{name}' if it is not required",
        )

    return result("Data Quality", indicators, problems, recommendations)
