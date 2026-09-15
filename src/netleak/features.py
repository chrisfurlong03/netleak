"""Build and cache per-dataset feature matrices; select a rung's matrix from the cache.

`build()` streams the pcapML file once and writes cache/<dataset>/p<max_packets>/:

    nprint.i8        int8 raw array (n_samples, max_packets * 960) of nPrint bits, memmapped
    ts_offsets.i16   int16 (n_samples, max_packets) TCP timestamp-option offsets, -1 = none
    varying.npy      bool per column: False if the column is constant across all samples
    hand.parquet     R3 hand features
    meta.parquet     sid, label, group, n_packets
    manifest.json    shapes, versions, source size, timings

`load()` opens that cache and `FeatureSet.matrix(rung, rows)` returns a model-ready X.
Every rung is derived from the same cache, so R0-R2 differ only by `rungs.py`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import rungs
from .datasets import DatasetSpec
from .encode import (
    ENCODER_VERSION,
    HAND_COLUMNS,
    PACKET_BITS,
    TCP_OPT_START,
    TS_VALUE_BITS,
    column_name,
    encode_sample,
    hand_features,
)
from .load import iter_samples

log = logging.getLogger(__name__)
_CHUNK_ROWS = 2000


def cache_dir(
    spec: DatasetSpec, cache_root: Path, max_packets: int | None = None, limit: int | None = None
) -> Path:
    name = f"p{max_packets or spec.max_packets}" + (f"_n{limit}" if limit else "")
    return cache_root / spec.name / name


def build(
    spec: DatasetSpec,
    source: Path,
    cache_root: Path,
    max_packets: int | None = None,
    limit: int | None = None,
    force: bool = False,
    log_every: int = 5000,
) -> Path:
    """Extract features for every sample in `source` (skipped if a fresh cache exists)."""
    max_packets = max_packets or spec.max_packets
    out = cache_dir(spec, cache_root, max_packets, limit)
    manifest_path = out / "manifest.json"
    source_bytes = source.stat().st_size
    if manifest_path.exists() and not force:
        manifest = json.loads(manifest_path.read_text())
        if manifest["encoder_version"] == ENCODER_VERSION and manifest["source_bytes"] == source_bytes:
            log.info("features for %s are cached at %s", spec.name, out)
            return out
    out.mkdir(parents=True, exist_ok=True)

    width = max_packets * PACKET_BITS
    col_min = np.full(width, 127, dtype=np.int8)
    col_max = np.full(width, -128, dtype=np.int8)
    meta, hand = [], []
    nprint_seconds = hand_seconds = 0.0
    started = time.perf_counter()

    with (
        open(out / "nprint.i8.tmp", "wb") as bits_file,
        open(out / "ts_offsets.i16.tmp", "wb") as ts_file,
    ):
        for i, rec in enumerate(iter_samples(spec, source, max_packets, limit)):
            t0 = time.perf_counter()
            row, ts_offsets = encode_sample(rec.ips, max_packets)
            t1 = time.perf_counter()
            hand.append(hand_features(rec.ips, rec.timestamps))
            t2 = time.perf_counter()
            nprint_seconds += t1 - t0
            hand_seconds += t2 - t1

            bits_file.write(row.tobytes())
            ts_file.write(ts_offsets.tobytes())
            np.minimum(col_min, row, out=col_min)
            np.maximum(col_max, row, out=col_max)
            meta.append((rec.sid, rec.label, rec.group, rec.n_packets))
            if log_every and (i + 1) % log_every == 0:
                log.info("%s: %d samples (%.0fs)", spec.name, i + 1, time.perf_counter() - started)

    n = len(meta)
    if n == 0:
        raise ValueError(f"no samples found in {source}")
    (out / "nprint.i8.tmp").replace(out / "nprint.i8")
    (out / "ts_offsets.i16.tmp").replace(out / "ts_offsets.i16")
    np.save(out / "varying.npy", col_min != col_max)
    pd.DataFrame(np.vstack(hand), columns=list(HAND_COLUMNS)).to_parquet(out / "hand.parquet")
    pd.DataFrame(meta, columns=["sid", "label", "group", "n_packets"]).to_parquet(out / "meta.parquet")

    total = time.perf_counter() - started
    manifest = {
        "dataset": spec.name,
        "source": source.name,
        "source_bytes": source_bytes,
        "n_samples": n,
        "max_packets": max_packets,
        "packet_bits": PACKET_BITS,
        "limit": limit,
        "encoder_version": ENCODER_VERSION,
        "rung_version": rungs.rung_version(),
        "read_seconds": total - nprint_seconds - hand_seconds,
        "nprint_seconds": nprint_seconds,
        "hand_seconds": hand_seconds,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("built %s features: %d samples in %.0fs -> %s", spec.name, n, total, out)
    return out


@dataclass
class FeatureSet:
    root: Path
    manifest: dict
    meta: pd.DataFrame
    hand: pd.DataFrame
    nprint: np.memmap
    ts_offsets: np.ndarray
    varying: np.ndarray

    @property
    def n_samples(self) -> int:
        return self.manifest["n_samples"]

    @property
    def max_packets(self) -> int:
        return self.manifest["max_packets"]

    def extract_seconds_per_sample(self, rung: str) -> float:
        key = "hand_seconds" if rungs.get(rung).source == "hand" else "nprint_seconds"
        return (self.manifest[key] + self.manifest["read_seconds"]) / self.n_samples

    def matrix(
        self, rung: str, rows: np.ndarray | None = None, drop_constant: bool = True
    ) -> tuple[np.ndarray, list[str]]:
        """Feature matrix and column names for `rung`, restricted to `rows`.

        nPrint rungs return int8; `drop_constant` removes columns constant over the whole
        dataset (label-free, so it cannot leak). R3 returns float32 hand features.
        """
        r = rungs.get(rung)
        rows = np.arange(self.n_samples) if rows is None else np.asarray(rows)
        if r.source == "hand":
            return self.hand.to_numpy(np.float32)[rows], list(self.hand.columns)

        keep = rungs.column_mask(r, self.max_packets)
        if drop_constant:
            keep &= self.varying
        cols = np.flatnonzero(keep)
        X = np.empty((len(rows), len(cols)), dtype=np.int8)
        for start in range(0, len(rows), _CHUNK_ROWS):
            chunk = rows[start : start + _CHUNK_ROWS]
            X[start : start + len(chunk)] = self.nprint[chunk][:, cols]
        if r.mask_tcp_timestamps:
            _zero_timestamps(X, self.ts_offsets[rows], cols, self.nprint.shape[1])
        return X, [column_name(c) for c in cols]


def _zero_timestamps(X: np.ndarray, ts_offsets: np.ndarray, cols: np.ndarray, width: int) -> None:
    """Zero the TSval/TSecr bits of every TCP timestamp option present in X."""
    sample, packet = np.nonzero(ts_offsets >= 0)
    if sample.size == 0:
        return
    position = np.full(width, -1, dtype=np.int64)
    position[cols] = np.arange(len(cols))
    start = packet * PACKET_BITS + TCP_OPT_START + ts_offsets[sample, packet]
    full_cols = start[:, None] + np.arange(TS_VALUE_BITS)
    x_cols = position[full_cols]
    x_rows = np.broadcast_to(sample[:, None], x_cols.shape)
    present = x_cols >= 0
    X[x_rows[present], x_cols[present]] = 0


def load(
    spec: DatasetSpec, cache_root: Path, max_packets: int | None = None, limit: int | None = None
) -> FeatureSet:
    root = cache_dir(spec, cache_root, max_packets, limit)
    if not (root / "manifest.json").exists():
        raise FileNotFoundError(f"no features at {root}; run `netleak features -d {spec.name}`")
    manifest = json.loads((root / "manifest.json").read_text())
    n, p = manifest["n_samples"], manifest["max_packets"]
    return FeatureSet(
        root=root,
        manifest=manifest,
        meta=pd.read_parquet(root / "meta.parquet"),
        hand=pd.read_parquet(root / "hand.parquet"),
        nprint=np.memmap(root / "nprint.i8", dtype=np.int8, mode="r", shape=(n, p * PACKET_BITS)),
        ts_offsets=np.fromfile(root / "ts_offsets.i16", dtype=np.int16).reshape(n, p),
        varying=np.load(root / "varying.npy"),
    )
