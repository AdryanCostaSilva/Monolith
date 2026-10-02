import csv
import mmap
import tempfile
from pathlib import Path

import pandas as pd


class LoadError(Exception):
    """Error while loading the dataset."""


SUPPORTED_EXTENSIONS = [".csv", ".xlsx", ".parquet"]
DELIMITERS = [",", ";", "\t"]
ENCODINGS = ["utf-8-sig", "latin1"]
PARQUET_BATCH_SIZE = 65_536
PARQUET_IN_MEMORY_ROWS = 100_000


def _read_parquet(path, progress=None):
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Decode sequentially into compact batches instead of prefetching all row groups.
    with pq.ParquetFile(path, pre_buffer=False) as source:
        large = source.metadata.num_rows > PARQUET_IN_MEMORY_ROWS
        compact = large or any(
            pa.types.is_nested(field.type) for field in source.schema_arrow
        )
        if large:
            # An anonymous temporary file owns the decoded data. Arrow arrays
            # reference its mapping, whose pages the OS can reclaim under pressure.
            with tempfile.TemporaryFile() as backing:
                with pa.ipc.new_file(backing, source.schema_arrow) as writer:
                    rows = 0
                    for batch in source.iter_batches(batch_size=PARQUET_BATCH_SIZE, use_threads=False):
                        writer.write_batch(batch)
                        rows += batch.num_rows
                        if progress:
                            progress(f"Loading rows: {rows:,} / {source.metadata.num_rows:,}")
                backing.flush()
                mapped = mmap.mmap(backing.fileno(), 0, access=mmap.ACCESS_READ)
            table = pa.ipc.open_file(pa.BufferReader(mapped)).read_all()
            df = table.to_pandas(types_mapper=pd.ArrowDtype)
            # Arrow buffers retain the mapping even when a Series outlives df.
            # Keep a reference here too, to release scanned pages between columns.
            object.__setattr__(df, "_parquet_mapping", mapped)
            return df
        batches = []
        rows = 0
        for batch in source.iter_batches(batch_size=PARQUET_BATCH_SIZE, use_threads=False):
            batches.append(batch)
            rows += batch.num_rows
            if progress:
                progress(f"Loading rows: {rows:,} / {source.metadata.num_rows:,}")
        table = pa.Table.from_batches(batches, schema=source.schema_arrow)
    if compact:
        return table.to_pandas(types_mapper=pd.ArrowDtype)
    return table.to_pandas()


def _detect_delimiter(sample):
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        first_line = sample.splitlines()[0]
        return max(DELIMITERS, key=first_line.count)


def _read_csv(path):
    for encoding in ENCODINGS:
        try:
            with open(path, encoding=encoding) as f:
                sample = f.read(10_000)

            sep = _detect_delimiter(sample)
            if sep == ";":
                decimal = ","
            else:
                decimal = "."

            df = pd.read_csv(path, sep=sep, encoding=encoding, decimal=decimal)
            return df, encoding, sep, sample

        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError as e:
            raise LoadError("The file has no columns to read.") from e
        except pd.errors.ParserError as e:
            raise LoadError(
                f"Error reading the CSV (rows with different column counts?): {e}"
            ) from e

    raise LoadError("Could not detect the file's encoding.")


def _check_duplicate_header(sample, sep):
    first_line = sample.splitlines()[0]
    names = next(csv.reader([first_line], delimiter=sep))
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise LoadError(f"Duplicate column names: {', '.join(duplicates)}")


def _validate(df):
    if df.empty:
        raise LoadError("The file has no data.")
    if df.shape[1] < 2:
        raise LoadError("Only 1 column found. The delimiter was probably not detected correctly.")


def load(path, *, progress=None):
    """Read CSV, XLSX or Parquet and return (df, info) without changing the data."""
    path = Path(path)

    if not path.exists():
        raise LoadError(f"File not found: {path}")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise LoadError(f"Unsupported format: '{extension}'. Use .csv, .xlsx or .parquet.")

    if path.stat().st_size == 0:
        raise LoadError("The file is empty.")

    if extension == ".csv":
        df, encoding, sep, sample = _read_csv(path)
        _check_duplicate_header(sample, sep)
    elif extension == ".xlsx":
        df = pd.read_excel(path)
        encoding, sep = None, None
    else:
        try:
            df = _read_parquet(path, progress)
        except ImportError as e:
            raise LoadError(
                "Parquet support requires pyarrow. Install the dependencies with "
                "python -m pip install -r requirements.txt."
            ) from e
        except (OSError, ValueError) as e:
            raise LoadError(f"Error reading the Parquet file: {e}") from e
        encoding, sep = None, None

    _validate(df)

    info = {
        "file": path.name,
        "format": extension.lstrip("."),
        "encoding": encoding,
        "delimiter": sep,
        "rows": df.shape[0],
        "columns": df.shape[1],
    }
    return df, info
