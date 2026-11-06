"""Working-copy lifecycle, reproducible history, comparison, and exports."""

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.engine import evaluate_dataset
from src.metadata import METADATA_ATTR
from src.preparation.transforms import transform
from src.profiling import profile


class PreparationSession:
    def __init__(self, original):
        # The host owns the immutable source. Allocate copies only for transformations.
        self.original = original
        self.working = original
        self.source_rows = np.arange(2, len(original) + 2)
        self.history = []
        self.revision = 0
        self.target = None
        self._preview = None

    def set_target(self, target):
        if target != self.target:
            # A previously transformed feature must never silently become a target.
            self.reset()
            self.target = target

    def discard_preview(self):
        self._preview = None

    def preview(self, operation):
        self.discard_preview()
        change = transform(self.working, operation, target=self.target, source_rows=self.source_rows)
        self._preview = (self.revision, change)
        return change

    def apply(self):
        if self._preview is None or self._preview[0] != self.revision:
            raise ValueError("Preview the current action before applying it.")
        change = self._preview[1]
        if not change.affected_rows:
            raise ValueError("This preview contains no changes to apply.")
        self.working = change.data
        self.source_rows = change.project_source_rows(self.source_rows)
        self.history.append(change.record())
        self.revision += 1
        self.discard_preview()

    def undo(self):
        if not self.history:
            return
        # Replay fitted operations instead of retaining a full dataframe per undo step.
        from src.preparation.transforms import Operation

        remaining = self.history[:-1]
        data = self.original
        source_rows = np.arange(2, len(self.original) + 2)
        for record in remaining:
            change = transform(data, Operation(record["action"], record["column"], record["parameters"]),
                               target=self.target, source_rows=source_rows)
            data = change.data
            source_rows = change.project_source_rows(source_rows)
        self.working = data
        self.source_rows = source_rows
        self.history = remaining
        self.revision += 1
        self.discard_preview()

    def reset(self):
        self.working = self.original
        self.source_rows = np.arange(2, len(self.original) + 2)
        self.history = []
        self.revision += 1
        self.discard_preview()

    def inspect(self, column, *, preview=False):
        from src.preparation.inspection import inspect_frame

        data, rows = self.working, self.source_rows
        if preview:
            change = self._current_preview()
            data, rows = change.data, change.project_source_rows(rows)
        return inspect_frame(data, column, self.target, source_rows=rows)

    def _current_preview(self):
        if self._preview is None or self._preview[0] != self.revision:
            raise ValueError("Create a fresh preview to inspect its records.")
        return self._preview[1]

    def duplicate_details(self, example_index, *, original=False):
        change = self._current_preview()
        if change.operation.action != "duplicates":
            raise ValueError("Preview duplicate removal to compare a matching pair.")
        example = change.examples[example_index]
        data = self.original if original else self.working
        kept = example["matched_source_row"] - 2 if original else example["matched_row"] - 1
        removed = example["source_row"] - 2 if original else example["row"] - 1
        return {
            "kept_source_row": example["matched_source_row"], "removed_source_row": example["source_row"],
            "kept_working_row": example["matched_row"], "removed_working_row": example["row"],
            "columns": [{"column": str(name), "kept": _cell_text(data.iat[kept, index]),
                         "removed": _cell_text(data.iat[removed, index])} for index, name in enumerate(data.columns)],
        }

    def compare(self, context, dimension_weights=None):
        """Use exactly the same context, weights, and engine for both versions."""
        # Metadata can be replaced after preparation started. Reuse the current
        # source evidence for both assessments without mutating either dataframe.
        prepared = self.working.copy(deep=False)
        prepared.attrs = deepcopy(self.original.attrs)
        return {
            label: evaluate_dataset(data, context, profile(data), dimension_weights=dimension_weights)
            for label, data in (("original", self.original), ("prepared", prepared))
        }

    def export(self, path, *, source, context, comparison=None):
        path = Path(path)
        if path.suffix.lower() not in {".csv", ".xlsx", ".parquet"}:
            raise ValueError("Choose a CSV, XLSX, or Parquet output file.")
        metadata_path = path.with_name(f"{path.stem}_preparation.json")
        manifest = {
            "source": source, "output": path.name,
            "original_rows": len(self.original), "prepared_rows": len(self.working),
            "context": asdict(context), "steps": self.history, "comparison": comparison,
            "source_metadata": deepcopy(self.original.attrs.get(METADATA_ATTR, {})),
            "metadata_note": "Uploaded metadata describes the source. Review units and categories after preparation.",
            "scaling_note": "Fit preparation parameters on training data only; reuse them for validation and test data.",
        }
        # Serialize before writing the dataset so invalid metadata cannot leave a partial export.
        payload = json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_value, allow_nan=False)
        if path.suffix.lower() == ".csv":
            self.working.to_csv(path, index=False, encoding="utf-8-sig")
        elif path.suffix.lower() == ".xlsx":
            self.working.to_excel(path, index=False)
        else:
            self.working.to_parquet(path, index=False)
        metadata_path.write_text(payload, encoding="utf-8")
        return path, metadata_path


def _json_value(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _cell_text(value):
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return "(missing)"
    return repr(value) if isinstance(value, str) else str(value)
