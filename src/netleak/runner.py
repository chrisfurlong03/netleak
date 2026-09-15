"""Run experiments: one grid cell, the full grid, field importance, or the smoke test.

Notebooks should call these functions directly; `cli.py` is a thin wrapper around them.
A cell is (dataset, rung, model, split, seed, max_packets, max_samples) and produces
one `RunResult` JSON under results/<dataset>/.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import features, models, results, rungs, splits
from .datasets import SYNTHETIC, DatasetSpec
from .download import download, find_source
from .encode import ENCODER_VERSION
from .importance import field_importance
from .paths import Paths, default_paths

log = logging.getLogger(__name__)


@dataclass
class Fitted:
    result: results.RunResult
    estimator: object
    X_test: np.ndarray
    y_test: np.ndarray
    feature_names: list[str]


def fit_one(
    spec: DatasetSpec,
    rung: str,
    model: str,
    split: splits.SplitKind,
    *,
    paths: Paths | None = None,
    seed: int = 0,
    max_packets: int | None = None,
    max_samples: int | None = None,
    test_size: float = 0.2,
) -> Fitted:
    """Train and evaluate one cell from cached features (run `features.build` first)."""
    paths = paths or default_paths()
    fs = features.load(spec, paths.cache, max_packets)
    labels = fs.meta["label"].to_numpy(dtype=str)
    groups = fs.meta["group"].to_numpy(dtype=str)

    rows = splits.subsample(labels, max_samples, seed)
    train, test = splits.make_split(labels[rows], groups[rows], split, test_size, seed)
    train_rows, test_rows = rows[train], rows[test]

    t0 = time.perf_counter()
    X_train, names = fs.matrix(rung, train_rows)
    X_test, _ = fs.matrix(rung, test_rows)
    select_seconds = time.perf_counter() - t0

    estimator = models.make_model(model, seed)
    t0 = time.perf_counter()
    estimator.fit(X_train.astype(np.float32), labels[train_rows])
    fit_seconds = time.perf_counter() - t0
    del X_train

    X_test = X_test.astype(np.float32)
    t0 = time.perf_counter()
    y_pred = estimator.predict(X_test)
    predict_seconds = time.perf_counter() - t0

    class_labels = sorted(set(labels[rows]))
    y_test = labels[test_rows]
    result = results.RunResult(
        dataset=spec.name,
        rung=rung,
        model=model,
        split=split,
        seed=seed,
        max_packets=fs.max_packets,
        max_samples=max_samples,
        n_train=len(train_rows),
        n_test=len(test_rows),
        n_features=len(names),
        chance_balanced_accuracy=1 / len(set(y_test)),
        leaderboard_balanced_accuracy=spec.leaderboard_bacc,
        labels=class_labels,
        extract_seconds_per_sample=fs.extract_seconds_per_sample(rung),
        select_seconds=select_seconds,
        fit_seconds=fit_seconds,
        predict_seconds=predict_seconds,
        rung_version=rungs.rung_version(),
        encoder_version=ENCODER_VERSION,
        git_sha=results.git_sha(),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        notes={"test_classes_missing": sorted(set(class_labels) - set(y_test))},
        **results.score(y_test, y_pred, class_labels),
    )
    return Fitted(result, estimator, X_test, y_test, names)


def run_one(spec: DatasetSpec, rung: str, model: str, split: splits.SplitKind, *,
            paths: Paths | None = None, **kwargs) -> results.RunResult:  # fmt: skip
    """`fit_one`, then save the result JSON. kwargs: seed, max_packets, max_samples, test_size."""
    paths = paths or default_paths()
    result = fit_one(spec, rung, model, split, paths=paths, **kwargs).result
    results.save(result, paths.results)
    log.info(
        "%s %s %-6s %-7s bacc=%.3f f1=%.3f features=%d fit=%.1fs",
        spec.name, rung, model, split, result.balanced_accuracy, result.macro_f1,
        result.n_features, result.fit_seconds,
    )  # fmt: skip
    return result


def grid(
    spec: DatasetSpec,
    *,
    paths: Paths | None = None,
    rung_names: tuple[str, ...] = rungs.RUNG_ORDER,
    model_names: tuple[str, ...] = models.DEFAULT_MODELS,
    split_kinds: tuple[str, ...] | None = None,
    seed: int = 0,
    max_packets: int | None = None,
    max_samples: int | None = None,
    force: bool = False,
) -> list[results.RunResult]:
    """Every rung x model x split (default: `spec.splits`). Up-to-date cells are skipped."""
    paths = paths or default_paths()
    packets = max_packets or spec.max_packets
    out = []
    for rung in rung_names:
        for model in model_names:
            for split in split_kinds or spec.splits:
                rid = results.run_id(rung, model, split, seed, packets, max_samples)
                path = results.result_path(paths.results, spec.name, rid)
                if path.exists() and not force:
                    existing = results.load(path)
                    if (
                        existing.rung_version == rungs.rung_version()
                        and existing.encoder_version == ENCODER_VERSION
                    ):
                        out.append(existing)
                        continue
                out.append(run_one(spec, rung, model, split, paths=paths, seed=seed,
                                   max_packets=max_packets, max_samples=max_samples))  # fmt: skip
    return out


def importance(
    spec: DatasetSpec,
    rung: str = "R1",
    model: str = "lgbm",
    split: str | None = None,
    *,
    paths: Paths | None = None,
    n_repeats: int = 3,
    **kwargs,
) -> pd.DataFrame:
    """Field-level permutation importance on the test split (default split: `spec.splits[0]`).

    Saved as CSV under results/<dataset>/importance/.
    """
    paths = paths or default_paths()
    fitted = fit_one(spec, rung, model, split or spec.splits[0], paths=paths, **kwargs)
    df = field_importance(fitted.estimator, fitted.X_test, fitted.y_test, fitted.feature_names,
                          n_repeats=n_repeats, seed=fitted.result.seed)  # fmt: skip
    path = paths.results / spec.name / "importance" / f"{fitted.result.run_id}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("importance -> %s (top: %s)", path, ", ".join(df["field"].head(5)))
    return df


def smoke(root: Path) -> list[results.RunResult]:
    """End to end on the synthetic dataset in `root`: data, features, grid, importance, figures."""
    from . import plots

    paths = Paths(root)
    spec = SYNTHETIC
    download(spec, paths)
    features.build(spec, find_source(spec, paths), paths.cache)
    out = grid(spec, paths=paths)
    importance(spec, "R1", "rf", "grouped", paths=paths)
    plots.all_figures(paths)
    return out
