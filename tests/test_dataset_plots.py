"""Validate plot statistics and self-contained Matplotlib exports."""

import base64
import json
import unittest
from copy import deepcopy
from html.parser import HTMLParser
from io import BytesIO

import numpy as np
import pandas as pd
from PIL import Image

from src.context import UsageContext
from src.profiling import profile
from src.profiling.visualizations import MAX_NUMERIC_COLUMNS, MAX_SAMPLE_ROWS, visualization_profile
from src.reporting import generate_report
from src.reporting.dataset_plots import dataset_plots_html


class ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "img":
            self.images.append(dict(attrs))


class VisualizationProfileTests(unittest.TestCase):
    def test_histograms_correlations_and_pair_counts_use_finite_rows(self):
        df = pd.DataFrame({
            "a": [-2., -1., 0., 1., 2., np.inf, np.nan],
            "b": [4., 2., 0., -2., -4., 100., np.inf],
            "constant": [1.] * 7,
            "flag": [True, False, True, False, True, False, True],
        })
        before = df.copy(deep=True)
        result = visualization_profile(df)
        histogram = result["histograms"]["a"]
        self.assertEqual(histogram["finite_count"], 5)
        self.assertEqual(histogram["edges"][0], -2)
        self.assertEqual(histogram["edges"][-1], 2)
        self.assertEqual(sum(histogram["counts"]), 5)
        self.assertEqual(np.flatnonzero(histogram["counts"]).tolist(), [0, 6, 12, 18, 23])
        self.assertNotIn("flag", result["histograms"])
        correlation = result["correlation"]
        i, j = (correlation["columns"].index(name) for name in ("a", "b"))
        self.assertAlmostEqual(correlation["values"][i][j], -1)
        self.assertEqual(correlation["pair_counts"][i][j], 5)
        self.assertNotIn("constant", correlation["columns"])
        json.dumps(result, allow_nan=False)
        pd.testing.assert_frame_equal(df, before)

    def test_large_inputs_are_bounded_and_reproducible(self):
        df = pd.DataFrame({f"column_{i}": np.arange(MAX_SAMPLE_ROWS + 21) + i
                           for i in range(MAX_NUMERIC_COLUMNS + 2)})
        first = visualization_profile(df)
        self.assertEqual(first, visualization_profile(df))
        self.assertEqual(first["sample_rows"], MAX_SAMPLE_ROWS)
        self.assertEqual(first["total_rows"], len(df))
        self.assertEqual(first["numeric_columns_total"], MAX_NUMERIC_COLUMNS + 2)
        self.assertEqual(len(first["histograms"]), MAX_NUMERIC_COLUMNS)
        for histogram in first["histograms"].values():
            self.assertEqual(sum(histogram["counts"]), MAX_SAMPLE_ROWS)

    def test_nullable_empty_text_and_extreme_columns_are_serializable(self):
        for df in (
            pd.DataFrame({"a": pd.Series([1, None, 3], dtype="Int64")}),
            pd.DataFrame({"a": pd.Series(dtype=float)}),
            pd.DataFrame({"label": ["x", "y"]}),
            pd.DataFrame({"a": [np.inf, -np.inf, np.nan]}),
            pd.DataFrame({"a": [np.finfo(float).max] * 3}),
        ):
            with self.subTest(dtype=df.dtypes.to_dict()):
                result = visualization_profile(df)
                json.dumps(result, allow_nan=False)
                for histogram in result["histograms"].values():
                    self.assertTrue(all(np.isfinite(histogram["edges"])))
                    self.assertEqual(sum(histogram["counts"]), histogram["finite_count"])


class DatasetPlotTests(unittest.TestCase):
    def make_report(self):
        df = pd.DataFrame({
            "amount": [10, 20, 30, 40, 50, 60],
            "volume": [20, 40, 60, 80, 100, 120],
            "group": ["A", "A", "A", "B", "B", "C"],
            "other": ["one", "two", "two", "one", "one", "two"],
        })
        return generate_report({}, profile(df),
                               UsageContext("Explore data", important_columns=["volume", "group"]),
                               {"dimensions": []})

    def test_matplotlib_pngs_are_embedded_with_accessible_descriptions_and_data(self):
        report = self.make_report()
        before = deepcopy(report)
        html = dataset_plots_html(report)
        parser = ImageParser()
        parser.feed(html)
        self.assertEqual(len(parser.images), 5)  # Two histograms, heatmap, two categories.
        self.assertIn("all 6 rows", html)
        self.assertIn("r = 1.00, 6 paired sample rows", html)
        self.assertIn("View plot data", html)
        self.assertLess(html.index("<h4>volume</h4>"), html.index("<h4>amount</h4>"))
        for attrs in parser.images:
            prefix, encoded = attrs["src"].split(",", 1)
            self.assertEqual(prefix, "data:image/png;base64")
            self.assertTrue(attrs["alt"])
            image = Image.open(BytesIO(base64.b64decode(encoded, validate=True)))
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 600)
            image.verify()
        self.assertEqual(report, before)

    def test_saved_summaries_produce_quartile_plots_without_inventing_histograms(self):
        report = self.make_report()
        del report["profile"]["visualizations"]
        html = dataset_plots_html(report)
        self.assertIn("Numeric ranges and quartiles", html)
        self.assertIn("Whiskers show minimum and maximum", html)
        self.assertNotIn("Correlation heatmap", html)
        self.assertIn("Re-evaluate the dataset", html)

    def test_labels_are_literal_and_escaped(self):
        label = r'<script>$\unknown{value}$</script>'
        df = pd.DataFrame({label: [label, "ordinary", label], "number": [1, 2, 3]})
        report = generate_report({}, profile(df), UsageContext("Explore"), {"dimensions": []})
        html = dataset_plots_html(report)
        parser = ImageParser()
        parser.feed(html)
        self.assertNotIn("script", parser.tags)
        self.assertIn("&lt;script&gt;", html)
        self.assertEqual(len(parser.images), 2)

    def test_nested_and_constant_categories_are_omitted(self):
        report = self.make_report()
        report["profile"]["columns"] = {
            "nested": {"unique_count": 2, "top_values": [{"value": [1, 2], "count": 2}]},
            "constant": {"unique_count": 1, "top_values": [{"value": "x", "count": 6}]},
        }
        report["profile"].pop("visualizations")
        html = dataset_plots_html(report)
        self.assertIn("No varying numeric columns", html)
        self.assertNotIn("Common categories", html)


if __name__ == "__main__":
    unittest.main()
