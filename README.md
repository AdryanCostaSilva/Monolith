# Monolith

Monolith is a Python desktop application that evaluates whether tabular data is
ready for its intended use. It calculates a data-readiness score, identifies
issues, and recommends improvements for CSV (`.csv`), Excel (`.xlsx`), and
Parquet (`.parquet`) datasets.

## Run locally

Requires Python 3 with Tkinter available.

```bash
git clone https://github.com/AdryanCostaSilva/Monolith
cd Monolith
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 main.py
```

On Windows, use `python` instead of `python3` and activate the environment with
`.venv\Scripts\Activate.ps1` in PowerShell.

## Usage

1. **Load a dataset** to review its dimensions, missing values, and column information.
2. **Set the context:** project goal, task type, target (if applicable), important
   columns, documentation, and data provenience.
3. **Run the evaluation** to view the data-readiness score, issues, and recommended
   improvements. Export the report as JSON or HTML if needed.
