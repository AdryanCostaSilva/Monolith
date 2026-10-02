"""Exact factorization of nested Arrow columns without Python objects per cell."""

import json
import mmap

import numpy as np
import pandas as pd

NESTED_BATCH_SIZE = 65_536


def release_pages(df):
    """Release scanned mmap pages from RSS; the data remains available on disk."""
    mapped = getattr(df, "_parquet_mapping", None)
    if mapped is not None and hasattr(mapped, "madvise"):
        mapped.madvise(mmap.MADV_DONTNEED)


def is_nested(series):
    if not isinstance(series.dtype, pd.ArrowDtype):
        return False
    import pyarrow as pa

    return pa.types.is_nested(series.dtype.pyarrow_dtype)


def _first_positions(codes, count):
    positions = np.full(count, len(codes), dtype=np.int64)
    np.minimum.at(positions, codes, np.arange(len(codes), dtype=np.int64))
    return positions


class _NestedEncoder:
    """Share exact value IDs between batches, including IDs for nested children."""

    def __init__(self, kind):
        import pyarrow as pa

        self.kind = kind
        self.lookup = {}
        self.nan_key = object()
        self.struct = pa.types.is_struct(kind)
        self.fixed = pa.types.is_fixed_size_list(kind)
        self.sequence = (
            self.fixed or pa.types.is_list(kind) or pa.types.is_large_list(kind)
            or pa.types.is_map(kind)
        )
        if self.struct:
            self.children = [_NestedEncoder(field.type) for field in kind]
        elif self.sequence:
            child = (
                pa.struct([("key", kind.key_type), ("value", kind.item_type)])
                if pa.types.is_map(kind) else kind.value_type
            )
            self.children = [_NestedEncoder(child)]

    def intern(self, key):
        code = self.lookup.get(key)
        if code is None:
            code = len(self.lookup)
            self.lookup[key] = code
        return code

    def encode(self, array):
        if self.struct:
            columns = [
                child.encode(array.field(index))
                for index, child in enumerate(self.children)
            ]
            groups = np.zeros(len(array), dtype=np.int64)
            for column, child in zip(columns, self.children):
                groups, _ = pd.factorize(groups * max(len(child.lookup), 1) + column)
            groups[array.is_null().to_numpy(zero_copy_only=False)] = -1
            local, values = pd.factorize(groups)
            positions = _first_positions(local, len(values))
            remap = np.array([
                self.intern(
                    None if values[index] == -1
                    else tuple(int(column[position]) for column in columns)
                )
                for index, position in enumerate(positions)
            ], dtype=np.int64)
            return remap[local]

        if self.sequence:
            if self.fixed:
                offsets = (np.arange(len(array) + 1) + array.offset) * self.kind.list_size
            else:
                offsets = array.offsets.to_numpy(zero_copy_only=False)
            base = int(offsets[0])
            child_codes = self.children[0].encode(
                array.values.slice(base, int(offsets[-1]) - base)
            )
            offsets = offsets - base
            nulls = array.is_null().to_numpy(zero_copy_only=False)
            codes = np.empty(len(array), dtype=np.int64)
            # Byte strings compare the complete contents, order and length.
            for index in range(len(array)):
                key = (
                    None if nulls[index]
                    else child_codes[offsets[index]:offsets[index + 1]].tobytes()
                )
                codes[index] = self.intern(key)
            return codes

        local, values = pd.factorize(
            pd.Series(array, dtype=pd.ArrowDtype(array.type)), use_na_sentinel=False
        )
        remap = []
        for value in values:
            key = None if value is pd.NA or value is None else value
            if isinstance(key, float) and np.isnan(key):
                key = self.nan_key
            remap.append(self.intern(key))
        return np.array(remap, dtype=np.int64)[local]


class _NestedValues:
    """Reference representatives in the original buffers; decode only top values."""

    def __init__(self, source, positions):
        self.source = source
        self.positions = positions

    def __len__(self):
        return len(self.positions)

    def __getitem__(self, index):
        return self.source[int(self.positions[index])]

    def is_valid(self):
        return self.source.is_valid().take(self.positions)

    def to_pylist(self):
        return [self[index].as_py() for index in range(len(self))]


def factorize_column(series):
    """Return integer codes and distinct values, including a code for nulls."""
    if not is_nested(series):
        return pd.factorize(series, use_na_sentinel=False)

    source = series.array.__arrow_array__()
    encoder = _NestedEncoder(source.type)
    codes = np.empty(len(series), dtype=np.int64)
    offset = 0
    for chunk in source.iterchunks():
        # Scratch memory depends on one batch, never on the full nested column.
        for start in range(0, len(chunk), NESTED_BATCH_SIZE):
            batch = chunk.slice(start, NESTED_BATCH_SIZE)
            codes[offset:offset + len(batch)] = encoder.encode(batch)
            offset += len(batch)
    positions = _first_positions(codes, len(encoder.lookup))
    return codes, _NestedValues(source, positions)


def value_counts(series):
    codes, values = factorize_column(series)
    counts = np.bincount(codes, minlength=len(values))
    if is_nested(series):
        values = pd.Index([
            None if value is None else json.dumps(value, default=str)
            for value in values.to_pylist()
        ], dtype=object)
    result = pd.Series(counts, index=values)
    return result[~result.index.isna()].sort_values(ascending=False, kind="stable")
