"""Explicit transformations. Inputs are never mutated; fitted parameters are recorded."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype, is_object_dtype, is_string_dtype

from src.profiling.values import factorize_column, is_nested
from src.profiling.outliers import iqr_details, outside_bounds


@dataclass(frozen=True)
class Operation:
    action: str
    column: object = None
    parameters: dict = field(default_factory=dict)


@dataclass
class Change:
    data: pd.DataFrame
    operation: Operation
    affected_rows: int
    changed_cells: int
    removed_rows: int
    examples: list
    kept_positions: np.ndarray | None = None

    def project_source_rows(self, source_rows):
        """Keep source references separate from dataset columns and pandas indexes."""
        return source_rows if self.kept_positions is None else source_rows[self.kept_positions]

    def record(self):
        return {
            "action": self.operation.action,
            "column": self.operation.column,
            "parameters": dict(self.operation.parameters),
            "affected_rows": self.affected_rows,
            "changed_cells": self.changed_cells,
            "removed_rows": self.removed_rows,
        }


def is_measurement(series):
    return (is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype)
            and not is_complex_dtype(series.dtype))


def numeric_values(series):
    if not is_measurement(series):
        raise ValueError("Choose a numerical measurement column.")
    values = series.to_numpy(dtype=float, na_value=np.nan, copy=True)
    if np.isinf(values).any():
        raise ValueError("This column contains infinity. Correct those values before preparing it.")
    return values


def outlier_details(series):
    values = numeric_values(series)
    finite = values[np.isfinite(values)]
    if not len(finite):
        raise ValueError("This column has no finite measurements.")
    return iqr_details(values)


def duplicate_representatives(df):
    """Return each row's first equal position, including nested Parquet values."""
    groups = np.zeros(len(df), dtype=np.int64)
    for name in df.columns:
        codes, _ = factorize_column(df[name])
        groups, _ = pd.factorize(pd.MultiIndex.from_arrays([groups, codes]))
    first = np.full(int(groups.max()) + 1 if len(groups) else 0, len(df), dtype=np.int64)
    np.minimum.at(first, groups, np.arange(len(df)))
    return first[groups]


def duplicate_mask(df):
    return duplicate_representatives(df) != np.arange(len(df))


def source_row_numbers(df, source_rows=None):
    """Number source table rows as in Excel: header 1, first data row 2."""
    rows = np.arange(2, len(df) + 2) if source_rows is None else np.asarray(source_rows)
    if rows.ndim != 1 or len(rows) != len(df):
        raise ValueError("Source row references must match the dataset length.")
    return rows


def _display(value):
    text = repr(value) if isinstance(value, str) and value != value.strip() else str(value)
    return text[:120]


