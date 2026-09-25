DEFAULT_INDICATOR_WEIGHT = 1

DIMENSION_WEIGHTS = {
    "Completeness": 1,
    "Consistency": 1,
    "Class Balance": 1,
    "Documentation": 1,
    "Provenance": 1,
    "Data Quality": 1,
}

SCORE_BANDS = (
    (0, "Not ready"),
    (50, "Requires preparation"),
    (75, "Almost ready"),
    (90, "Ready"),
)
