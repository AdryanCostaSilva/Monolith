from dataclasses import dataclass, field


TASK_TYPES = ("classification", "regression", "other")

DOCUMENTATION_ITEMS = (
    "variable_descriptions",
    "target_definition",
    "data_collection",
    "collection_period",
    "units_and_categories",
    "known_limitations",
)

PROVENANCE_ITEMS = (
    "origin",
    "collector",
    "generation_period",
    "transformations",
    "version",
)


def _empty_checklist(items):
    return dict.fromkeys(items, False)


def _validate_checklist(name, answers, items):
    if set(answers) != set(items):
        raise ValueError(f"{name} must contain: {', '.join(items)}")
    if not all(isinstance(answer, bool) for answer in answers.values()):
        raise TypeError(f"All {name} answers must be boolean values.")


@dataclass
class UsageContext:
    project_goal: str
    task_type: str = "other"
    target_column: str | None = None
    important_columns: list[str] = field(default_factory=list)
    notes: str = ""
    documentation: dict[str, bool] = field(
        default_factory=lambda: _empty_checklist(DOCUMENTATION_ITEMS)
    )
    provenance: dict[str, bool] = field(
        default_factory=lambda: _empty_checklist(PROVENANCE_ITEMS)
    )

    def __post_init__(self):
        if self.task_type not in TASK_TYPES:
            raise ValueError(f"task_type must be one of: {', '.join(TASK_TYPES)}")
        _validate_checklist("documentation", self.documentation, DOCUMENTATION_ITEMS)
        _validate_checklist("provenance", self.provenance, PROVENANCE_ITEMS)
