"""Extended metrics (precision, recall, F1, confusion matrices) from the saved predictions.

Usage: python extended_metrics.py [folder]   (defaults to this script's folder)
Reads churn_predictions.json and wine_predictions.json written by measure.py and
writes extended_metrics.json next to them.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)

exp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
out = {}
for ds in ("churn", "wine"):
    preds = json.load(open(exp / f"{ds}_predictions.json", encoding="utf-8"))
    groups = defaultdict(list)
    for p in preds:
        groups[(p["condition"], p["model"])].append(p)
    for (cond, model), runs in groups.items():
        rows = []
        cm_total = None
        for r in runs:
            y, yp = np.array(r["truth"]), np.array(r["prediction"])
            labels = sorted(set(y))
            m = {"accuracy": accuracy_score(y, yp), "balanced_accuracy": balanced_accuracy_score(y, yp),
                 "precision_macro": precision_score(y, yp, average="macro", zero_division=0),
                 "recall_macro": recall_score(y, yp, average="macro", zero_division=0),
                 "f1_macro": f1_score(y, yp, average="macro", zero_division=0),
                 "majority_accuracy": max((y == c).mean() for c in labels)}
            if ds == "churn":
                m.update(precision_pos=precision_score(y, yp, pos_label=1, zero_division=0),
                         recall_pos=recall_score(y, yp, pos_label=1, zero_division=0),
                         f1_pos=f1_score(y, yp, pos_label=1, zero_division=0))
            cm = confusion_matrix(y, yp, labels=labels)
            cm_total = cm if cm_total is None else cm_total + cm
            rows.append(m)
        summary = {k: (float(np.mean([r[k] for r in rows])), float(np.std([r[k] for r in rows], ddof=1)))
                   for k in rows[0]}
        out[f"{ds}|{cond}|{model}"] = {"n": len(runs), "test_rows": len(runs[0]["truth"]),
                                        "metrics": summary, "confusion_sum": cm_total.tolist()}
json.dump(out, open(exp / "extended_metrics.json", "w", encoding="utf-8"), indent=1)
for key, value in out.items():
    if "equivalent" in key:
        continue
    print(key, " ".join(f"{name}={mean*100:.2f}±{sd*100:.2f}" for name, (mean, sd) in value["metrics"].items()))