def transform(df, operation, *, target=None, source_rows=None):
    """Return a candidate copy with counts and examples; reject ambiguous operations."""
    action, name = operation.action, operation.column
    parameters = dict(operation.parameters)
    source_rows = source_row_numbers(df, source_rows)
    if action != "duplicates":
        if name not in df.columns:
            raise ValueError("Choose a column in this dataset.")
        if target is not None and name == target:
            raise ValueError("The target column is protected. Choose an input feature.")
        series = df[name]
    removed = np.zeros(len(df), dtype=bool)
    changed = np.zeros(len(df), dtype=bool)
    result = df.copy(deep=True)

    if action == "duplicates":
        representatives = duplicate_representatives(df)
        removed = representatives != np.arange(len(df))
        parameters = {"keep": "first", "scope": "all columns"}
    elif action == "drop_missing":
        removed = series.isna().to_numpy()
    elif action in {"fill_median", "fill_mode"}:
        if is_nested(series):
            raise ValueError("Nested values cannot be filled with this method.")
        if "value" not in parameters:
            if action == "fill_median":
                values = numeric_values(series)
                finite = values[np.isfinite(values)]
                if not len(finite):
                    raise ValueError("An entirely missing column has no median to use.")
                magnitude = float(np.abs(finite).max()) or 1.0
                parameters["value"] = float(np.median(finite / magnitude) * magnitude)
            else:
                modes = series.mode(dropna=True)
                if modes.empty:
                    raise ValueError("An entirely missing column has no most frequent value.")
                parameters["value"] = modes.iloc[0]
        # Nullable integer columns may need a fractional median.
        source = series.astype(float) if action == "fill_median" else series
        result[name] = source.fillna(parameters["value"])
    elif action in {"trim", "casefold"}:
        if is_nested(series) or not (is_object_dtype(series.dtype) or is_string_dtype(series.dtype)
                                     or isinstance(series.dtype, pd.CategoricalDtype)):
            raise ValueError("Choose a text column for text cleanup.")
        result[name] = series.astype(object).map(
            lambda value: (value.strip().casefold() if action == "casefold" else value.strip())
            if isinstance(value, str) else value
        )
    elif action in {"clip_outliers", "drop_outliers"}:
        mask, bounds = outlier_details(series)
        if not parameters:
            parameters = bounds
        low, high = parameters["lower"], parameters["upper"]
        mask = outside_bounds(numeric_values(series), parameters)
        if action == "drop_outliers":
            removed = mask
        else:
            result[name] = series.astype(float).clip(low, high)
    elif action in {"minmax", "standardize"}:
        values = numeric_values(series)
        finite = values[np.isfinite(values)]
        if not len(finite):
            raise ValueError("An entirely missing column cannot be scaled.")
        if not parameters:
            magnitude = float(np.abs(finite).max()) or 1.0
            scaled = finite / magnitude
            offset = float(scaled.min() if action == "minmax" else scaled.mean())
            divisor = float(scaled.max() - offset if action == "minmax" else scaled.std())
            if divisor == 0:
                raise ValueError("A constant column cannot be scaled. Choose a varying measurement.")
            parameters = {"magnitude": magnitude, "offset": offset, "divisor": divisor}
        magnitude, offset, divisor = (parameters[key] for key in ("magnitude", "offset", "divisor"))
        if not all(np.isfinite(value) for value in (magnitude, offset, divisor)) or magnitude <= 0 or divisor <= 0:
            raise ValueError("Invalid scaling parameters.")
        with np.errstate(over="ignore", invalid="ignore"):
            output = (values / magnitude - offset) / divisor
        if not np.isfinite(output[~np.isnan(values)]).all():
            raise ValueError("These values exceed the supported numerical range after scaling.")
        result[name] = output
    else:
        raise ValueError(f"Unknown preparation action: {action}")

    examples = []
    if removed.any():
        if removed.all():
            raise ValueError("This action would remove every row. No changes were applied.")
        for position in np.flatnonzero(removed)[:8]:
            value = (df.iloc[position][name] if name is not None else
                     "; ".join(f"{column}={_display(df.iloc[position][column])}" for column in df.columns[:4]))
            example = {"row": int(position) + 1, "source_row": int(source_rows[position]),
                       "before": _display(value), "after": "Row removed"}
            if action == "duplicates":
                kept = int(representatives[position])
                example.update(matched_row=kept + 1, matched_source_row=int(source_rows[kept]))
            examples.append(example)
        result = result.iloc[~removed].copy()
    elif action != "duplicates" and not action.startswith("drop_"):
        equal = series.eq(result[name]).fillna(False) | (series.isna() & result[name].isna())
        changed = ~equal.to_numpy(dtype=bool)
        for position in np.flatnonzero(changed)[:8]:
            examples.append({"row": int(position) + 1, "source_row": int(source_rows[position]), "before": _display(series.iloc[position]),
                             "after": _display(result[name].iloc[position])})

    return Change(result, Operation(action, name, parameters), int((changed | removed).sum()),
                  int(changed.sum()), int(removed.sum()), examples,
                  np.flatnonzero(~removed) if removed.any() else None)
