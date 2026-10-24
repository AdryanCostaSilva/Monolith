import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.context import DOCUMENTATION_ITEMS, PROVENANCE_ITEMS, UsageContext
from src.engine import evaluate_dataset
from src.evaluation import evaluate_documentation, evaluate_provenance
from src.loading import load
from src.metadata import MAX_METADATA_BYTES, collect_metadata
from src.profiling import profile
from src.reporting import export_html, export_json, generate_report


def sample_metadata():
    return {
        "schema_version": "1",
        "columns": {
            "temperature": {"description": "Air temperature", "unit": "Celsius"},
            "fault": {"description": "Sensor fault", "categories": {"0": "OK", "1": "Fault"}},
        },
        "documentation": {
            "target_definition": {"column": "fault", "description": "Fault occurrence"},
            "data_collection": "Hourly sensor readings",
            "collection_period": {"start": "2026-01-01", "end": "2026-01-31"},
            "known_limitations": ["Single station"],
        },
        "provenance": {
            "origin": "Station A archive", "collector": "Operations team",
            "generation_period": {"start": "2026-01-01", "end": "2026-01-31"},
            "transformations": ["Raw export; none applied"], "version": "1.0",
        },
    }


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sample.csv"
        self.path.write_text("temperature,fault\n20,0\n21,1\n22,0\n23,1\n", encoding="utf-8")
        self.metadata_path = self.path.parent / "metadata" / "description.json"
        self.metadata_path.parent.mkdir()
        self.context = UsageContext("Predict faults", "classification", "fault")

    def write_metadata(self, metadata=None):
        self.metadata_path.write_text(json.dumps(metadata if metadata is not None else sample_metadata()), encoding="utf-8")

    def test_explicit_selection_earns_points_without_any_checkboxes(self):
        self.write_metadata()
        df, info = load(self.path, metadata_path=self.metadata_path)
        for evaluate in (evaluate_documentation, evaluate_provenance):
            dimension = evaluate(self.context, df)
            self.assertEqual(dimension["score"], 100)
            self.assertTrue(all(item["status"] == "documented" for item in dimension["indicators"]))
            self.assertFalse(any(item["self_reported"] for item in dimension["indicators"]))
        self.assertEqual(info["metadata_file"], self.metadata_path.name)
        self.assertEqual(info["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_checkboxes_receive_full_credit_without_metadata(self):
        df, _ = load(self.path)
        context = UsageContext("Explore", documentation=dict.fromkeys(DOCUMENTATION_ITEMS, True),
                               provenance=dict.fromkeys(PROVENANCE_ITEMS, True))
        for evaluate in (evaluate_documentation, evaluate_provenance):
            dimension = evaluate(context, df)
            self.assertEqual(dimension["score"], 100)
            self.assertTrue(all(item["status"] == "self_reported" for item in dimension["indicators"]))
            self.assertTrue(all(item["source"] == "User checkbox" for item in dimension["indicators"]))
            self.assertTrue(dimension["assessment"]["dataset_sha256"])

    def test_dataset_loading_does_not_search_for_metadata(self):
        self.path.with_name(self.path.name + ".metadata.json").write_text(json.dumps(sample_metadata()))
        df, info = load(self.path)
        self.assertIsNone(info["metadata_file"])
        self.assertFalse(info["metadata_warnings"])
        self.assertEqual(evaluate_documentation(self.context, df)["score"], 0)
        self.assertEqual(evaluate_provenance(self.context, df)["score"], 0)

    def test_each_checkbox_overrides_missing_invalid_and_partial_json(self):
        metadata = sample_metadata()
        metadata["columns"]["fault"] = {}
        metadata["documentation"]["data_collection"] = False
        metadata["documentation"].pop("collection_period")
        metadata["provenance"] = {"origin": False, "generation_period": "invalid"}
        self.write_metadata(metadata)
        df, _ = load(self.path, metadata_path=self.metadata_path)
        for group, items, evaluate in (
            ("documentation", DOCUMENTATION_ITEMS, evaluate_documentation),
            ("provenance", PROVENANCE_ITEMS, evaluate_provenance),
        ):
            baseline = evaluate(self.context, df)
            for item in items:
                with self.subTest(group=group, item=item):
                    context = deepcopy(self.context)
                    getattr(context, group)[item] = True
                    dimension = evaluate(context, df)
                    for before, after in zip(baseline["indicators"], dimension["indicators"]):
                        if after["item"] == item:
                            self.assertEqual(after["value"], 100)
                            self.assertEqual(after["status"], "self_reported")
                            self.assertEqual(after["source"], "User checkbox")
                            self.assertIs(after["evidence"], True)
                        else:
                            self.assertEqual(before, after)
                    getattr(context, group)[item] = False
                    self.assertEqual(evaluate(context, df), baseline)

    def test_invalid_json_does_not_disable_checkbox_confirmations(self):
        self.metadata_path.write_text("{")
        df, info = load(self.path, metadata_path=self.metadata_path)
        self.context.documentation["data_collection"] = True
        self.context.provenance["origin"] = True
        self.assertTrue(info["metadata_warnings"])
        self.assertEqual(evaluate_documentation(self.context, df)["score"], 16.67)
        self.assertEqual(evaluate_provenance(self.context, df)["score"], 20)

    def test_checked_target_definition_remains_excluded_without_target(self):
        context = UsageContext("Explore")
        context.documentation["target_definition"] = True
        dimension = evaluate_documentation(context)
        self.assertEqual(dimension["score"], 0)
        self.assertEqual(dimension["excluded_indicators"][0]["status"], "not_applicable")

    def test_column_coverage_uses_actual_columns_and_ignores_extras(self):
        metadata = sample_metadata()
        metadata["columns"]["fault"] = {"description": " ", "categories": {"0": ""}}
        metadata["columns"]["absent"] = {"description": "Unused", "unit": "m"}
        self.write_metadata(metadata)
        df, _ = load(self.path, metadata_path=self.metadata_path)
        dimension = evaluate_documentation(self.context, df)
        coverage = [item for item in dimension["indicators"] if item["field"] == "columns"]
        self.assertEqual([item["value"] for item in coverage], [50, 50])
        self.assertEqual([item["status"] for item in coverage], ["partial", "partial"])
        self.assertEqual(dimension["score"], 83.33)

    def test_target_definition_must_match_selected_existing_column(self):
        self.write_metadata()
        df, _ = load(self.path, metadata_path=self.metadata_path)
        for target in ("temperature", "not_a_column"):
            with self.subTest(target=target):
                context = UsageContext("Predict", "classification", target)
                definition = next(item for item in evaluate_documentation(context, df)["indicators"]
                                  if item["item"] == "target_definition")
                self.assertEqual(definition["value"], 0)
        dimension = evaluate_documentation(UsageContext("Explore"), df)
        self.assertEqual(dimension["score"], 100)
        self.assertEqual(len(dimension["indicators"]), 5)
        self.assertEqual(dimension["excluded_indicators"][0]["status"], "not_applicable")

    def test_bad_dates_booleans_empty_fields_and_wrong_types_get_no_credit(self):
        metadata = sample_metadata()
        metadata["documentation"].update({
            "data_collection": True, "known_limitations": [],
            "collection_period": {"start": "2026-02-30", "end": "2026-03-01"},
        })
        metadata["provenance"].update({
            "origin": " ", "collector": False, "version": 1,
            "transformations": [False],
            "generation_period": {"start": "2026-02-01", "end": "2026-01-01"},
        })
        self.write_metadata(metadata)
        df, _ = load(self.path, metadata_path=self.metadata_path)
        self.assertEqual(evaluate_documentation(self.context, df)["score"], 50)
        self.assertEqual(evaluate_provenance(self.context, df)["score"], 0)

    def test_malformed_metadata_is_visible_and_does_not_block_loading(self):
        for content in ("{", "[]", '{"schema_version": "2"}', "{}", "\ufeff{}"):
            with self.subTest(content=content):
                self.metadata_path.write_text(content, encoding="utf-8")
                df, info = load(self.path, metadata_path=self.metadata_path)
                self.assertTrue(info["metadata_warnings"])
                self.assertEqual(evaluate_documentation(self.context, df)["score"], 0)
        self.metadata_path.write_bytes(b" " * (MAX_METADATA_BYTES + 1))
        self.assertIn("2 MiB", collect_metadata(self.path, self.metadata_path)["warnings"][0])

    def test_wrong_section_types_are_missing_evidence(self):
        self.write_metadata({"schema_version": "1", "columns": [], "documentation": True, "provenance": []})
        df, _ = load(self.path, metadata_path=self.metadata_path)
        self.assertEqual(evaluate_documentation(self.context, df)["score"], 0)
        self.assertEqual(evaluate_provenance(self.context, df)["score"], 0)

    def test_checksum_binding_detects_changes_to_dataset(self):
        metadata = sample_metadata()
        metadata["dataset_sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.write_metadata(metadata)
        self.assertFalse(collect_metadata(self.path, self.metadata_path)["warnings"])
        self.path.write_text("temperature,fault\n25,1\n", encoding="utf-8")
        df, info = load(self.path, metadata_path=self.metadata_path)
        self.assertIn("does not match", info["metadata_warnings"][0])
        self.assertEqual(evaluate_provenance(self.context, df)["score"], 0)

    def test_json_and_html_preserve_evidence_escape_text_and_are_repeatable(self):
        metadata = sample_metadata()
        metadata["provenance"]["origin"] = "<script>publisher</script>"
        self.write_metadata(metadata)
        df, info = load(self.path, metadata_path=self.metadata_path)
        before = deepcopy(df.attrs)
        dataset_profile = profile(df)
        first = evaluate_dataset(df, self.context, dataset_profile)
        self.assertEqual(first, evaluate_dataset(df, self.context, dataset_profile))
        self.assertEqual(df.attrs, before)
        report = generate_report(info, dataset_profile, self.context, first)
        json_path = export_json(report, self.path.parent / "report.json")
        html_path = export_html(report, self.path.parent / "report.html")
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        provenance = next(item for item in saved["result"]["dimensions"] if item["dimension"] == "Provenance")
        self.assertEqual(provenance["indicators"][0]["evidence"], "<script>publisher</script>")
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;publisher&lt;/script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn(self.metadata_path.name, html)
        self.assertIn(info["sha256"], html)

    def test_exports_distinguish_checkbox_overrides_from_metadata_fallback(self):
        self.write_metadata()
        df, info = load(self.path, metadata_path=self.metadata_path)
        self.context.documentation["variable_descriptions"] = True
        self.context.provenance["collector"] = True
        dataset_profile = profile(df)
        report = generate_report(info, dataset_profile, self.context,
                                 evaluate_dataset(df, self.context, dataset_profile))
        saved = json.loads(export_json(report, self.path.parent / "report.json").read_text())
        dimensions = {item["dimension"]: item for item in saved["result"]["dimensions"]}
        descriptions = dimensions["Documentation"]["indicators"][0]
        self.assertEqual(descriptions["status"], "self_reported")
        self.assertEqual(descriptions["source"], "User checkbox")
        origin = dimensions["Provenance"]["indicators"][0]
        self.assertEqual(origin["source"], self.metadata_path.name)
        self.assertEqual(origin["status"], "documented")
        html = export_html(report, self.path.parent / "report.html").read_text()
        self.assertIn("User checkbox", html)
        self.assertIn("Checked items receive full credit", html)
        self.assertNotIn("do not contribute points", html)

    def test_metadata_selection_works_for_excel_and_parquet(self):
        self.write_metadata()
        df = pd.read_csv(self.path)
        for extension in ("xlsx", "parquet"):
            with self.subTest(extension=extension):
                path = self.path.with_suffix("." + extension)
                if extension == "xlsx":
                    df.to_excel(path, index=False)
                else:
                    df.to_parquet(path, index=False)
                loaded, _ = load(path, metadata_path=self.metadata_path)
                self.assertEqual(evaluate_documentation(self.context, loaded)["score"], 100)
                self.assertEqual(evaluate_provenance(self.context, loaded)["score"], 100)


if __name__ == "__main__":
    unittest.main()
