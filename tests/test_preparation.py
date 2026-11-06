import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
from pandas.testing import assert_frame_equal

from src.context import UsageContext
from src.preparation import Operation, PreparationSession, transform
from src.preparation.inspection import inspect_frame
from src.preparation.transforms import duplicate_mask
from src.ui.preparation_charts import CHART_VIEWS, preparation_figure, readiness_figure


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({"age": [20., 30., 40., np.nan], "city": [" SP ", "sp", None, "RJ"],
                                "target": [0, 1, 0, 1]})

    def test_preview_is_nonmutating_apply_is_explicit_and_undo_replays(self):
        original = self.df.copy(deep=True)
        session = PreparationSession(self.df)
        change = session.preview(Operation("fill_median", "age"))
        self.assertEqual(change.changed_cells, 1)
        self.assertEqual(change.data["age"].iloc[-1], 30)
        assert_frame_equal(self.df, original)
        assert_frame_equal(session.working, original)
        session.apply()
        filled = session.working.copy()
        session.preview(Operation("minmax", "age"))
        session.apply()
        np.testing.assert_allclose(session.working["age"], [0, .5, 1, .5])
        session.undo()
        assert_frame_equal(session.working, filled)
        session.undo()
        assert_frame_equal(session.working, original)
        self.assertFalse(session.history)
        assert_frame_equal(self.df, original)

    def test_apply_requires_fresh_preview_and_noops_are_not_recorded(self):
        session = PreparationSession(self.df)
        with self.assertRaises(ValueError):
            session.apply()
        session.preview(Operation("duplicates"))
        with self.assertRaises(ValueError):
            session.apply()
        session.preview(Operation("trim", "city"))
        session.reset()
        with self.assertRaises(ValueError):
            session.apply()

    def test_target_is_protected_and_new_target_resets_prepared_features(self):
        session = PreparationSession(self.df)
        session.set_target("target")
        with self.assertRaisesRegex(ValueError, "target"):
            session.preview(Operation("minmax", "target"))
        session.preview(Operation("minmax", "age"))
        session.apply()
        session.set_target("age")
        assert_frame_equal(session.working, self.df)
        self.assertFalse(session.history)

    def test_scaling_preserves_nulls_and_fitted_parameters_can_be_reused(self):
        fit = transform(self.df, Operation("minmax", "age"))
        test = pd.DataFrame({"age": [25., 50., np.nan]})
        applied = transform(test, fit.operation)
        np.testing.assert_allclose(applied.data["age"], [.25, 1.5, np.nan], equal_nan=True)
        self.assertTrue(pd.isna(fit.data["age"].iloc[-1]))
        standardized = transform(self.df, Operation("standardize", "age")).data["age"]
        self.assertAlmostEqual(standardized.mean(), 0)
        self.assertAlmostEqual(standardized.std(ddof=0), 1)

    def test_scaling_handles_large_and_tiny_finite_values(self):
        for values in ([-1e308, 0, 1e308], [1e-300, 2e-300, 3e-300]):
            df = pd.DataFrame({"x": values})
            change = transform(df, Operation("minmax", "x"))
            np.testing.assert_allclose(change.data["x"], [0, .5, 1])
            self.assertTrue(np.isfinite(transform(df, Operation("standardize", "x")).data["x"]).all())

    def test_invalid_numeric_columns_fail_without_mutation(self):
        for values in ([1, np.inf], [1, 1], [np.nan, np.nan], [True, False], ["1", "2"]):
            df = pd.DataFrame({"x": values})
            original = df.copy()
            with self.assertRaises(ValueError):
                transform(df, Operation("minmax", "x"))
            assert_frame_equal(df, original)

    def test_fractional_median_supports_nullable_integer_and_arrow(self):
        for dtype in ("Int64", "int64[pyarrow]"):
            df = pd.DataFrame({"x": pd.Series([1, 2, None], dtype=dtype)})
            change = transform(df, Operation("fill_median", "x"))
            self.assertEqual(change.data["x"].iloc[-1], 1.5)

    def test_missing_and_text_actions_have_exact_counts(self):
        mode = transform(self.df, Operation("fill_mode", "target"))
        self.assertEqual(mode.changed_cells, 0)
        drop = transform(self.df, Operation("drop_missing", "age"))
        self.assertEqual(drop.removed_rows, 1)
        self.assertEqual(drop.changed_cells, 0)
        text = transform(self.df, Operation("casefold", "city"))
        self.assertEqual(text.changed_cells, 2)
        self.assertEqual(text.data["city"].tolist()[:2], ["sp", "sp"])
        self.assertTrue(pd.isna(text.data["city"].iloc[2]))
        with self.assertRaisesRegex(ValueError, "every row"):
            transform(pd.DataFrame({"x": [None, None]}), Operation("drop_missing", "x"))

    def test_outlier_capping_and_removal_report_rows_and_keep_missing(self):
        df = pd.DataFrame({"x": [1., 2., 3., 4., 100., np.nan], "y": range(6)})
        clipped = transform(df, Operation("clip_outliers", "x"))
        self.assertEqual(clipped.changed_cells, 1)
        self.assertAlmostEqual(clipped.data["x"].iloc[4], 7)
        self.assertTrue(pd.isna(clipped.data["x"].iloc[5]))
        removed = transform(df, Operation("drop_outliers", "x"))
        self.assertEqual(removed.removed_rows, 1)
        self.assertEqual(removed.data["y"].tolist(), [0, 1, 2, 3, 5])

    def test_capped_boundary_is_not_reflagged_by_scaling_or_scoring(self):
        from src.evaluation.quality import _count_outliers

        df = pd.DataFrame({"income": [2200., 2700., 3000., 3200., 3500., 4000., 4200.,
                                      4500., 5000., 5200., 25000., np.nan]})
        self.assertEqual(_count_outliers(df["income"]), (1, 11))
        capped = transform(df, Operation("clip_outliers", "income")).data
        self.assertEqual(_count_outliers(capped["income"]), (0, 11))
        for method in ("minmax", "standardize"):
            scaled = transform(capped, Operation(method, "income")).data
            self.assertEqual(_count_outliers(scaled["income"]), (0, 11))
            details = inspect_frame(scaled, "income")
            self.assertEqual(details["outliers"], 0)
            self.assertFalse(details["box"]["fliers"])

    def test_fitted_iqr_limits_still_flag_future_extreme_values(self):
        fitted = transform(pd.DataFrame({"x": [1., 2., 3., 4., 100.]}), Operation("drop_outliers", "x"))
        future = pd.DataFrame({"x": [1., 10., 1e308]})
        change = transform(future, fitted.operation)
        self.assertEqual(change.removed_rows, 2)
        self.assertEqual(change.data["x"].tolist(), [1.])

    def test_inspection_and_scoring_agree_when_infinite_measurements_exist(self):
        from src.evaluation.quality import _count_outliers

        df = pd.DataFrame({"x": [1., 2., 3., 4., 100., np.inf, np.nan]})
        details = inspect_frame(df, "x")
        self.assertEqual(details["outliers"], _count_outliers(df["x"])[0])
        self.assertIn("Infinite", details["note"])
        self.assertTrue(any(row["value"] == "inf" for row in details["records"]))

    def test_normalization_preview_uses_the_same_number_of_histogram_bins(self):
        df = pd.DataFrame({"x": np.arange(30, dtype=float)})
        before = inspect_frame(df, "x")
        after = inspect_frame(transform(df, Operation("minmax", "x")).data, "x")
        figure = preparation_figure(before, after)
        self.assertEqual(len(figure.axes[0].patches), 12)
        self.assertEqual(len(figure.axes[1].patches), 12)

    def test_duplicate_removal_supports_nested_parquet_values(self):
        nested = pd.Series([[1, 2], [1, 2], None, None], dtype=pd.ArrowDtype(pa.list_(pa.int64())))
        df = pd.DataFrame({"nested": nested, "x": [1, 1, 2, 2]})
        self.assertEqual(duplicate_mask(df).tolist(), [False, True, False, True])
        change = transform(df, Operation("duplicates"))
        self.assertEqual(change.removed_rows, 2)
        self.assertEqual(len(change.data), 2)
        self.assertEqual([(row["source_row"], row["matched_source_row"]) for row in change.examples], [(3, 2), (5, 4)])

    def test_duplicate_preview_links_to_first_matching_source_row(self):
        df = pd.DataFrame({"x": [10, 20, 10, 10], "label": [0, 1, 0, 0]}, index=[99, 99, 7, 1000])
        session = PreparationSession(df)
        change = session.preview(Operation("duplicates"))
        self.assertEqual([(row["source_row"], row["matched_source_row"]) for row in change.examples], [(4, 2), (5, 2)])
        details = session.duplicate_details(0)
        self.assertEqual(details["kept_source_row"], 2)
        self.assertEqual(details["removed_source_row"], 4)
        self.assertTrue(all(column["kept"] == column["removed"] for column in details["columns"]))
        self.assertEqual(details["columns"][1]["kept"], "0")
        assert_frame_equal(session.working, df)

    def test_source_rows_survive_earlier_removal_undo_and_reset(self):
        df = pd.DataFrame({"x": [1., np.nan, 2., 1., 1.], "city": ["a", "gone", "b", "a", "a"]},
                          index=[50, 50, 300, 900, 999])
        session = PreparationSession(df)
        session.preview(Operation("drop_missing", "x"))
        session.apply()
        self.assertEqual(session.source_rows.tolist(), [2, 4, 5, 6])
        change = session.preview(Operation("duplicates"))
        self.assertEqual(change.examples[0]["row"], 3)
        self.assertEqual(change.examples[0]["source_row"], 5)
        self.assertEqual(change.examples[0]["matched_source_row"], 2)
        session.apply()
        self.assertEqual(session.source_rows.tolist(), [2, 4])
        session.undo()
        self.assertEqual(session.source_rows.tolist(), [2, 4, 5, 6])
        session.reset()
        self.assertEqual(session.source_rows.tolist(), [2, 3, 4, 5, 6])

    def test_duplicate_detail_can_show_original_values_before_text_cleanup(self):
        df = pd.DataFrame({"city": [" SP ", "sp"], "value": [10, 10]})
        session = PreparationSession(df)
        session.preview(Operation("casefold", "city"))
        session.apply()
        session.preview(Operation("duplicates"))
        prepared = session.duplicate_details(0)["columns"][0]
        original = session.duplicate_details(0, original=True)["columns"][0]
        self.assertEqual(prepared["kept"], prepared["removed"])
        self.assertNotEqual(original["kept"], original["removed"])
        self.assertIn(" SP ", original["kept"])
        session.discard_preview()
        with self.assertRaises(ValueError):
            session.duplicate_details(0)

    def test_comparison_uses_same_context_and_weights_and_preserves_target(self):
        session = PreparationSession(self.df)
        session.set_target("target")
        session.preview(Operation("fill_median", "age"))
        session.apply()
        context = UsageContext("Predict", "classification", "target")
        comparison = session.compare(context, {"Completeness": 1})
        self.assertGreater(comparison["prepared"]["score"], comparison["original"]["score"])
        self.assertEqual(comparison["original"]["weight_source"], comparison["prepared"]["weight_source"])
        pd.testing.assert_series_equal(session.working["target"], self.df["target"])

    def test_export_roundtrips_and_saves_fitted_history_in_all_supported_formats(self):
        session = PreparationSession(self.df)
        session.preview(Operation("minmax", "age"))
        session.apply()
        with tempfile.TemporaryDirectory() as directory:
            for extension in ("csv", "xlsx", "parquet"):
                dataset, metadata = session.export(Path(directory) / f"prepared.{extension}", source="original.csv",
                                                    context=UsageContext("Analyze"))
                self.assertTrue(dataset.is_file())
                manifest = json.loads(metadata.read_text(encoding="utf-8"))
                self.assertEqual(manifest["steps"][0]["action"], "minmax")
                self.assertIn("divisor", manifest["steps"][0]["parameters"])
                reader = {"csv": pd.read_csv, "xlsx": pd.read_excel, "parquet": pd.read_parquet}[extension]
                np.testing.assert_allclose(reader(dataset)["age"], [0, .5, 1, np.nan], equal_nan=True)

    def test_inspection_bounds_samples_and_charts_render_without_pyplot(self):
        df = pd.DataFrame({"x": np.r_[np.arange(12000), 1e6], "target": [0] * 12000 + [1]})
        before = inspect_frame(df, "x", "target")
        self.assertEqual(len(before["values"]), 10000)
        self.assertEqual(before["outliers"], 1)
        self.assertEqual(before, inspect_frame(df, "x", "target"))
        after = inspect_frame(transform(df, Operation("drop_outliers", "x")).data, "x", "target")
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        for view in CHART_VIEWS:
            figure = preparation_figure(before, after, view=view, dark=True)
            FigureCanvasAgg(figure).draw()
            self.assertTrue(figure.axes)

    def test_category_share_includes_missing_rows_and_declines_high_cardinality(self):
        df = pd.DataFrame({"city": ["SP", "SP", "RJ", None]})
        data = inspect_frame(df, "city")
        self.assertEqual(sum(item["count"] for item in data["category_share"]), 4)
        self.assertEqual(len(data["category_share"]), 3)
        many = inspect_frame(pd.DataFrame({"x": list("abcdefgh")}), "x")
        self.assertFalse(many["category_share"])
        self.assertIn("five", many["category_share_note"])

    def test_donut_labels_counts_directly_without_a_legend(self):
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        before = inspect_frame(pd.DataFrame({"city": ["SP", "SP", "RJ", None]}), "city")
        for view in ("Filled / missing", "Category share"):
            figure = preparation_figure(before, view=view)
            FigureCanvasAgg(figure).draw()
            self.assertIsNone(figure.axes[0].get_legend())
            labels = " ".join(text.get_text() for text in figure.axes[0].texts)
            self.assertIn("25.0%", labels)
            self.assertIn("4\nrows", labels)

    def test_comparison_uses_latest_source_metadata_for_both_versions(self):
        from src.metadata import METADATA_ATTR

        session = PreparationSession(self.df)
        session.preview(Operation("fill_median", "age"))
        session.apply()
        evidence = {"source": "new.json", "dataset_sha256": "source-hash", "warnings": [],
                    "metadata": {"provenance": {"origin": "Research archive"}}}
        self.df.attrs[METADATA_ATTR] = evidence
        comparison = session.compare(UsageContext("Analyze"))
        for dimension in ("Documentation", "Provenance"):
            old = next(item for item in comparison["original"]["dimensions"] if item["dimension"] == dimension)
            new = next(item for item in comparison["prepared"]["dimensions"] if item["dimension"] == dimension)
            self.assertEqual(old, new)
            self.assertEqual(new["assessment"]["source"], "new.json")
        self.assertNotIn(METADATA_ATTR, session.working.attrs)

    def test_preparation_text_and_primary_action_contrast_in_both_themes(self):
        from src.ui.theme import colors

        def luminance(color):
            rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in rgb]
            return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))

        def contrast(first, second):
            high, low = sorted((luminance(first), luminance(second)), reverse=True)
            return (high + .05) / (low + .05)

        for dark in (False, True):
            palette = colors(dark)
            self.assertGreaterEqual(contrast(palette["accent"], palette["on_accent"]), 4.5)
            for foreground in ("ink", "muted"):
                for background in ("page", "surface"):
                    self.assertGreaterEqual(contrast(palette[foreground], palette[background]), 4.5)
            self.assertGreaterEqual(contrast(palette["context"], palette["surface"]), 3)


if __name__ == "__main__":
    unittest.main()
