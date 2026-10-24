from src.evaluation.metadata import evaluate_metadata


LABELS = {
    "origin": "Data origin",
    "collector": "Data collector",
    "generation_period": "Generation period",
    "transformations": "Applied transformations",
    "version": "Dataset version",
}


def evaluate(context, df=None):
    return evaluate_metadata(context, df, "provenance", LABELS)
