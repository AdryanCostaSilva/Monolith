"""Exercise real Tk controls, background operations, and the existing app lifecycle."""

import json
import tempfile
import time
import tkinter
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from src.profiling import profile
from src.ui.main_window import PREPARATION_TAB, RESULTS_TAB, DataReadinessApp
from src.ui.preparation_page import STEPS


class PreparationControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = DataReadinessApp()
        except tkinter.TclError as error:
            raise unittest.SkipTest(str(error)) from error
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.update()
        for job in cls.app.tk.call("after", "info"):
            cls.app.tk.call("after", "cancel", job)
        cls.app.destroy()

    def wait(self):
        deadline = time.monotonic() + 20
        while self.app._busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertFalse(self.app._busy, "Background operation timed out")

    def setUp(self):
        self.df = pd.DataFrame({"income": [1., 2., 3., 4., 100., np.nan],
                                "city": [" SP ", "sp", "RJ", "RJ", "SP", None],
                                "target": [0, 0, 1, 1, 1, 0]})
        info = {"file": "sample.csv", "format": "csv", "rows": 6, "columns": 3}
        self.app._dataset_loaded((self.df, info, profile(self.df)))
        self.app.goal_entry.insert(0, "Predict a class")
        self.app.task_menu.set("classification")
        self.app.target_menu.set("target")
        self.app._evaluate()
        self.wait()
        self.page = self.app.preparation_page
        self.page.category_menu.set("Outliers")
        self.page._choose_category("Outliers")
        self.wait()
        self.app.tabs.set(PREPARATION_TAB)

    def test_preview_apply_compare_undo_preserve_original_results(self):
        baseline = self.app.result
        original = self.df.copy()
        self.page.preview_button.invoke()
        self.assertTrue(self.app._busy)
        self.assertEqual(self.app.load_button.cget("state"), "disabled")
        self.wait()
        self.assertEqual(self.page.preview_change.changed_cells, 1)
        self.assertEqual(len(self.page.canvas.figure.axes), 2)
        self.assertEqual(self.page.apply_button.cget("state"), "normal")
        self.page.apply_button.invoke()
        self.wait()
        self.assertEqual(len(self.page.session.history), 1)
        self.assertEqual(self.page.apply_button.cget("state"), "disabled")
        self.assertAlmostEqual(self.page.session.working["income"].iloc[4], 7)
        self.page.compare_button.invoke()
        self.wait()
        self.assertIsNotNone(self.page.comparison)
        self.assertIn("Original:", self.page.comparison_text.cget("text"))
        self.assertEqual(self.app.result, baseline)
        assert_frame_equal(self.app.df, original)
        self.page.undo_button.invoke()
        self.wait()
        assert_frame_equal(self.page.session.working, original)
        self.assertIsNone(self.page.comparison)

    def test_selection_change_invalidates_preview_and_target_cannot_be_transformed(self):
        self.page.preview_button.invoke()
        self.wait()
        self.page.column_menu.set("target")
        self.page._selection_changed()
        self.wait()
        self.assertIsNone(self.page.preview_change)
        self.assertEqual(self.page.apply_button.cget("state"), "disabled")
        self.assertEqual(self.page.preview_button.cget("state"), "disabled")

    def test_new_dataset_and_changed_target_clear_preparation(self):
        self.page.preview_button.invoke()
        self.wait()
        self.page.apply_button.invoke()
        self.wait()
        self.app.target_menu.set("income")
        self.app._save_context(navigate=False)
        self.assertFalse(self.page.session.history)
        assert_frame_equal(self.page.session.working, self.df)
        self.assertIn("Target changed", self.page.status.cget("text"))
        self.page.set_dataset()
        self.assertIsNone(self.page.session)
        self.assertFalse(self.page.canvas.get_tk_widget().winfo_manager())
        self.assertEqual(self.page.preview_button.cget("state"), "disabled")

    def test_export_and_weight_change_invalidate_stale_comparison(self):
        self.page.preview_button.invoke()
        self.wait()
        self.page.apply_button.invoke()
        self.wait()
        self.page.compare_button.invoke()
        self.wait()
        self.app._change_dimension_weight("Documentation", 50)
        self.assertIsNone(self.page.comparison)
        self.assertEqual(self.page.dimension_weights["Documentation"], 50)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "prepared.csv"
            with patch("src.ui.preparation_page.filedialog.asksaveasfilename", return_value=str(output)):
                self.page.export_button.invoke()
            self.wait()
            self.assertTrue(output.exists())
            metadata = json.loads(output.with_name("prepared_preparation.json").read_text(encoding="utf-8"))
            self.assertIsNone(metadata["comparison"])
            self.assertEqual(len(metadata["steps"]), 1)

    def test_export_cannot_overwrite_source(self):
        self.page.preview_button.invoke()
        self.wait()
        self.page.apply_button.invoke()
        self.wait()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "source.csv"
            output.write_text("original data", encoding="utf-8")
            self.page.source_path = output
            with patch("src.ui.preparation_page.filedialog.asksaveasfilename", return_value=str(output)):
                self.page.export_button.invoke()
            self.assertFalse(self.app._busy)
            self.assertEqual(output.read_text(encoding="utf-8"), "original data")
            self.assertIn("preserve the original", self.page.status.cget("text"))

    def test_existing_results_navigation_and_missing_value_chart(self):
        self.app.tabs.set(RESULTS_TAB)
        self.app.prepare_button.invoke()
        self.assertEqual(self.app.tabs.get(), PREPARATION_TAB)
        self.page.category_menu.set("Missing values")
        self.page._choose_category("Missing values")
        self.wait()
        self.assertEqual(self.page.chart_view.get(), "Missing values")
        self.page.preview_button.invoke()
        self.wait()
        self.assertEqual(self.page.preview_change.changed_cells, 1)
        self.page.apply_button.invoke()
        self.wait()
        self.page.reset_button.invoke()
        self.wait()
        self.assertFalse(self.page.session.history)
        assert_frame_equal(self.page.session.working, self.df)

    def test_theme_and_chart_switches_reuse_the_live_canvas(self):
        import customtkinter as ctk

        canvas = self.page.canvas
        errors = []
        previous_handler = self.app.report_callback_exception
        previous_mode = ctk.get_appearance_mode()
        self.app.report_callback_exception = lambda *error: errors.append(error)
        try:
            canvas.get_tk_widget().focus_set()
            for mode in ("Dark", "Light"):
                ctk.set_appearance_mode(mode)
                self.app.update()
                self.assertIs(self.page.canvas, canvas)
                self.assertTrue(canvas.get_tk_widget().winfo_exists())
            self.page.chart_view.set("Target balance")
            self.page._draw_chart()
            self.assertIs(self.page.canvas, canvas)
            self.assertEqual(len(canvas.figure.axes), 1)
            self.assertFalse(errors)
        finally:
            ctk.set_appearance_mode(previous_mode)
            self.app.report_callback_exception = previous_handler

    def test_guided_navigation_keeps_inspection_read_only_and_normalization_separate(self):
        self.page._choose_step(STEPS[0])
        self.wait()
        self.assertEqual(self.page.step, 0)
        self.assertFalse(self.page.preview_button.grid_info())
        self.assertFalse(self.page.category_menu.grid_info())
        self.page.next_button.invoke()
        self.wait()
        self.assertEqual(self.page.step, 1)
        self.assertNotIn("Normalization", self.page.category_menu.cget("values"))
        self.page.next_button.invoke()
        self.wait()
        self.assertEqual(self.page.step, 2)
        self.assertEqual(self.page.category_menu.get(), "Normalization")
        self.assertFalse(self.page.category_menu.grid_info())
        self.page.preview_button.invoke()
        self.wait()
        self.assertEqual(self.page.preview_change.operation.action, "minmax")
        self.assertEqual(self.page.next_button.cget("state"), "disabled")
        self.page.apply_button.invoke()
        self.wait()
        self.assertEqual(len(self.page.session.history), 1)
        self.page.next_button.invoke()
        self.assertEqual(self.page.step, 3)
        self.assertTrue(self.page.review_frame.grid_info())
        self.assertFalse(self.page.workspace.grid_info())
        self.page.compare_button.invoke()
        self.wait()
        self.page.review_mode.set("Table")
        self.page._draw_review()
        self.assertTrue(self.page.comparison_table.grid_info())
        self.assertEqual(len(self.page.comparison_table.get_children()), 6)
        assert_frame_equal(self.app.df, self.df)

    def test_navigation_discards_unapplied_preview_without_mutating_working_copy(self):
        self.page.preview_button.invoke()
        self.wait()
        self.page._choose_step(STEPS[2])
        self.wait()
        self.assertIsNone(self.page.preview_change)
        self.assertFalse(self.page.session.history)
        assert_frame_equal(self.page.session.working, self.df)

    def test_metadata_selection_invalidates_preparation_comparison(self):
        self.page.preview_button.invoke()
        self.wait()
        self.page.apply_button.invoke()
        self.wait()
        self.page.compare_button.invoke()
        self.wait()
        self.assertIsNotNone(self.page.comparison)
        self.app._metadata_loaded({"source": "updated.json", "dataset_sha256": "source-hash",
                                   "metadata": {"schema_version": "1"}, "warnings": []})
        self.assertIsNone(self.page.comparison)
        self.assertEqual(len(self.page.session.history), 1)

    def test_duplicate_preview_displays_both_source_rows_and_all_columns(self):
        from src.preparation import PreparationSession

        df = pd.DataFrame({"income": [5., 10., 5.], "city": ["RJ", "SP", "RJ"], "target": [0, 1, 0]})
        self.page.session = PreparationSession(df)
        self.page.session.set_target("target")
        self.page._choose_category("Duplicates")
        self.wait()
        self.page.preview_button.invoke()
        self.wait()
        children = self.page.table.get_children()
        self.assertEqual(self.page.table.item(children[0], "values")[:2], ("4", "2"))
        self.assertEqual(self.page.table.heading("row", "text"), "Remove source row")
        self.assertTrue(self.page.pair_frame.grid_info())
        self.assertEqual(len(self.page.duplicate_values.get_children()), 3)
        for item in self.page.duplicate_values.get_children():
            values = self.page.duplicate_values.item(item, "values")
            self.assertEqual(values[1], values[2])
        self.page.pair_mode.set("Original file")
        self.page._duplicate_selected()
        self.assertIn("Original", self.page.pair_note.cget("text"))
        self.page.apply_button.invoke()
        self.wait()
        self.assertEqual(len(self.page.session.working), 2)
        self.assertFalse(self.page.pair_frame.grid_info())


if __name__ == "__main__":
    unittest.main()
