import sys

import pandas as pd

from src.aggregation import aggregate
from src.context import UsageContext
from src.evaluation import (
    evaluate_class_balance,
    evaluate_completeness,
    evaluate_consistency,
    evaluate_documentation,
    evaluate_provenance,
    evaluate_quality,
)
from src.loading import load
from src.profiling import profile
from src.reporting import export_html, export_json, generate_report


def sample_data():
    df = pd.DataFrame(
        {
            "Age": [22, None, 35, 35],
            "Cabin": [None, None, "E46", "E46"],
            "Embarked": ["S", "C", "Q", "Q"],
            "Survived": [0, 0, 1, 1],
        }
    )
    info = {
        "file": "sample.csv",
        "format": "csv",
        "encoding": "utf-8",
        "delimiter": ",",
        "rows": len(df),
        "columns": len(df.columns),
    }
    context = UsageContext(
        "Predict passenger survival",
        task_type="classification",
        target_column="Survived",
        important_columns=["Age", "Survived"],
    )
    return df, info, context


def main():
    if len(sys.argv) > 1:
        df, info = load(sys.argv[1])
        context = UsageContext("Evaluate dataset readiness")
    else:
        df, info, context = sample_data()

    dataset_profile = profile(df)
    dimensions = [
        evaluate_completeness(df, context),
        evaluate_consistency(df, dataset_profile),
        evaluate_class_balance(df, context),
        evaluate_documentation(context),
        evaluate_provenance(context),
        evaluate_quality(df),
    ]
    result = aggregate(dimensions)
    report = generate_report(info, dataset_profile, context, result)
    json_path = export_json(report, "evidence/demo_report.json")
    html_path = export_html(report, "evidence/demo_report.html")

    print(f"Score: {result['score']} ({result['classification']})")
    for dimension in result["dimensions"]:
        print(f"- {dimension['dimension']}: {dimension['score']}")
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
