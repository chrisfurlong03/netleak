"""Which header fields carry the signal? Permutation importance grouped by nPrint field.

Permuting 96,000 bit columns one at a time is infeasible and uninterpretable, so all
columns of a field (e.g. every `pkt*_ipv4_ttl_*` bit) are shuffled together across
samples, and the drop in balanced accuracy is that field's importance.

Caveat: fields that carry the same information mask each other. If TTL and window size
both identify the class, permuting either alone costs nothing, and both can score ~0.
A near-zero importance means "not needed given the others", not "uninformative".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from .encode import field_of


def field_importance(
    estimator,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    n_repeats: int = 3,
    max_rows: int = 5000,
    seed: int = 0,
) -> pd.DataFrame:
    """One row per field: columns, mean and std drop in balanced accuracy when permuted."""
    rng = np.random.default_rng(seed)
    if len(y) > max_rows:
        keep = rng.choice(len(y), max_rows, replace=False)
        X, y = X[keep], y[keep]
    X = np.array(X, copy=True)
    fields = np.array([field_of(n) for n in feature_names])
    baseline = balanced_accuracy_score(y, estimator.predict(X))

    rows = []
    for name in np.unique(fields):
        cols = np.flatnonzero(fields == name)
        original = X[:, cols].copy()
        drops = []
        for _ in range(n_repeats):
            X[:, cols] = original[rng.permutation(len(y))]
            drops.append(baseline - balanced_accuracy_score(y, estimator.predict(X)))
        X[:, cols] = original
        rows.append((name, len(cols), float(np.mean(drops)), float(np.std(drops))))

    df = pd.DataFrame(rows, columns=["field", "n_columns", "importance_mean", "importance_std"])
    df.attrs["baseline_balanced_accuracy"] = baseline
    return df.sort_values("importance_mean", ascending=False, ignore_index=True)
