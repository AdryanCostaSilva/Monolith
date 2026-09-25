# TODO — PBL 5 Demo (due today, 2026-09-25)

**Goal:** a working first version of the Data Readiness framework that shows a real use case: load a dataset, set the usage context, get a 0–100 score, and see scores per dimension, problems and recommendations. Record evidence of it working.

**What PBL 5 requires us to submit:**
- [ ] Working version of the artifact
- [ ] Application scenario
- [ ] Use case
- [ ] Practical demonstration
- [ ] Evidence (screenshots, video, exported reports)

---

## 0. Setup — 15 min
- [X] Create a `src/` folder in the repo root, and inside it: `loading/`, `profiling/`, `evaluation/`, `aggregation/`, `reporting/`, `ui/`. Put an empty `__init__.py` in `src/` and in each subfolder. Run everything from the repo root (`python main.py`).
- [X] Create `main.py` in the repo root. Its only job is to start the UI.
- [X] Create `src/config.py` for the weights, thresholds and score bands (one place to change them, which covers RNF04)
- [X] Create `datasets/` for the demo files
- [X] Agree on the **result contract** below so the engine and the UI can be built in parallel

### Result contract (agree on this first)
```python
# every evaluator returns:
{
    "dimension": "Completeness",
    "applicable": True,
    "score": 87.5,                      # 0–100
    "indicators": [{"name": "% filled cells", "value": 92.0, "weight": 1}],
    "problems": ["Column 'Cabin' has 77% missing values"],
    "recommendations": ["Remove or impute the missing values in column 'Cabin'"],
}

# the aggregator returns:
{
    "score": 78.3,
    "classification": "Requires preparation",
    "dimensions": [...],                # list of the dicts above
}
```

---

