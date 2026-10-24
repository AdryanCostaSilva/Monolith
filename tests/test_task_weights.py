import unittest
from copy import deepcopy

import pandas as pd

from src.aggregation import aggregate
from src.config import DIMENSION_WEIGHTS
from src.context import DOCUMENTATION_ITEMS, PROVENANCE_ITEMS, UsageContext
from src.engine import evaluate_dataset
from src.metadata import METADATA_ATTR
from src.evaluation import evaluate_class_balance
from src.evaluation.base import indicator, result


class TaskWeightTests(unittest.TestCase):
    def test_nonclassification_class_balance_does_not_lower_score(self):
        df = pd.DataFrame({"target": [10.5, 20.5, 30.5, 40.5]})
        for task_type in ("regression", "other"):
            with self.subTest(task_type=task_type):
                context = UsageContext(
                    "Predict a continuous value",
                    task_type=task_type,
                    target_column="target",
                )
                balance = evaluate_class_balance(df, context)
                self.assertFalse(balance["applicable"])
                self.assertIsNone(balance["score"])

                completeness = result("Completeness", [indicator("Filled", 80)])
                with_balance = aggregate([completeness, balance], task_type)
                without_balance = aggregate([completeness], task_type)

                self.assertEqual(with_balance["score"], 80)
                self.assertEqual(with_balance["score"], without_balance["score"])
                self.assertIsNone(with_balance["dimensions"][1]["score"])

    def test_classification_without_target_excludes_class_balance(self):
        context = UsageContext("Explore the data", task_type="classification")
        balance = evaluate_class_balance(pd.DataFrame({"value": [1, 2]}), context)
        completeness = result("Completeness", [indicator("Filled", 80)])

        evaluation = aggregate([completeness, balance], context.task_type)

        self.assertEqual(evaluation["score"], 80)
        self.assertFalse(evaluation["dimensions"][1]["applicable"])
        self.assertIsNone(evaluation["dimensions"][1]["score"])

    def test_classification_uses_class_balance_weight(self):
        context = UsageContext(
            "Predict a class", task_type="classification", target_column="target"
        )
        df = pd.DataFrame({"target": ["a", "a", "a", "b"]})
        balance = evaluate_class_balance(df, context)
        completeness = result("Completeness", [indicator("Filled", 80)])

        evaluation = aggregate([completeness, balance], context.task_type)

        self.assertTrue(balance["applicable"])
        self.assertEqual(balance["score"], 33.33)
        self.assertEqual(evaluation["score"], 69.37)

    def test_applicable_zero_still_lowers_score(self):
        context = UsageContext(
            "Predict a class", task_type="classification", target_column="target"
        )
        balance = evaluate_class_balance(pd.DataFrame({"target": ["a", "a"]}), context)
        completeness = result("Completeness", [indicator("Filled", 80)])

        evaluation = aggregate([completeness, balance], context.task_type)

        self.assertTrue(balance["applicable"])
        self.assertEqual(balance["score"], 0)
        self.assertEqual(evaluation["score"], 61.78)

    def test_perfect_regression_dataset_scores_100(self):
        df = pd.DataFrame(
            {"feature": [1, 2, 3, 4], "target": [10.5, 20.5, 30.5, 40.5]}
        )
        context = UsageContext(
            "Predict a continuous value",
            task_type="regression",
            target_column="target",
            documentation=dict.fromkeys(DOCUMENTATION_ITEMS, True),
            provenance=dict.fromkeys(PROVENANCE_ITEMS, True),
        )
        df.attrs[METADATA_ATTR] = {"source": "sample.csv.metadata.json", "metadata": {
            "columns": {
                "feature": {"description": "Input", "unit": "dimensionless"},
                "target": {"description": "Output", "unit": "dimensionless"},
            },
            "documentation": {
                "target_definition": {"column": "target", "description": "Output"},
                "data_collection": "Measured in a controlled experiment",
                "collection_period": {"start": "2026-01-01", "end": "2026-01-02"},
                "known_limitations": ["Small sample"],
            },
            "provenance": {
                "origin": "Experiment 1", "collector": "Research team",
                "generation_period": {"start": "2026-01-01", "end": "2026-01-02"},
                "transformations": ["Raw measurements"], "version": "1",
            },
        }}

        evaluation = evaluate_dataset(df, context)

        self.assertEqual(evaluation["score"], 100)
        self.assertEqual(evaluation["classification"], "Ready")
        balance = next(
            dimension
            for dimension in evaluation["dimensions"]
            if dimension["dimension"] == "Class Balance"
        )
        self.assertFalse(balance["applicable"])
        self.assertIsNone(balance["score"])

    def test_applicable_dimension_requires_a_configured_weight(self):
        dimension = result("Unknown", [indicator("Example", 80)])

        with self.assertRaisesRegex(ValueError, "No weight configured"):
            aggregate([dimension], "regression")

    def test_at_least_one_applicable_dimension_is_required(self):
        balance = result("Class Balance", [], applicable=False)

        with self.assertRaisesRegex(ValueError, "At least one applicable dimension"):
            aggregate([balance], "regression")

    def test_custom_weights_change_overall_score_without_changing_dimension_scores(self):
        dimensions = [
            result("Completeness", [indicator("Filled", 80)]),
            result("Documentation", [indicator("Documented", 0)]),
        ]
        original = deepcopy(dimensions)
        defaults = deepcopy(DIMENSION_WEIGHTS)

        evaluation = aggregate(
            dimensions, "regression", {"Completeness": 1, "Documentation": 3}
        )

        self.assertEqual(evaluation["score"], 20)
        self.assertEqual(evaluation["weight_source"], "custom")
        self.assertEqual(evaluation["dimensions"][0]["weight_percentage"], 25)
        self.assertEqual(evaluation["dimensions"][1]["weight_percentage"], 75)
        self.assertEqual([item["score"] for item in evaluation["dimensions"]], [80, 0])
        self.assertEqual(dimensions, original)
        self.assertEqual(DIMENSION_WEIGHTS, defaults)

    def test_zero_custom_weight_excludes_an_applicable_dimension(self):
        dimensions = [
            result("Completeness", [indicator("Filled", 80)]),
            result("Documentation", [indicator("Documented", 0)]),
        ]

        evaluation = aggregate(dimensions, "regression", {"Documentation": 0})

        self.assertEqual(evaluation["score"], 80)
        self.assertTrue(evaluation["dimensions"][1]["applicable"])
        self.assertEqual(evaluation["dimensions"][1]["score"], 0)
        self.assertEqual(evaluation["dimensions"][1]["weight_percentage"], 0)

    def test_all_zero_custom_weights_are_rejected(self):
        dimensions = [result("Completeness", [indicator("Filled", 80)])]

        with self.assertRaisesRegex(ValueError, "positive weight"):
            aggregate(dimensions, "regression", {"Completeness": 0})

    def test_invalid_custom_weights_are_rejected(self):
        dimensions = [result("Completeness", [indicator("Filled", 80)])]
        for weight in (-1, float("nan"), float("inf"), "10", True):
            with self.subTest(weight=weight):
                with self.assertRaisesRegex(ValueError, "finite, non-negative"):
                    aggregate(dimensions, "regression", {"Completeness": weight})
        with self.assertRaisesRegex(ValueError, "No weight configured"):
            aggregate(dimensions, "regression", {"Class Balance": 10})

    def test_reset_to_study_defaults_restores_original_score(self):
        dimensions = [
            result("Completeness", [indicator("Filled", 80)]),
            result("Documentation", [indicator("Documented", 0)]),
        ]
        original = aggregate(dimensions, "regression")
        custom = aggregate(dimensions, "regression", {"Documentation": 50})

        reset = aggregate(custom["dimensions"], "regression")

        self.assertNotEqual(custom["score"], original["score"])
        self.assertEqual(reset, original)
        self.assertEqual(reset["weight_source"], "study_defaults")

    def test_engine_accepts_custom_weights(self):
        df = pd.DataFrame({"feature": [1, 2, 3, 4]})
        context = UsageContext("Explore the data", task_type="regression")

        evaluation = evaluate_dataset(
            df,
            context,
            dimension_weights={
                "Completeness": 0,
                "Consistency": 0,
                "Data Quality": 0,
                "Documentation": 1,
                "Provenance": 1,
            },
        )

        self.assertEqual(evaluation["score"], 0)
        self.assertEqual(evaluation["weight_source"], "custom")


if __name__ == "__main__":
    unittest.main()
