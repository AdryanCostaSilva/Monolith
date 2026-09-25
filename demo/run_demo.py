"""Run the engine twice per dataset and export reproducible results, without a UI."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

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
from src.loading.loader import SUPPORTED_EXTENSIONS
from src.profiling import profile
from src.reporting import export_html, export_json, generate_report


def run_dataset(path):
    df, info = load(path)
    context = UsageContext("Evaluate dataset readiness")
    if "Survived" in df.columns:
        context = UsageContext(
            "Predict passenger survival",
            task_type="classification",
            target_column="Survived",
            important_columns=["Survived"],
        )

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
    return generate_report(info, dataset_profile, context, result)


def main():
    paths = sorted(
        path for path in (ROOT / "datasets").glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not paths:
        print("FAIL: Add a CSV or XLSX file to datasets/.")
        return 1

    failures = 0
    for path in paths:
        try:
            first = run_dataset(path)
            second = run_dataset(path)
            if first["result"] != second["result"]:
                raise ValueError("Engine results differ between runs (RNF02).")

            # Keep the input extension so sample.csv and sample.xlsx cannot collide.
            output = ROOT / "evidence" / "smoke_test" / path.name
            json_path = export_json(first, f"{output}.json")
            html_path = export_html(first, f"{output}.html")

            result = first["result"]
            print(f"PASS: {path.name}: {result['score']} ({result['classification']})")
            for dimension in result["dimensions"]:
                score = dimension["score"] if dimension["applicable"] else "Not applicable"
                print(f"  {dimension['dimension']}: {score}")
            print("  Both runs produced identical results (RNF02).")
            print(f"  JSON: {json_path.relative_to(ROOT)}")
            print(f"  HTML: {html_path.relative_to(ROOT)}")
        except Exception as error:
            # Attempt the remaining datasets, but fail the overall smoke test.
            failures += 1
            print(f"FAIL: {path.name}: {error}")

    print(f"\n{len(paths) - failures}/{len(paths)} dataset(s) passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