## 1. Loader — `src/loading/loader.py` — 45 min
- [X] `load(path) -> (df, info)`
- [X] CSV: detect the delimiter (`csv.Sniffer`, from `, ; \t |`)
- [X] CSV: try `utf-8-sig`, then fall back to `latin-1`
- [X] CSV: if the separator is `;`, use `decimal=","`
- [X] XLSX: `pd.read_excel` (openpyxl is already in requirements)
- [X] Extension check is case-insensitive (`.CSV` works)
- [X] Validate the result: file not empty, more than 1 column, no duplicate column **names**. Raise a clear error message otherwise. (Duplicate **rows** are not the loader's job; they go to `consistency.py` in step 4.)
- [X] `info` = `{file, format, encoding, delimiter, rows, columns}`
- **Done when:** a `,`/UTF-8 CSV, a `;`/Latin-1 CSV and an `.xlsx` all load correctly

## 2. Profiler — `src/profiling/profiler.py` — 45 min
- [X] `profile(df) -> dict`, which returns data only and never prints
- [X] Per column: type, % missing, unique count, basic stats (numeric) or top values (categorical)
- [X] Dataset level: rows, columns, % missing cells, duplicate rows
- [X] Flag "numbers stored as text": a text column where ≥ 90% of the values convert to numbers
- **Done when:** `profile(titanic)` shows Age/Cabin/Embarked with missing values

## 3. Usage context — 20 min
- [X] `UsageContext` (a dataclass) with: project goal, task type (`classification` / `regression` / `other`), target column (optional), important columns, notes
- [X] Documentation checklist (6 yes/no answers): variable descriptions, target definition, how data was collected, collection period, units/categories, known limitations
- [X] Provenance checklist (5 yes/no answers): origin, who collected it, generation period, transformations applied, version

## 4. Evaluators — `src/evaluation/` — 2 h
Each one returns the contract dict. Every indicator is on a 0–100 scale.

- [X] **`completeness.py`**
  - % filled cells
  - % columns with < 20% missing
  - % complete rows
  - % filled in the *important* columns from the context
- [X] **`consistency.py`**
  - % non-duplicate rows
  - % columns without mixed types / numbers stored as text
  - % categorical columns without case or whitespace variants (`"SP"` vs `"sp "`)
- [X] **`class_balance.py`**: only applies to classification with a target; otherwise `applicable=False`
  - minority/majority class ratio → score
  - flag any class with less than 5% of the rows
- [X] **`documentation.py`**: score = % of "yes" answers in the checklist
- [X] **`provenance.py`**: score = % of "yes" answers in the checklist
- [X] **`quality.py`**
  - % numeric values that aren't outliers (IQR rule)
  - % non-constant columns
- [X] Every problem found also adds a recommendation (plain rule-based text, no AI)

## 5. Aggregator — `src/aggregation/aggregator.py` — 30 min
- [X] `D_j = Σ(w_i · I_i) / Σ w_i` (one score per dimension)
- [X] `DR = Σ(W_j · D_j) / Σ W_j`, **only over applicable dimensions** (the remaining weights renormalize automatically)
- [X] v1: equal weights, defined in `config.py`
- [X] Score bands (preliminary, in `config.py`):
  - 0–49 → Not ready
  - 50–74 → Requires preparation
  - 75–89 → Almost ready
  - 90–100 → Ready
- **Done when:** removing Class Balance (regression task) does not lower the score

## 6. Report — `src/reporting/report_generator.py` — 30 min
- [X] `generate_report(info, profile, context, result) -> dict`
- [X] Export to **JSON** (full data)
- [X] Export to **HTML or TXT** (readable, for the evidence folder)
- [X] Content: dataset info, score + band, score per dimension, problems, the indicators behind each score, recommendations

## 7. Engine smoke test (no UI) — 20 min
- [X] `demo/run_demo.py`: load → profile → evaluate → aggregate → report, for every dataset in `datasets/`
- [X] Run it twice and confirm the scores are identical (RNF02: reproducible)

## 8. UI — `src/ui/main_window.py` (CustomTkinter) — 2 h
Move `DataReadinessApp` out of `app.py`. **No analysis logic in the UI.** It only calls the engine.
- [ ] Screen 1 — **Load** (Use Case 1): pick a file, show the format detected, rows, columns, % missing (reuse the existing cards)
- [ ] Screen 2 — **Context** (Use Case 2): task type dropdown, target dropdown (filled from the columns), checkboxes for important columns, the documentation and provenance checklists
- [ ] Screen 3 — **Evaluate** (Use Case 3): an "Evaluate" button that runs the engine
- [ ] Screen 4 — **Results** (Use Case 4): big score + band, a bar/card for each dimension, list of problems, list of recommendations, "Export report" button
- [ ] Fix the old bugs: use `pathlib.Path(path).name` instead of `split("/")`, and make the extension check case-insensitive
- [ ] Delete `app.py` (or turn it into a stub that calls `main.py`)

## 9. Demo scenario + evidence — 1 h
- [ ] `datasets/titanic.csv`: clean-ish classification dataset, target `Survived`
- [ ] `demo/inject_issues.py`: creates `titanic_degraded.csv` with extra missing values, duplicated rows, an imbalanced target, and a column of numbers stored as text (the Budach et al. 2022 approach)
- [ ] One real Brazilian open-data CSV (`;` + Latin-1) from dados.gov.br, to show the loader handles real files
- [ ] Run all 3 through the UI:
  - [ ] Screenshots of each screen → `evidence/`
  - [ ] Exported reports (JSON + HTML) → `evidence/`
  - [ ] Short screen recording (2–3 min): clean dataset → high score, degraded → lower score, with the right dimensions flagged
- [ ] Make a before/after table: score per dimension, clean vs degraded

## 10. Write-up — `pbl5.tex` on Overleaf — 1 h
- [ ] **Working version:** what was built, the architecture (link it to the PBL4 modules), tech stack
- [ ] **Application scenario:** e.g. "a team wants to train a survival classifier and needs to know whether the dataset is ready"
- [ ] **Use case:** walk through Use Cases 1–4 with screenshots
- [ ] **Demonstration:** the clean vs degraded vs gov-CSV results table and what the tool flagged
- [ ] **Evidence:** screenshots, report excerpts, video link
- [ ] **Parameters:** list the weights, thresholds and bands used, and note they are preliminary (as PBL4 says)
- [ ] **Limitations:** tabular data only, one header row; Documentation and Provenance are self-reported

---

## If we run out of time, cut in this order
1. HTML export (keep JSON + screenshots)
2. The Brazilian gov CSV
3. The `quality.py` extras (keep it to the outlier check only)
4. Screen recording (screenshots are enough evidence)

**Never cut:** loader → profiler → evaluators → aggregator → results screen → clean vs degraded comparison.

## Suggested split (4 people, in parallel after step 0)
| Who | Steps |
|---|---|
| ______ | 1, 2, 7 (loader, profiler, smoke test) |
| ______ | 4, 5 (evaluators, aggregator) |
| ______ | 8 (UI, built against a fake result dict until the engine is ready) |
| ______ | 3, 6, 9, 10 (context, report, datasets/evidence, write-up) |
