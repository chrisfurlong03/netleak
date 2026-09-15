"""Train/test splits. The split kind is itself an audit axis.

- "grouped": no host (`meta.group`) appears in both train and test, so a model cannot
  score by recognising a host it has already seen. Needs several hosts per class; it is
  impossible on OS detection, where every class is a single host.
- "block": each class's last `test_size` fraction of samples, in file order, is held
  out as one contiguous block. Neighbouring samples (overlapping flows, adjacent
  windows) stay on one side. A within-host control, weaker than "grouped".
- "random": a plain stratified split, the setting most leaderboard numbers come from.

Every split refuses to produce a test set containing a class absent from training.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

SplitKind = Literal["grouped", "block", "random"]
SPLITS: tuple[SplitKind, ...] = ("grouped", "block", "random")


def make_split(
    labels: np.ndarray,
    groups: np.ndarray,
    kind: SplitKind,
    test_size: float = 0.2,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (train_indices, test_indices) into `labels`."""
    index = np.arange(len(labels))
    if kind == "random":
        train, test = train_test_split(index, test_size=test_size, stratify=labels, random_state=seed)
    elif kind == "grouped":
        folds = StratifiedGroupKFold(n_splits=max(2, round(1 / test_size)), shuffle=True, random_state=seed)
        train, test = next(folds.split(index, labels, groups))
        overlap = set(groups[train]) & set(groups[test])
        assert not overlap, f"grouped split leaked {len(overlap)} hosts into both sides"
    elif kind == "block":
        in_test = np.zeros(len(labels), dtype=bool)
        for label in np.unique(labels):
            members = index[labels == label]  # file order
            in_test[members[-max(1, round(len(members) * test_size)) :]] = True
        train, test = index[~in_test], index[in_test]
    else:
        raise ValueError(f"unknown split {kind!r}; choose from {SPLITS}")

    untrained = set(labels[test]) - set(labels[train])
    if untrained:
        raise ValueError(
            f"{kind} split puts every sample of {sorted(untrained)} in the test set (too few "
            f"hosts per class?); use a split listed in the dataset's `splits`"
        )
    return np.sort(train), np.sort(test)


def subsample(labels: np.ndarray, max_samples: int | None, seed: int = 0) -> np.ndarray:
    """Stratified subset of at most `max_samples` indices (all indices if None)."""
    index = np.arange(len(labels))
    if max_samples is None or max_samples >= len(labels):
        return index
    _, counts = np.unique(labels, return_counts=True)
    stratify = labels if counts.min() >= 2 else None
    kept, _ = train_test_split(index, train_size=max_samples, stratify=stratify, random_state=seed)
    return np.sort(kept)
