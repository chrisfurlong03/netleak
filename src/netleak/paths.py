"""Filesystem layout: data/ (raw pcapML), cache/ (features), results/ (JSON + figures).

Everything takes a `Paths`, so tests and `netleak smoke` can run in a throwaway
directory. The default root is the repository checkout; override with NETLEAK_ROOT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def figures(self) -> Path:
        return self.results / "figures"


def default_paths() -> Paths:
    return Paths(Path(os.environ.get("NETLEAK_ROOT", REPO_ROOT)))
