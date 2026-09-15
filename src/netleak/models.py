"""Model zoo: every entry is a scikit-learn-style estimator with fit(X, y) / predict(X).

Hyperparameters are fixed and deliberately untuned, so differences between rungs come
from the features, not from per-rung tuning. All models weight classes by inverse
frequency, since the metric is balanced accuracy.

    logreg     linear baseline (median-impute + standardise + multinomial logistic regression)
    rf         random forest
    lgbm       LightGBM gradient boosting
    autogluon  AutoGluon Tabular, the leaderboard's model (needs `pip install -e ".[automl]"`)
"""

from __future__ import annotations

import tempfile

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MODELS: tuple[str, ...] = ("logreg", "rf", "lgbm", "autogluon")
DEFAULT_MODELS: tuple[str, ...] = ("logreg", "rf", "lgbm")


def make_model(name: str, seed: int = 0, n_jobs: int = -1):
    if name == "logreg":
        return make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed),
        )
    if name == "rf":
        return RandomForestClassifier(
            n_estimators=300, class_weight="balanced", n_jobs=n_jobs, random_state=seed
        )
    if name == "lgbm":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=63,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.5,
            class_weight="balanced",
            random_state=seed,
            n_jobs=n_jobs,
            verbose=-1,
        )
    if name == "autogluon":
        return AutoGluonClassifier(seed=seed)
    raise ValueError(f"unknown model {name!r}; choose from {MODELS}")


class AutoGluonClassifier:
    """Minimal fit/predict adapter around `autogluon.tabular.TabularPredictor`."""

    def __init__(self, time_limit: int = 600, presets: str = "medium_quality", seed: int = 0):
        self.time_limit, self.presets, self.seed = time_limit, presets, seed

    def fit(self, X: np.ndarray, y: np.ndarray) -> AutoGluonClassifier:
        import pandas as pd
        from autogluon.tabular import TabularPredictor

        frame = pd.DataFrame(X, columns=[f"f{i}" for i in range(X.shape[1])])
        frame["label"] = y
        self.predictor_ = TabularPredictor(
            label="label",
            eval_metric="balanced_accuracy",
            path=tempfile.mkdtemp(prefix="netleak-autogluon-"),
            verbosity=1,
        ).fit(frame, time_limit=self.time_limit, presets=self.presets)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        import pandas as pd

        frame = pd.DataFrame(X, columns=[f"f{i}" for i in range(X.shape[1])])
        return self.predictor_.predict(frame).to_numpy()
