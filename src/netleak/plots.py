"""Report figures and a summary table, rendered from results/*.json only.

    headline.png              balanced accuracy vs rung; rows = split, columns = dataset,
                              one line per model, leaderboard and chance as reference lines
    cost.png                  fit time vs rung (log scale), grouped split
    confusion_<dataset>.png   row-normalised confusion matrix for R1 / LightGBM / grouped
    importance_<...>.png      field-level permutation importance, one per importance CSV
    results/summary.csv       every cell's balanced accuracy, the table view of headline.png

Colours: the first three slots of a CVD-validated categorical palette (one per model,
in fixed order), a single-hue blue ramp for magnitudes, and ink tones for all text.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, to_rgb  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

from . import results as results_io  # noqa: E402
from .datasets import REGISTRY  # noqa: E402
from .paths import Paths  # noqa: E402
from .rungs import RUNG_ORDER  # noqa: E402
from .splits import SPLITS  # noqa: E402

SURFACE, INK, INK_2, MUTED, GRID, BASELINE = (
    "#fcfcfb",
    "#0b0b0b",
    "#52514e",
    "#898781",
    "#e1e0d9",
    "#c3c2b7",
)
MODEL_COLORS = {"logreg": "#2a78d6", "rf": "#eb6834", "lgbm": "#1baf7a", "autogluon": "#4a3aa7"}
MODEL_LABELS = {
    "logreg": "Logistic regression",
    "rf": "Random forest",
    "lgbm": "LightGBM",
    "autogluon": "AutoGluon",
}
BLUE_RAMP = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SPLIT_LABELS = {"grouped": "Grouped by host", "block": "Contiguous block", "random": "Random"}


def _style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "text.color": INK,
        "legend.frameon": False,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    })  # fmt: skip


def _datasets(df: pd.DataFrame) -> list[str]:
    return [name for name in REGISTRY if name in set(df["dataset"])]


def _model_lines(ax, sub: pd.DataFrame, y: str) -> None:
    x = np.arange(len(RUNG_ORDER))
    for model, color in MODEL_COLORS.items():
        values = sub[sub["model"] == model].set_index("rung")[y].reindex(list(RUNG_ORDER))
        if values.isna().all():
            continue
        ax.plot(x, values.to_numpy(), color=color, marker="o", markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=2, label=MODEL_LABELS[model])  # fmt: skip
    ax.set_xticks(x, RUNG_ORDER)
    ax.set_xlim(-0.3, len(RUNG_ORDER) - 0.7)  # identical x positions even in empty/partial panels
    ax.grid(axis="x", visible=False)


def _reference_line(ax, y: float, text: str, color: str) -> None:
    ax.axhline(y, color=color, linewidth=1, zorder=1)
    ax.annotate(text, xy=(1, y), xycoords=("axes fraction", "data"), xytext=(0, 3),
                textcoords="offset points", ha="right", va="bottom", color=color, fontsize=8)  # fmt: skip


def _legend(fig, axes) -> None:
    handles, labels = {}, {}
    for ax in np.ravel(axes):
        for handle, label in zip(*ax.get_legend_handles_labels(), strict=True):
            handles.setdefault(label, handle)
    labels = list(handles)
    fig.legend([handles[k] for k in labels], labels, loc="upper center", ncol=len(labels),
               bbox_to_anchor=(0.5, 1.0), labelcolor=INK_2, handlelength=2.2)  # fmt: skip


def _layout_below_legend(fig, legend_inches: float = 0.45) -> None:
    """tight_layout that reserves a fixed band at the top for the figure legend."""
    fig.tight_layout(rect=(0, 0, 1, 1 - legend_inches / fig.get_size_inches()[1]))


def headline(df: pd.DataFrame, out: Path) -> Path:
    _style()
    names = _datasets(df)
    split_kinds = [s for s in SPLITS if s in set(df["split"])]
    fig, axes = plt.subplots(len(split_kinds), len(names), sharey=True, squeeze=False,
                             figsize=(4.4 * len(names) + 0.8, 3.0 * len(split_kinds) + 0.9))  # fmt: skip
    for i, split in enumerate(split_kinds):
        for j, name in enumerate(names):
            ax = axes[i][j]
            sub = df[(df["dataset"] == name) & (df["split"] == split)]
            _model_lines(ax, sub, "balanced_accuracy")
            ax.set_ylim(0, 1.02)
            ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
            if i == 0:
                ax.set_title(REGISTRY[name].title, loc="left", fontsize=10)
            if j == 0:
                ax.set_ylabel(f"Balanced accuracy\n{SPLIT_LABELS[split]} split")
            if i == len(split_kinds) - 1:
                ax.set_xlabel("Feature restriction rung")

            if split not in REGISTRY[name].splits:
                note = f"Not run: {SPLIT_LABELS[split].lower()} split\nis invalid for this dataset"
                ax.text(0.5, 0.5, note, transform=ax.transAxes, ha="center", va="center",
                        color=MUTED, fontsize=9)  # fmt: skip
                continue
            if REGISTRY[name].leaderboard_bacc:
                _reference_line(ax, REGISTRY[name].leaderboard_bacc,
                                f"Leaderboard {REGISTRY[name].leaderboard_bacc:.1%}", INK_2)  # fmt: skip
            if not sub.empty:
                _reference_line(ax, sub["chance_balanced_accuracy"].median(), "Chance", MUTED)
    _legend(fig, axes)
    _layout_below_legend(fig)
    return _save(fig, out)


def cost(df: pd.DataFrame, out: Path) -> Path:
    """Fit time per rung, on each dataset's strictest split (`spec.splits[0]`)."""
    _style()
    names = _datasets(df)
    fig, axes = plt.subplots(1, len(names), squeeze=False, figsize=(4.4 * len(names) + 0.8, 3.4))
    for j, name in enumerate(names):
        ax = axes[0][j]
        split = REGISTRY[name].splits[0]
        _model_lines(ax, df[(df["dataset"] == name) & (df["split"] == split)], "fit_seconds")
        ax.set_yscale("log")
        ax.set_title(f"{REGISTRY[name].title}\n{SPLIT_LABELS[split]} split", loc="left", fontsize=10)
        ax.set_xlabel("Feature restriction rung")
        if j == 0:
            ax.set_ylabel("Training time (seconds, log scale)")
    _legend(fig, axes)
    _layout_below_legend(fig)
    return _save(fig, out)


