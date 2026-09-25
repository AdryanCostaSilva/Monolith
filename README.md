# Monolith

## Engine smoke test (TODO section 7)

From the repository root, install the dependencies and run:

```sh
python -m pip install -r requirements.txt
python demo/run_demo.py
```

`python -m demo.run_demo` also works. No UI is started.

The runner reads every CSV/XLSX directly inside `datasets/` and calls the existing
loader, profiler, six evaluators, aggregator and report generator. It runs the
pipeline twice per file and compares the complete evaluation results, including
the overall score and each dimension's score (RNF02). A failed dataset is printed
as `FAIL`; other datasets are still attempted. The command exits with status 1
if any dataset fails or no supported datasets exist, and 0 if all pass.

`datasets/smoke_sample.csv` is a tiny synthetic fixture with missing values and a
duplicate row, based on the existing `demo_report.py` example. It is not the real
Titanic dataset required by section 9. Add the actual demo datasets to this folder
when available; they will be picked up automatically.

Files containing `Survived` use a classification context with that target marked
important. Other files use the default `other` task, so Class Balance is not
applicable. Documentation and provenance answers remain false because the runner
has no evidence for those checklists; their scores will therefore be zero.

Successful runs export JSON and HTML under `evidence/smoke_test/`, for example
`smoke_sample.csv.json` and `smoke_sample.csv.html`. These contain the dataset info,
profile, context, scores, indicators, problems and recommendations. Re-running
replaces these generated reports.
