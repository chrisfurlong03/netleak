"""Regenerate report tables and figures from results/, so the prose can never go stale.

Writes report/_generated/: one markdown table per view, plus a copy of results/figures/.
Run via `make report`; never hand-edit anything under _generated/.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parent
sys.path.insert(0, str(ROOT / "src"))

from netleak import results as results_io  # noqa: E402
from netleak.datasets import REGISTRY  # noqa: E402
from netleak.plots import MODEL_LABELS, SPLIT_LABELS, primary_runs  # noqa: E402

RUNG_LABELS = {
    "R0": "R0 · all bits",
    "R1": "R1 · benchmark-legal",
    "R2": "R2 · behaviour only",
    "R3": "R3 · 12 hand features",
}


def _pct(value: float | None) -> str:
    return "–" if pd.isna(value) else f"{100 * value:.1f}%"


def score_table(df: pd.DataFrame, dataset: str) -> str:
    sub = df[df["dataset"] == dataset]
    if sub.empty:
        return "_No results yet for this dataset._\n"
    table = sub.pivot_table(index=["split", "rung"], columns="model", values="balanced_accuracy")
    models = [m for m in MODEL_LABELS if m in table.columns]
    lines = [
        "| Test-set rule | Representation | " + " | ".join(MODEL_LABELS[m] for m in models) + " |",
        "|---|---|" + "---|" * len(models),
    ]
    for split in SPLIT_LABELS:
        for rung in RUNG_LABELS:
            if (split, rung) not in table.index:
                continue
            row = table.loc[(split, rung)]
            cells = " | ".join(_pct(row.get(m)) for m in models)
            lines.append(f"| {SPLIT_LABELS[split]} | {RUNG_LABELS[rung]} | {cells} |")
    return "\n".join(lines) + "\n"


def cost_table(df: pd.DataFrame) -> str:
    rows = (
        df.groupby(["dataset", "rung"])
        .agg(features=("n_features", "max"), fit=("fit_seconds", "median"))
        .reset_index()
    )
    lines = [
        "| Dataset | Representation | Input columns | Median fit time (s) |",
        "|---|---|---:|---:|",
    ]
    for _, r in rows.iterrows():
        title = REGISTRY[r["dataset"]].title
        rung = RUNG_LABELS[r["rung"]]
        lines.append(f"| {title} | {rung} | {r['features']:,} | {r['fit']:.1f} |")
    return "\n".join(lines) + "\n"


def importance_table(dataset: str, top: int = 6) -> str:
    files = sorted((ROOT / "results" / dataset / "importance").glob("*.csv"))
    if not files:
        return "_No importance run for this dataset yet._\n"
    csv = files[0]
    df = pd.read_csv(csv).head(top)
    lines = [
        f"Field importance from `{csv.stem}`:",
        "",
        "| Header field | Bit columns | Drop in balanced accuracy |",
        "|---|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(f"| `{r['field']}` | {r['n_columns']:,} | {100 * r['importance_mean']:+.1f} points |")
    return "\n".join(lines) + "\n"


def packet_ablation_table(all_runs: pd.DataFrame, dataset: str = "os_detection") -> str:
    """Compare the benchmark's packet count against a shorter sample, where both were run."""
    sub = all_runs[(all_runs["dataset"] == dataset) & all_runs["max_samples"].isna()]
    counts = sorted(sub["max_packets"].unique())
    if len(counts) < 2:
        return "_No packet-count ablation has been run._\n"
    full, short = max(counts), min(counts)
    lines = [
        f"LightGBM, {REGISTRY[dataset].title.split(' (')[0]}, contiguous block split.",
        "",
        f"| Representation | {full} packets | {short} packets | Difference | Columns {full} → {short} |",
        "|---|---:|---:|---:|---:|",
    ]
    for rung in RUNG_LABELS:
        cells = {
            n: sub[
                (sub["max_packets"] == n)
                & (sub["rung"] == rung)
                & (sub["model"] == "lgbm")
                & (sub["split"] == "block")
            ]
            for n in (full, short)
        }
        if any(c.empty for c in cells.values()):
            continue
        a, b = (cells[n].iloc[0] for n in (full, short))
        lines.append(
            f"| {RUNG_LABELS[rung]} | {_pct(a['balanced_accuracy'])} | {_pct(b['balanced_accuracy'])} "
            f"| {100 * (b['balanced_accuracy'] - a['balanced_accuracy']):+.1f} pts "
            f"| {a['n_features']:,} → {b['n_features']:,} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    out = REPORT / "_generated"
    out.mkdir(exist_ok=True)
    df = primary_runs(results_io.load_all(ROOT / "results"))
    for dataset in REGISTRY:
        if dataset == "synthetic":
            continue
        (out / f"scores_{dataset}.md").write_text(score_table(df, dataset))
        (out / f"importance_{dataset}.md").write_text(importance_table(dataset))
    (out / "cost.md").write_text(cost_table(df))
    (out / "ablation.md").write_text(packet_ablation_table(results_io.load_all(ROOT / "results")))
    figures = out / "figures"
    shutil.rmtree(figures, ignore_errors=True)
    shutil.copytree(ROOT / "results" / "figures", figures)
    counts = df.groupby("dataset").size().to_dict()
    (out / "coverage.md").write_text(
        "Experiment cells behind this report: "
        + ", ".join(f"**{n}** for {REGISTRY[d].title}" for d, n in counts.items())
        + f". Rung version `{df['rung_version'].iloc[0]}`, encoder version "
        + f"`{df['encoder_version'].iloc[0]}`, seed {df['seed'].iloc[0]}.\n"
    )
    print(f"wrote {len(list(out.glob('*.md')))} tables and {len(list(figures.glob('*')))} figures")


if __name__ == "__main__":
    main()
