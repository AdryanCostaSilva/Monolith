# Training experiment: models trained with and without Monolith preparation

This folder holds the reproducible experiment reported in the paper (§6.3 preparation
scenario, §7.2 protocol, §8.2 results, Table 7 and Figure 10). The experiment is
external to the app: `measure.py` imports the real preparation core from `src/`,
fits every learned parameter (medians, modes, IQR limits, means, standard deviations,
categories) on the training rows only, and replays it on the held-out rows.

## Reproduce

From the repository root, in an environment with the project requirements plus
scikit-learn (the exact measured versions are in `requirements_measured.txt`):

```bash
pip install -r requirements.txt scikit-learn==1.9.1
python evidence/article_results/measure.py
python evidence/article_results/extended_metrics.py
python evidence/article_results/plot_f1.py
```

`measure.py` takes a few minutes and overwrites the outputs in this folder. It asserts
that train and test customers never overlap, that no parameter is fitted on test rows,
that targets and source frames stay unchanged, and that an independent pandas/NumPy
implementation of the same treatments gives identical data and predictions.

## Design

- **Data:** `datasets/churn_showcase_1000.csv` (synthetic, seed 20261030: 1,000 rows of
  960 distinct customers plus 40 exact copies, 200 missing cells, 24 extreme
  `MonthlySpend` values, case and spacing variants in `Plan` and `Region`, target
  `Churned` 800/200) with `churn_showcase_1000_metadata.json`; the injected problems are
  listed in `churn_showcase_1000_answer_key.json`. Wine (UCI, 178 rows, 13 features,
  3 classes) is loaded from scikit-learn.
- **Models:** kNN (k=5) and Random Forest (200 trees, max depth 8), no tuning or resampling.
- **Splits:** 10 stratified 70/30 splits, seed 20261030, identical across conditions.
  Churn is split by `CustomerID`, so copies of a customer never reach both sides.
- **Conditions:** `minimum_manual` (median/mode imputation and one-hot only, the minimum
  that trains), `monolith` (duplicates, text casefold, imputation, IQR clipping of
  `MonthlySpend`, z-score; only z-score on Wine) and `equivalent_manual` (the same
  treatments written by hand, used to check equivalence).

## Files

| File | Content |
|---|---|
| `measure.py` | Runs the preparation showcase and the training experiment |
| `extended_metrics.py` | Precision, recall, F1 and summed confusion matrices from the saved predictions |
| `plot_f1.py` | Figure 10 (`experimento-f1.png`) |
| `training_summary.json` | Mean and sample standard deviation per dataset, condition and model |
| `extended_metrics.json` | Table 7 values and confusion matrices |
| `churn_runs.json`, `wine_runs.json` | Metrics for every split |
| `churn_predictions.json`, `wine_predictions.json` | Truth and prediction for every held-out row |
| `churn_first_split.json`, `wine_first_split.json` | Rows and preparation history of the first split |
| `showcase_preparation.json` | DRS before and after preparation (90.98 to 93.72), scale-only and no-metadata checks |
| `churn_prepared.csv`, `churn_prepared_preparation.json` | The prepared dataset as exported by the app, with its history |
| `direct_fit_missing_error.json` | The expected failure when kNN is fitted on data with missing values |
| `reproducibility.json` | Environment, seeds, model parameters and SHA-256 hashes of the data and of every `src/` module |

## Results (F1-macro, %, mean of 10 splits)

| Dataset | Model | Without Monolith | With Monolith |
|---|---|---|---|
| Churn | kNN | 55.33 ± 2.22 | 70.09 ± 4.37 |
| Churn | Random Forest | 70.26 ± 3.66 | 72.06 ± 2.58 |
| Wine | kNN | 68.28 ± 4.58 | 96.92 ± 1.94 |
| Wine | Random Forest | 97.77 ± 1.18 | 97.96 ± 1.37 |

The equivalent manual condition produced the same predictions as the Monolith condition
in all 40 dataset/split/model pairs.

## Provenance

The outputs come from the run of 2026-10-30 (`reproducibility.json`). The `src/` hashes
recorded there match commit 607a06a as checked out on Windows (CRLF line endings), and a
re-run on 2026-11-10 at that commit produced byte-identical outputs; only
`reproducibility.json` itself differs (timestamp and `git_head`). The two CSV files are
stored byte-exact (see `.gitattributes`) because the metadata JSON pins the dataset's
SHA-256.
