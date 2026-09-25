import csv
from pathlib import Path
import pandas as pd

class LoadError(Exception):
    """Error while loading the dataset."""

SUPPORTED_EXTENSIONS = [".csv", ".xlsx"]
DELIMITERS = [",", ";", "\t"] # Basicamente, os separadores
ENCODINGS = ["utf-8-sig", "latin1"] # utf-8-sig tambem remove o BOM que o Excel coloca no inicio

def _detect_delimiter(sample):
    try:
        return csv.Sniffer().sniff(sample, delimiters= DELIMITERS).delimiter # O sniffer tenta adivinhar o delimitador do arquivo vendo se esta na nossa lista DELIMITERS. se nao, erro
    except csv.Error:
        # Sniffer gave up: use the candidate that appears most in the first line
        first_line = sample.splitlines()[0]
        return max(DELIMITERS, key=first_line.count)

def _read_csv(path):
    for encoding in ENCODINGS:
        try:
            with open(path, encoding=encoding) as f:
                sample = f.read(10_000)           # only the first ~10k characters

            sep = _detect_delimiter(sample)
            if sep == ";":
                decimal = ","
            else:
                decimal = "."

            df = pd.read_csv(path, sep=sep, encoding=encoding, decimal=decimal)
            return df, encoding, sep, sample

        except UnicodeDecodeError:
            continue                              # wrong encoding, try the next one
        except pd.errors.EmptyDataError as e:
            raise LoadError("The file has no columns to read.") from e
        except pd.errors.ParserError as e:
            raise LoadError(f"Error reading the CSV (rows with different column counts?): {e}") from e

    raise LoadError("Could not detect the file's encoding.")

def _check_duplicate_header(sample, sep):
    # pandas renomeia colunas repetidas (Name, Name.1), entao checamos o cabecalho cru
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

def load(path):
    """Reads a .csv or .xlsx and returns (df, info). Does not clean or change the data."""
    path = Path(path)

    if not path.exists():
        raise LoadError(f"File not found: {path}")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise LoadError(f"Unsupported format: '{extension}'. Use .csv or .xlsx.")

    if path.stat().st_size == 0:
        raise LoadError("The file is empty.")

    if extension == ".csv":
        df, encoding, sep, sample = _read_csv(path)
        _check_duplicate_header(sample, sep)
    else:
        df = pd.read_excel(path)
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
