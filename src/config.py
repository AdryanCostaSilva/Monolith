DEFAULT_INDICATOR_WEIGHT = 1

# Dimension weight = points of macro-F1 (classification), R2 (regression) or AMI
# (clustering) lost when the matching dimension falls to 50% quality, with training
# and test data both degraded. Measured on the raw DQ4AI results of Mohammed, Budach
# et al., "The Effects of Data Quality on Machine Learning Performance on Tabular
# Data" (arXiv 2207.14529v6), using the paper's own Table 3 method (Section 7.1).
# Consistency = (2 x consistent representation + uniqueness) / 3, matching its indicators.
# Data Quality = feature accuracy. "other" = mean of classification, regression and clustering.
# Documentation and Provenance are not covered by the paper: 2.5 is the midpoint of
# its "low effect" band (under 5 points).
# Class Balance applies only to classification, so it has no weight for other tasks.
DIMENSION_WEIGHTS = {
    "classification": {
        "Completeness": 7.8,
        "Consistency": 2.1,
        "Class Balance": 2.3,
        "Documentation": 2.5,
        "Provenance": 2.5,
        "Data Quality": 15.1,
    },
    "regression": {
        "Completeness": 23.5,
        "Consistency": 3.7,
        "Documentation": 2.5,
        "Provenance": 2.5,
        "Data Quality": 33.7,
    },
    "other": {
        "Completeness": 14.5,
        "Consistency": 2.1,
        "Documentation": 2.5,
        "Provenance": 2.5,
        "Data Quality": 20.4,
    },
}

SCORE_BANDS = (
    (0, "Not ready"),
    (50, "Requires preparation"),
    (75, "Almost ready"),
    (90, "Ready"),
)

# User-facing explanation of each evaluation dimension, shown in the UI
# (results tab, dimension card tooltips and context captions) and copied into
# exported reports. One place to change (RNF04). Keys must match the
# "dimension" field produced by each evaluator in src/evaluation/.
DIMENSION_HELP = {
    "Completeness": (
        "Measures whether every cell that matters is filled in: the overall "
        "missing percentage, missing values in the columns you marked as "
        "important, and rows that still contain missing values."
    ),
    "Consistency": (
        "Measures whether the data sticks to one format: numbers stored as "
        "text, the same category written in different ways, columns with "
        "mixed types, and duplicate rows."
    ),
    "Class Balance": (
        "Measures how unevenly the classes of the target column are "
        "distributed; very imbalanced classes make classification harder. "
        "This dimension only applies to classification tasks."
    ),
    "Documentation": (
        "Measures whether the dataset is described for someone who did not "
        "build it: variable descriptions, target definition, collection "
        "method and period, units and categories, and known limitations."
    ),
    "Provenance": (
        "Measures whether the origin and generation process of the data are "
        "recorded: source, collector, generation period, applied "
        "transformations, and dataset version."
    ),
    "Data Quality": (
        "Measures value-level noise that plausibly harms training: extreme "
        "outliers detected per column by the IQR rule, and constant columns "
        "that carry no information."
    ),
}
