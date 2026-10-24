import json
import tempfile
import time
import tkinter
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.config import DIMENSION_WEIGHTS
from src.loading import load
from src.metadata import METADATA_ATTR
from src.profiling import profile
from src.ui.main_window import NO_TARGET, DataReadinessApp


def wait_for_evaluation(app, timeout=10):
    deadline = time.time() + timeout
    while app._busy and time.time() < deadline:
        app.update()


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
        wait_for_evaluation(app)
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
        wait_for_evaluation(self.app)
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
        wait_for_evaluation(app)

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
        wait_for_evaluation(app)

        self.assertIsNotNone(app.result)
        self.assertEqual(app.result["weight_source"], "study_defaults")
        self.assertIsNone(app.dimension_weights)
        self.assertIsNone(app.dimension_cards["Class Balance"].slider)

    def test_context_displays_metadata_coverage_and_selected_target_status(self):
        app = self.app
        app.df.attrs[METADATA_ATTR] = {
            "source": "sample.csv.metadata.json", "metadata": {
                "columns": {"feature": {"description": "Input value"}},
                "documentation": {
                    "target_definition": {"column": "target", "description": "Class label"},
                },
                "provenance": {"origin": "Experiment archive"},
            },
        }
        app._save_context(navigate=False)
        self.assertIn("50%", app.evidence_labels["variable_descriptions"].cget("text"))
        self.assertIn("Documented", app.evidence_labels["target_definition"].cget("text"))
        self.assertIn("Documented", app.evidence_labels["origin"].cget("text"))

        app.target_menu.set(NO_TARGET)
        app._save_context(navigate=False)
        self.assertEqual(app.evidence_labels["target_definition"].cget("text"), "Not applicable")

        app.df.attrs.clear()
        app._reset_context_controls()
        self.assertIn("Missing", app.evidence_labels["origin"].cget("text"))
        self.assertIn("No metadata selected", app.metadata_status.cget("text"))

    def upload_metadata(self, metadata):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "chosen-description.json"
        path.write_text(json.dumps(metadata), encoding="utf-8")
        with patch("src.ui.main_window.filedialog.askopenfilename", return_value=str(path)):
            self.app._load_metadata()
        self.assertTrue(self.app._busy)
        self.assertEqual(self.app.metadata_button.cget("state"), "disabled")
        wait_for_evaluation(self.app)
        self.assertFalse(self.app._busy)
        return path

    def test_metadata_picker_invalidates_results_and_preserves_context(self):
        app = self.app
        context, dataset_profile = app.context, app.dataset_profile
        path = self.upload_metadata({
            "schema_version": "1", "columns": {"feature": {"description": "Input"}},
            "provenance": {"origin": "Test archive"},
        })
        self.assertEqual(app.info["metadata_file"], path.name)
        self.assertIn(path.name, app.metadata_status.cget("text"))
        self.assertIn("50%", app.evidence_labels["variable_descriptions"].cget("text"))
        self.assertIn("Documented", app.evidence_labels["origin"].cget("text"))
        self.assertFalse(app.provenance_vars["origin"].get())
        self.assertIs(app.context, context)
        self.assertIs(app.dataset_profile, dataset_profile)
        self.assertIsNone(app.result)
        self.assertEqual(app.export_button.cget("state"), "disabled")
        self.assertEqual(app.remove_metadata_button.cget("state"), "normal")

    def test_metadata_picker_cancellation_preserves_current_results(self):
        result = self.app.result
        with patch("src.ui.main_window.filedialog.askopenfilename", return_value=""):
            self.app._load_metadata()
        self.assertIs(self.app.result, result)
        self.assertFalse(self.app._busy)

    def test_checkbox_changes_update_status_and_unchecking_restores_json(self):
        app = self.app
        self.upload_metadata({"schema_version": "1", "columns": {"feature": {"description": "Input"}}})
        checkbox = next(widget for widget in app.documentation_frame.winfo_children()
                        if widget.cget("text") == "Variable descriptions")
        checkbox.toggle()
        self.assertIn("Self reported", app.evidence_labels["variable_descriptions"].cget("text"))
        self.assertIn("100%", app.evidence_labels["variable_descriptions"].cget("text"))
        app._evaluate()
        wait_for_evaluation(app)
        documentation = next(item for item in app.result["dimensions"] if item["dimension"] == "Documentation")
        self.assertEqual(documentation["indicators"][0]["value"], 100)

        checkbox.toggle()
        self.assertIn("50%", app.evidence_labels["variable_descriptions"].cget("text"))
        self.assertIsNone(app.result)
        self.assertEqual(app.export_button.cget("state"), "disabled")

    def test_removing_metadata_keeps_checkbox_confirmations(self):
        app = self.app
        self.upload_metadata({"schema_version": "1", "provenance": {"origin": "Test archive"}})
        app.provenance_vars["collector"].set(True)
        app._evaluate()
        wait_for_evaluation(app)
        app.remove_metadata_button.invoke()
        self.assertIsNone(app.result)
        self.assertIsNone(app.info["metadata_file"])
        self.assertTrue(app.provenance_vars["collector"].get())
        self.assertIn("Missing", app.evidence_labels["origin"].cget("text"))
        self.assertIn("Self reported", app.evidence_labels["collector"].cget("text"))
        self.assertEqual(app.remove_metadata_button.cget("state"), "disabled")
        app._evaluate()
        wait_for_evaluation(app)
        provenance = next(item for item in app.result["dimensions"] if item["dimension"] == "Provenance")
        self.assertEqual(provenance["score"], 20)

    def test_loading_a_new_dataset_clears_metadata_and_checkboxes(self):
        app = self.app
        self.upload_metadata({"schema_version": "1", "provenance": {"origin": "Test archive"}})
        app.provenance_vars["collector"].set(True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replacement.csv"
            path.write_text("feature,target\n2,0\n3,1\n")
            df, info = load(path)
            app._dataset_loaded((df, info, profile(df)))
        self.assertIsNone(app.info["metadata_file"])
        self.assertFalse(app.provenance_vars["collector"].get())
        self.assertIn("No metadata selected", app.metadata_status.cget("text"))
        self.assertEqual(app.remove_metadata_button.cget("state"), "disabled")

    def test_invalid_metadata_replacement_discards_previous_json(self):
        app = self.app
        self.upload_metadata({"schema_version": "1", "provenance": {"origin": "Test archive"}})
        app.provenance_vars["collector"].set(True)
        self.upload_metadata({"schema_version": "unsupported"})
        self.assertTrue(app.info["metadata_warnings"])
        self.assertIn("schema_version", app.metadata_status.cget("text"))
        self.assertIn("Missing", app.evidence_labels["origin"].cget("text"))
        self.assertIn("Self reported", app.evidence_labels["collector"].cget("text"))
        self.assertIsNone(app.result)


if __name__ == "__main__":
    unittest.main()
