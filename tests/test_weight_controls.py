import tkinter
import unittest

import pandas as pd

from src.config import DIMENSION_WEIGHTS
from src.profiling import profile
from src.ui.main_window import NO_TARGET, DataReadinessApp


class WeightControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app = DataReadinessApp()
        except tkinter.TclError as error:
            raise unittest.SkipTest(f"Tk display unavailable: {error}") from error
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def setUp(self):
        app = self.app
        app._reset_results()
        app.df = pd.DataFrame({"feature": [1, 2, 3, 4], "target": [0, 0, 1, 1]})
        app.info = {"file": "sample.csv"}
        app.dataset_profile = profile(app.df)
        app.context = None
        app.dimension_weights = None
        app.weight_task_type = None
        app._reset_context_controls()
        app.goal_entry.insert(0, "Predict a class")
        app.task_menu.set("classification")
        app.target_menu.set("target")
        app._evaluate()
        app.update_idletasks()
        self.assertIsNotNone(app.result)

    def test_weights_are_collapsed_until_requested(self):
        self.assertFalse(self.app.weights_expanded)
        self.assertFalse(self.app.dimension_cards["Completeness"].controls.grid_info())

        self.app.weight_toggle.invoke()

        self.assertTrue(self.app.weights_expanded)
        self.assertTrue(self.app.dimension_cards["Completeness"].controls.grid_info())
        self.assertTrue(self.app.reset_weights_button.grid_info())

        self.app.weight_toggle.invoke()

        self.assertFalse(self.app.dimension_cards["Completeness"].controls.grid_info())
        self.assertFalse(self.app.reset_weights_button.grid_info())

    def test_slider_updates_score_and_reset_restores_defaults(self):
        app = self.app
        baseline = app.result
        app.weight_toggle.invoke()
        slider = app.dimension_cards["Documentation"].slider
        slider.set(75)
        slider.cget("command")(75)

        self.assertLess(app.result["score"], baseline["score"])
        self.assertEqual(app.dimension_weights["Documentation"], 75)
        self.assertIn("Custom weights", app.weight_source_label.cget("text"))
        self.assertIn("75.0", app.dimension_cards["Documentation"].weight_value.cget("text"))

        app.reset_weights_button.invoke()

        self.assertEqual(app.result, baseline)
        self.assertIsNone(app.dimension_weights)
        self.assertEqual(slider.get(), DIMENSION_WEIGHTS["classification"]["Documentation"])
        self.assertTrue(app.weights_expanded)
        self.assertEqual(app.reset_weights_button.cget("state"), "disabled")

    def test_regression_has_no_class_balance_slider(self):
        self.app.task_menu.set("regression")
        self.app._evaluate()
        self.app.weight_toggle.invoke()

        self.assertIsNone(self.app.dimension_cards["Class Balance"].slider)
        self.assertIsNone(self.app.result["dimensions"][2]["weight"])

    def test_last_positive_weight_cannot_be_set_to_zero(self):
        app = self.app
        weights = dict.fromkeys(DIMENSION_WEIGHTS["classification"], 0)
        weights["Data Quality"] = 1
        app._apply_dimension_weights(weights, sync_sliders=True)
        previous = app.result
        slider = app.dimension_cards["Data Quality"].slider
        slider.set(0)

        slider.cget("command")(0)

        self.assertEqual(app.result, previous)
        self.assertEqual(slider.get(), 1)
        self.assertIn("positive weight", app.weight_help.cget("text"))

    def test_task_change_uses_new_defaults(self):
        app = self.app
        app._change_dimension_weight("Documentation", 75)

        app.task_menu.set("regression")
        app._evaluate()

        self.assertIsNone(app.dimension_weights)
        self.assertEqual(app.result["weight_source"], "study_defaults")
        self.assertEqual(app.dimension_cards["Data Quality"].slider.get(), 33.7)
        self.assertIsNone(app.dimension_cards["Class Balance"].slider)

    def test_context_change_clears_stale_exportable_results(self):
        self.app.goal_entry.insert("end", " with a new goal")

        self.app._save_context(navigate=False)

        self.assertIsNone(self.app.result)
        self.assertEqual(self.app.export_button.cget("state"), "disabled")

    def test_removing_target_restores_defaults_when_class_balance_was_only_weight(self):
        app = self.app
        weights = dict.fromkeys(DIMENSION_WEIGHTS["classification"], 0)
        weights["Class Balance"] = 1
        app._apply_dimension_weights(weights, sync_sliders=True)

        app.target_menu.set(NO_TARGET)
        app._evaluate()

        self.assertIsNotNone(app.result)
        self.assertEqual(app.result["weight_source"], "study_defaults")
        self.assertIsNone(app.dimension_weights)
        self.assertIsNone(app.dimension_cards["Class Balance"].slider)


if __name__ == "__main__":
    unittest.main()
