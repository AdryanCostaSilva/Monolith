"""Read explicitly selected metadata. Never infer lineage from file stats."""

import hashlib
import json
from pathlib import Path


METADATA_ATTR = "monolith_metadata"
MAX_METADATA_BYTES = 2 * 1024 * 1024


def collect_metadata(path, metadata_path=None):
    """Fingerprint a dataset and optionally read the user-selected metadata file."""
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return read_metadata(metadata_path, dataset_sha256=digest.hexdigest())


def read_metadata(path, *, dataset_sha256):
    """Read only the selected file; malformed metadata produces visible warnings."""
    evidence = {
        "source": None,
        "dataset_sha256": dataset_sha256,
        "metadata": {},
        "warnings": [],
    }
    if path is None:
        return evidence
    path = Path(path)
    evidence["source"] = path.name
    try:
        if path.stat().st_size > MAX_METADATA_BYTES:
            raise ValueError("metadata exceeds the 2 MiB limit")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        if metadata.get("schema_version") != "1":
            raise ValueError('schema_version must be "1"')
        expected = metadata.get("dataset_sha256")
        if expected is not None and expected != evidence["dataset_sha256"]:
            raise ValueError("dataset_sha256 does not match this dataset; evidence ignored")
        evidence["metadata"] = metadata
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        evidence["warnings"].append(f"{path.name}: {error}")
    return evidence
