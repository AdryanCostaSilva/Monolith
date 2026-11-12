"""Reproducible measurements for the Results and Discussion document.

This experiment is external to the app. It imports the actual preparation core,
fits every learned parameter on training rows, and replays it on held-out rows.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".venv" / "matplotlib"))
os.environ.setdefault("OMP_NUM_THREADS", "1")

import hashlib
import json
import platform
import subprocess
from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.datasets import load_wine
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, recall_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import OneHotEncoder

from src.context import UsageContext
from src.engine import evaluate_dataset
from src.loading import load
from src.preparation import Operation, PreparationSession, transform
from src.profiling import profile
from src.profiling.outliers import iqr_details

OUT = Path(__file__).resolve().parent
NUM = ["Age", "MonthlySpend", "TenureMonths", "SupportTickets"]
CAT = ["Plan", "Region", "Contract"]
TARGET = "Churned"


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2,
        default=lambda x: x.item() if hasattr(x, "item") else str(x), allow_nan=False), encoding="utf-8")


def apply_if_changed(session, operation):
    change = session.preview(operation)
    if change.affected_rows:
        session.apply()
    else:
        session.discard_preview()
    return change


def fitted_framework(train, test=None, *, wine=False):
    session = PreparationSession(train)
    target = "target" if wine else TARGET
    session.set_target(target)
    operations = []
    if not wine:
        operations = [Operation("duplicates")]
        operations += [Operation("casefold", c) for c in ("Plan", "Region")]
        operations += [Operation("fill_median", c) for c in NUM]
        operations += [Operation("fill_mode", c) for c in CAT]
        operations += [Operation("clip_outliers", "MonthlySpend")]
    numeric = [c for c in train.columns if c != "target"] if wine else NUM
    operations += [Operation("standardize", c) for c in numeric]
    for operation in operations:
        apply_if_changed(session, operation)
    result_test = test.copy(deep=True) if test is not None else None
    if result_test is not None:
        for record in session.history:
            if record["action"] != "duplicates":
                result_test = transform(result_test, Operation(record["action"], record["column"],
                    record["parameters"]), target=target).data
        assert result_test.index.equals(test.index)
        pd.testing.assert_series_equal(result_test[target], test[target])
    pd.testing.assert_series_equal(session.working[target], train.loc[session.working.index, target])
    return session, result_test


def manual_prepare(train, test, *, full=False, wine=False):
    """Equivalent operations independently implemented using pandas and NumPy."""
    tr, te = train.copy(deep=True), test.copy(deep=True)
    numeric = [c for c in train.columns if c != "target"] if wine else NUM
    if full and not wine:
        tr = tr.drop_duplicates().copy()
        for col in ("Plan", "Region"):
            for data in (tr, te):
                data[col] = data[col].map(lambda x: x.strip().casefold() if isinstance(x, str) else x)
    if not wine:
        for col in NUM:
            median = tr[col].median()
            tr[col], te[col] = tr[col].fillna(median), te[col].fillna(median)
        for col in CAT:
            mode = tr[col].mode().iloc[0]
            tr[col], te[col] = tr[col].fillna(mode), te[col].fillna(mode)
    if full:
        if not wine:
            q1, q3 = tr["MonthlySpend"].quantile([.25, .75])
            low, high = q1 - 1.5*(q3-q1), q3 + 1.5*(q3-q1)
            for data in (tr, te):
                data["MonthlySpend"] = data["MonthlySpend"].clip(low, high)
        for col in numeric:
            mean, std = tr[col].mean(), tr[col].std(ddof=0)
            tr[col], te[col] = (tr[col]-mean)/std, (te[col]-mean)/std
    return tr, te


def metrics(y, pred):
    result = {"accuracy": accuracy_score(y, pred),
              "balanced_accuracy": balanced_accuracy_score(y, pred),
              "macro_f1": f1_score(y, pred, average="macro", zero_division=0)}
    if len(np.unique(y)) == 2:
        result["minority_recall"] = recall_score(y, pred, pos_label=1, zero_division=0)
    return {key: float(value) for key, value in result.items()}


def run_models(dataset_name, data, *, wine=False):
    runs, predictions = [], []
    target = "target" if wine else TARGET
    unique = data if wine else data.drop_duplicates("CustomerID")
    splits = StratifiedShuffleSplit(n_splits=10, test_size=.30, random_state=20261030)
    for split, (a, b) in enumerate(splits.split(unique, unique[target])):
        if wine:
            train, test = data.iloc[a].copy(), data.iloc[b].copy()
            assert not set(train.index) & set(test.index)
        else:
            train_ids, test_ids = set(unique.iloc[a].CustomerID), set(unique.iloc[b].CustomerID)
            assert not train_ids & test_ids
            train = data[data.CustomerID.isin(train_ids)].copy()
            # One held-out prediction per customer, same rows for every condition.
            test = unique[unique.CustomerID.isin(test_ids)].copy()
        source_train, source_test = train.copy(deep=True), test.copy(deep=True)
        basic = manual_prepare(train, test, wine=wine)
        framework, prepared_test = fitted_framework(train, test, wine=wine)
        prepared = (framework.working, prepared_test)
        manual = manual_prepare(train, test, full=True, wine=wine)
        for framework_df, manual_df in zip(prepared, manual):
            pd.testing.assert_frame_equal(framework_df, manual_df, check_dtype=False,
                rtol=1e-11, atol=1e-11)
        conditions = {"minimum_manual": basic, "monolith": prepared, "equivalent_manual": manual}
        first_predictions = {}
        for condition, (tr, te) in conditions.items():
            features = [c for c in tr.columns if c != target] if wine else NUM+CAT
            if wine:
                xtr, xte = tr[features].to_numpy(), te[features].to_numpy()
            else:
                encoder = ColumnTransformer([("numeric", "passthrough", NUM),
                    ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT)])
                xtr, xte = encoder.fit_transform(tr[features]), encoder.transform(te[features])
            models = {"kNN (k=5)": KNeighborsClassifier(n_neighbors=5),
                      "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=8,
                          random_state=20261030+split, n_jobs=1)}
            for name, model in models.items():
                model.fit(xtr, tr[target])
                pred = model.predict(xte)
                if condition == "monolith":
                    first_predictions[name] = pred
                if condition == "equivalent_manual":
                    assert np.array_equal(pred, first_predictions[name]), (dataset_name, split, name)
                runs.append({"dataset": dataset_name, "split": split, "condition": condition,
                    "model": name, "train_rows": len(tr), "test_rows": len(te),
                    **metrics(te[target], pred)})
                predictions.append({"dataset": dataset_name, "split": split, "condition": condition,
                    "model": name, "test_source_positions": test.index.tolist(),
                    "truth": te[target].tolist(), "prediction": pred.tolist()})
        if split == 0:
            dump(dataset_name+"_first_split.json", {"train_source_positions": train.index.tolist(),
                "test_source_positions": test.index.tolist(), "history": framework.history,
                "train_rows_original": len(train), "train_rows_prepared": len(framework.working),
                "test_rows": len(test), "assertions": ["disjoint groups", "no test fitting",
                "unchanged targets", "unchanged sources", "manual equivalence", "same held-out rows"]})
        pd.testing.assert_frame_equal(train, source_train)
        pd.testing.assert_frame_equal(test, source_test)
        print(f"{dataset_name}: split {split+1}/10 complete", flush=True)
    table = pd.DataFrame(runs)
    summary = []
    for (condition, model), group in table.groupby(["condition", "model"], sort=False):
        summary.append({"dataset": dataset_name, "condition": condition, "model": model,
            "n_splits": len(group), **{key+suffix: float(getattr(group[key], statistic)())
                for key in ("accuracy", "balanced_accuracy", "macro_f1")
                + (("minority_recall",) if not wine else ())
                for statistic, suffix in (("mean", "_mean"), ("std", "_std"))}})
    dump(dataset_name+"_predictions.json", predictions)
    dump(dataset_name+"_runs.json", runs)
    return summary


def main():
    df, info = load(ROOT/"datasets/churn_showcase_1000.csv",
        metadata_path=ROOT/"datasets/churn_showcase_1000_metadata.json")
    context = UsageContext("Classificar cancelamento sintético; avaliar preparação",
        task_type="classification", target_column=TARGET, important_columns=NUM+CAT)
    untouched = df.copy(deep=True)
    session, _ = fitted_framework(df)
    comparison = session.compare(context)
    no_metadata = df.copy(deep=True)
    no_metadata.attrs = {}
    numeric_untouched = df.copy(deep=True)
    scaled_only = PreparationSession(numeric_untouched)
    scaled_only.set_target(TARGET)
    for c in NUM:
        apply_if_changed(scaled_only, Operation("standardize", c))
    scale_comparison = scaled_only.compare(context)
    assert scale_comparison["original"]["score"] == scale_comparison["prepared"]["score"]
    pd.testing.assert_frame_equal(df, untouched)
    show = {"dataset_info": info, "context": context.__dict__, "comparison": comparison,
        "without_metadata": evaluate_dataset(no_metadata, context),
        "scale_only_comparison": scale_comparison,
        "before": {"rows": len(df), "missing_cells": int(df.isna().sum().sum()),
            "duplicates": int(df.duplicated().sum()), "spend_outliers": int(iqr_details(df.MonthlySpend.to_numpy())[0].sum()),
            "target_counts": df[TARGET].value_counts().to_dict()},
        "after": {"rows": len(session.working), "missing_cells": int(session.working.isna().sum().sum()),
            "duplicates": int(session.working.duplicated().sum()),
            "spend_outliers": int(iqr_details(session.working.MonthlySpend.to_numpy())[0].sum()),
            "target_counts": session.working[TARGET].value_counts().to_dict()},
        "history": session.history}
    dump("showcase_preparation.json", show)
    session.export(OUT/"churn_prepared.csv", source=info, context=context, comparison=comparison)
    try:
        KNeighborsClassifier(5).fit(df[NUM], df[TARGET])
        raise AssertionError("Expected a direct fit with missing data to fail")
    except ValueError as error:
        dump("direct_fit_missing_error.json", {"status": "expected failure", "reason": str(error)})
    training = run_models("churn", df)
    wine = load_wine(as_frame=True).frame
    wine_source = Path(sklearn.__file__).parent/"datasets/data/wine_data.csv"
    training += run_models("wine", wine, wine=True)
    dump("training_summary.json", training)
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/"src").rglob("*.py"))}
    dump("reproducibility.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "sklearn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_hashes": source_hashes, "churn_sha256": hashlib.sha256((ROOT/"datasets/churn_showcase_1000.csv").read_bytes()).hexdigest(),
        "wine_sha256": hashlib.sha256(wine_source.read_bytes()).hexdigest(),
        "split_seed": 20261030, "splits": 10, "test_fraction": .3,
        "conditions": ["minimum_manual", "monolith", "equivalent_manual"],
        "model_parameters": {"knn": {"n_neighbors": 5}, "random_forest": {"n_estimators":200,
            "max_depth":8, "n_jobs":1, "random_state":"20261030 + split"}},
        "note":"Current local work includes uncommitted preparation changes; hashes identify the actual measured code."})
    print(json.dumps({"preparation": {"before": show["before"], "after": show["after"]},
        "scores": {k:v["score"] for k,v in comparison.items()}, "models": training}, indent=2), flush=True)


if __name__ == "__main__":
    main()