def confusion(
    df: pd.DataFrame, out: Path, rung: str = "R1", model: str = "lgbm", split: str | None = None
) -> Path | None:
    """Confusion matrix for one dataset's cell (default split: that dataset's strictest)."""
    split = split or REGISTRY[df["dataset"].iloc[0]].splits[0]
    match = df[(df["rung"] == rung) & (df["model"] == model) & (df["split"] == split)]
    if match.empty:
        return None
    _style()
    row = match.iloc[0]
    labels = list(row["labels"])
    counts = np.asarray(row["confusion_matrix"], dtype=float)
    recall = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)

    size = 2.2 + 0.42 * len(labels)
    fig, ax = plt.subplots(figsize=(size + 1.2, size))
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    image = ax.imshow(recall, cmap=cmap, vmin=0, vmax=1)
    ax.grid(False)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(f"{REGISTRY[row['dataset']].title}\n{rung} · {MODEL_LABELS[model]} · "
                 f"{SPLIT_LABELS[split].lower()} split", loc="left", fontsize=10)  # fmt: skip
    for (i, k), value in np.ndenumerate(recall):
        if value >= 0.005:
            shade = np.dot(to_rgb(cmap(value)), (0.299, 0.587, 0.114))
            ax.text(k, i, f"{value:.0%}", ha="center", va="center", fontsize=7,
                    color="white" if shade < 0.55 else INK)  # fmt: skip
    colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, format=PercentFormatter(1.0))
    colorbar.outline.set_visible(False)
    colorbar.set_label("Share of true class (row-normalised)", color=INK_2)
    fig.tight_layout()
    return _save(fig, out)


def importance_bars(csv: Path, out: Path, top: int = 15) -> Path:
    _style()
    df = pd.read_csv(csv)
    nonzero = df[df["importance_mean"].abs() >= 0.0005]  # zero bars are noise; the CSV keeps them
    df = (nonzero if len(nonzero) else df.head(1)).head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(df) + 1.2))
    y = np.arange(len(df))
    ax.barh(y, df["importance_mean"], height=0.6, color=MODEL_COLORS["logreg"])
    for yi, value in zip(y, df["importance_mean"], strict=True):
        ax.annotate(f"{value:+.3f}", xy=(max(value, 0), yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK_2)  # fmt: skip
    ax.set_yticks(y, df["field"])
    ax.axvline(0, color=BASELINE, linewidth=1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Drop in balanced accuracy when the field is permuted")
    rung, model, split = csv.stem.split("_")[:3]  # run_id: <rung>_<model>_<split>_p<n>_s<seed>
    dataset = csv.parent.parent.name
    title = REGISTRY[dataset].title if dataset in REGISTRY else dataset
    ax.set_title(f"{title}\n{rung} · {MODEL_LABELS.get(model, model)} · "
                 f"{SPLIT_LABELS.get(split, split).lower()} split", loc="left", fontsize=10)  # fmt: skip
    fig.tight_layout()
    return _save(fig, out)


def summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """Balanced accuracy per dataset / split / rung (rows) and model (columns)."""
    table = df.pivot_table(index=["dataset", "split", "rung"], columns="model",
                           values="balanced_accuracy", aggfunc="mean")  # fmt: skip
    return table[[m for m in MODEL_COLORS if m in table.columns]].round(3)


def all_figures(paths: Paths) -> list[Path]:
    df = results_io.load_all(paths.results)
    if df.empty:
        raise FileNotFoundError(f"no results under {paths.results}; run `netleak grid` first")
    paths.figures.mkdir(parents=True, exist_ok=True)
    summary_table(df).to_csv(paths.results / "summary.csv")
    out = [headline(df, paths.figures / "headline.png"), cost(df, paths.figures / "cost.png")]
    for name in _datasets(df):
        out.append(confusion(df[df["dataset"] == name], paths.figures / f"confusion_{name}.png"))
    for csv in sorted(paths.results.glob("*/importance/*.csv")):
        dataset = csv.parent.parent.name
        out.append(importance_bars(csv, paths.figures / f"importance_{dataset}_{csv.stem}.png"))
    return [p for p in out if p is not None]


def _save(fig, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return out
