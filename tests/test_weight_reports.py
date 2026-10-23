import json
import tempfile
import unittest
from pathlib import Path

from src.aggregation import aggregate
from src.context import UsageContext
from src.evaluation.base import indicator, result
from src.reporting import export_html, export_json, generate_report


class WeightReportTests(unittest.TestCase):
    def test_custom_weights_are_recorded_in_json_and_html(self):
        dimensions = [
            result("Completeness", [indicator("Filled", 80)]),
            result("Documentation", [indicator("Documented", 0)]),
            result("Class Balance", [], applicable=False),
        ]
        evaluation = aggregate(
            dimensions, "regression", {"Completeness": 1, "Documentation": 3}
        )
        context = UsageContext("Predict a continuous value", task_type="regression")
        report = generate_report({}, {"dataset": {}}, context, evaluation)

        with tempfile.TemporaryDirectory() as directory:
            json_path = export_json(report, Path(directory) / "report.json")
            html_path = export_html(report, Path(directory) / "report.html")
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")

        self.assertEqual(saved["result"], evaluation)
        self.assertIn("Weighting: Custom weights", html)
        self.assertIn("Overall weight: 1 (25.00%", html)
        self.assertIn("Overall weight: 3 (75.00%", html)
        self.assertIn("Class Balance: Not applicable", html)


if __name__ == "__main__":
    unittest.main()
