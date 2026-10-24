"""Check that offline graphics accurately represent evaluator and profile data."""

import re
import unittest
from copy import deepcopy
from html.parser import HTMLParser

import pandas as pd

from src.aggregation import aggregate
from src.context import UsageContext
from src.engine import evaluate_dataset
from src.evaluation.class_balance import evaluate as evaluate_balance
from src.profiling import profile
from src.reporting import generate_report
from src.reporting.report_generator import _render_html


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class ReportChartTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({"feature": [None, 2, 3, 4], "target": [0, 0, 0, 1]})
        self.context = UsageContext("Predict a target", "classification", "target")
        self.profile = profile(self.df)
        self.report = generate_report(
            {"file": "sample.csv"}, self.profile, self.context,
            evaluate_dataset(self.df, self.context, self.profile),
        )

    def test_scores_missingness_and_numeric_class_counts_match_source_data(self):
        before = deepcopy(self.report)
        html = _render_html(self.report)
        self.assertIn("Readiness by dimension", html)
        self.assertIn("25%", html)
        self.assertIn("3 (75%)", html)
        self.assertIn("1 (25%)", html)
        self.assertIn("0 missing labels excluded", html)
        for dimension in self.report["result"]["dimensions"]:
            score = f'{dimension["score"]:,.2f}'.rstrip("0").rstrip(".")
            self.assertIn(f"{score} / 100", html)
        self.assertEqual(self.report, before)

    def test_non_applicable_balance_and_no_missing_values(self):
        df = self.df.fillna(1)
        context = UsageContext("Predict a number", "regression", "target")
        dataset_profile = profile(df)
        report = generate_report({}, dataset_profile, context,
                                 evaluate_dataset(df, context, dataset_profile))
        html = _render_html(report)
        self.assertNotIn("Target class distribution", html)
        self.assertIn("Not applicable", html)
        self.assertIn("No missing values in any column", html)
        self.assertIn("Documentation</span><strong>0 / 100", html)

    def test_class_counts_are_bounded_and_exclude_missing_labels(self):
        df = pd.DataFrame({"target": [0] * 20 + list(range(1, 12)) + [None] * 3})
        balance = evaluate_balance(df, self.context)
        distribution = balance["class_distribution"]
        self.assertEqual(len(distribution["classes"]), 8)
        self.assertEqual(distribution["other_count"], 4)
        self.assertEqual(distribution["missing_count"], 3)
        self.assertEqual(sum(item["count"] for item in distribution["classes"]) +
                         distribution["other_count"], 31)
        self.report["result"] = aggregate([balance], self.context.task_type)
        html = _render_html(self.report)
        self.assertIn("Remaining classes (combined)", html)
        self.assertIn("31 non-missing labels", html)
        self.assertIn("3 missing labels excluded", html)

    def test_missing_columns_are_ranked_and_capped_at_ten(self):
        self.report["profile"]["columns"] = {
            f"feature_{index}": {"missing_percentage": index}
            for index in range(1, 13)
        }
        html = _render_html(self.report)
        self.assertIn("Showing 10 of 12 columns", html)
        self.assertLess(html.index(">feature_12<"), html.index(">feature_11<"))
        self.assertIn(">feature_3<", html)
        self.assertNotIn(">feature_2<", html)
        self.assertNotIn(">feature_1<", html)

    def test_all_missing_target_and_empty_data_have_no_division_by_zero(self):
        for df in (pd.DataFrame({"target": [None, None]}),
                   pd.DataFrame({"target": pd.Series(dtype=float)})):
            balance = evaluate_balance(df, self.context)
            self.report["profile"] = profile(df)
            self.report["result"] = aggregate([balance], self.context.task_type)
            html = _render_html(self.report)
            self.assertIn("No non-missing target labels", html)
            self.assertNotRegex(html.lower(), r"\bnan\b")
            if not len(df):
                self.assertIn("No rows to assess", html)

    def test_legacy_reports_use_full_categorical_counts_only(self):
        balance = next(item for item in self.report["result"]["dimensions"]
                       if item["dimension"] == "Class Balance")
        del balance["class_distribution"]
        # Numeric profiles in older reports contain summaries, not class counts.
        self.assertIn("Class counts are unavailable", _render_html(self.report))
        self.report["profile"]["columns"]["target"] = {
            "unique_count": 2,
            "top_values": [{"value": "yes", "count": 3}, {"value": "no", "count": 1}],
        }
        html = _render_html(self.report)
        self.assertIn("3 (75%)", html)
        self.assertIn(">yes<", html)
        self.report["profile"]["columns"]["target"]["unique_count"] = 9
        self.assertIn("Class counts are unavailable", _render_html(self.report))

    def test_untrusted_labels_are_text_and_charts_need_no_remote_resources(self):
        label = '<script>alert("hello")</script>'
        df = pd.DataFrame({label: [label, "normal", label]})
        context = UsageContext(label, "classification", label)
        dataset_profile = profile(df)
        report = generate_report({"file": label}, dataset_profile, context,
                                 evaluate_dataset(df, context, dataset_profile))
        html = _render_html(report)
        parser = DocumentParser()
        parser.feed(html)
        self.assertIn(label, "".join(parser.text))
        self.assertFalse(any(tag in {"script", "link", "iframe"}
                             for tag, _ in parser.tags))
        for tag, attrs in parser.tags:
            if tag == "img":
                self.assertTrue(attrs["src"].startswith("data:image/png;base64,"))
                self.assertTrue(attrs["alt"])
        svg = next(attrs for tag, attrs in parser.tags if tag == "svg")
        self.assertEqual(svg["role"], "img")
        self.assertIn("out of 100", svg["aria-label"])
        for width in re.findall(r'style="width: ([\d.]+)%"', html):
            self.assertTrue(0 <= float(width) <= 100)


if __name__ == "__main__":
    unittest.main()
