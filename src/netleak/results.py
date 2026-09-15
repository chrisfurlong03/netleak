"""The result record: one JSON file per experiment cell under results/<dataset>/.

`RunResult` is the contract between the harness and the report. Add fields rather than
renaming them, and never edit results/*.json by hand; regenerate with the CLI.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score


@dataclass
class RunResult:
    dataset: str
    rung: str
    model: str
    split: str
    seed: int
    max_packets: int
    max_samples: int | None
    n_train: int
    n_test: int
    n_features: int
    balanced_accuracy: float
    macro_f1: float
    chance_balanced_accuracy: float
    leaderboard_balanced_accuracy: float | None
    labels: list[str]
    confusion_matrix: list[list[int]]  # rows = true label, columns = predicted, order = labels
    extract_seconds_per_sample: float
    select_seconds: float
    fit_seconds: float
    predict_seconds: float
    rung_version: str
    encoder_version: str
    git_sha: str
    timestamp: str
    notes: dict = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return run_id(self.rung, self.model, self.split, self.seed, self.max_packets, self.max_samples)


def run_id(rung: str, model: str, split: str, seed: int, max_packets: int, max_samples: int | None) -> str:
    return (
        f"{rung}_{model}_{split}_p{max_packets}" + (f"_n{max_samples}" if max_samples else "") + f"_s{seed}"
    )


def result_path(results_dir: Path, dataset: str, rid: str) -> Path:
    return results_dir / dataset / f"{rid}.json"


def score(y_true, y_pred, labels: list[str]) -> dict:
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def save(result: RunResult, results_dir: Path) -> Path:
    path = result_path(results_dir, result.dataset, result.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2))
    return path


def load(path: Path) -> RunResult:
    return RunResult(**json.loads(path.read_text()))


def load_all(results_dir: Path) -> pd.DataFrame:
    """Every result as one row (confusion matrices included as lists)."""
    rows = [json.loads(p.read_text()) for p in sorted(results_dir.glob("*/*.json"))]
    return pd.DataFrame(rows)


def git_sha() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()  # fmt: skip
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
