from src.aggregation import aggregate
from src.evaluation import (
    evaluate_class_balance,
    evaluate_completeness,
    evaluate_consistency,
    evaluate_documentation,
    evaluate_provenance,
    evaluate_quality,
)
from src.profiling import profile


def evaluate_dataset(df, context, dataset_profile=None):
    dataset_profile = dataset_profile or profile(df)
    dimensions = [
        evaluate_completeness(df, context),
        evaluate_consistency(df, dataset_profile),
        evaluate_class_balance(df, context),
        evaluate_documentation(context),
        evaluate_provenance(context),
        evaluate_quality(df),
    ]
    return aggregate(dimensions)
