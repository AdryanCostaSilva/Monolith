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
   columns, and documentation and provenance checkboxes. Optionally use
   **Choose metadata JSON** in the Context tab to select a metadata file.
3. **Run the evaluation** to view the data-readiness score, issues, and recommended
   improvements. Export the report as JSON or HTML if needed.

## Documentation and provenance assessment

Load a dataset, then use **Choose metadata JSON** in the Context tab to upload
its metadata. The JSON can have any filename and live in any folder. Monolith
only reads the file you select; it does not search beside the dataset. Select
the file again after editing it. Use **Remove** to clear the selection.
Loading a different dataset clears the previous metadata selection.

For each item, a **checked checkbox takes priority** and earns 100 as a
self-reported confirmation, even if the JSON field is missing or invalid.
An unchecked checkbox means "use the uploaded JSON": the app evaluates that
field against the loaded columns and selected target. If neither a checkbox
confirmation nor valid metadata is available, the item earns zero. JSON is
optional; you can use checkboxes alone or combine both sources.

Changing checkboxes or replacing/removing metadata clears previous evaluation
results. Run the evaluation again to update the scores and export a report.

Example for a dataset with columns `temperature` and `fault`:

```json
{
  "schema_version": "1",
  "columns": {
    "temperature": {"description": "Measured air temperature", "unit": "Celsius"},
    "fault": {
      "description": "Whether the sensor reported a fault",
      "categories": {"0": "Normal operation", "1": "Fault reported"}
    }
  },
  "documentation": {
    "target_definition": {"column": "fault", "description": "Predict a sensor fault"},
    "data_collection": "Hourly readings from the station's calibrated sensor",
    "collection_period": {"start": "2026-01-01", "end": "2026-01-31"},
    "known_limitations": ["Readings cover one station during January only"]
  },
  "provenance": {
    "origin": "Station A sensor export, archive record ST-A-2026-01",
    "collector": "Station A operations team",
    "generation_period": {"start": "2026-01-01", "end": "2026-01-31"},
    "transformations": ["Raw export; no transformations applied"],
    "version": "2026-01-v1"
  }
}
```

For unchecked items, variable descriptions and units/category definitions earn the percentage of actual
dataset columns covered. Each column needs a description and either a unit or a
non-empty mapping of category values to descriptions (use `unit: "dimensionless"`
when appropriate). Other indicators earn 100 for a valid field and zero otherwise.
Dates must be ISO calendar dates with start no later than end. Limitations and
transformations require non-empty lists of text; explicitly describe raw data or
the absence of known limitations. The target definition must match the selected
column. Target definition is excluded when no target is selected, including when
its checkbox is checked. Indicators retain equal weights.

Every loaded file receives a SHA-256 fingerprint. An optional top-level
`dataset_sha256` in the metadata binds it to those exact file bytes; mismatches
invalidate the metadata. The hash is shown in the dataset info in exports and can
also be obtained with `sha256sum measurements.csv`. A hash alone earns no provenance
points: it identifies content, not its origin or collection history.

The Context screen displays assessment status for each item. JSON and HTML exports
identify whether each score came from a user checkbox or uploaded metadata, and
include evidence, statuses, fingerprint, and parsing warnings. Malformed metadata
(including unsupported schema versions or checksum mismatches) earns no metadata
credit; checked items still receive full credit. Metadata files are limited to 2 MiB.

These checks assess **user confirmations and metadata coverage and structure**;
they do not independently verify the author's statements. Without a checksum,
matching columns cannot prove that metadata belongs to this dataset version.
Free-text README/PDF extraction and external source verification are not implemented.

For Python callers, select metadata explicitly with
`load("measurements.csv", metadata_path="metadata.json")`. Omitting `metadata_path`
loads the dataset without metadata.
