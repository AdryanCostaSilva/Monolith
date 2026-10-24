from src.evaluation.metadata import evaluate_metadata


LABELS = {
    "variable_descriptions": "Variable descriptions",
    "target_definition": "Target definition",
    "data_collection": "Data collection method",
    "collection_period": "Collection period",
    "units_and_categories": "Units and categories",
    "known_limitations": "Known limitations",
}


def evaluate(context, df=None):
    return evaluate_metadata(context, df, "documentation", LABELS)
