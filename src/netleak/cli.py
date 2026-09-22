"""`netleak` command line. Each command is a thin wrapper over `runner`/`features`/`plots`.

netleak download   -d os_detection
netleak inspect    -d os_detection
netleak features   -d os_detection
netleak run        -d os_detection --rung R1 --model lgbm --split grouped
netleak grid       -d os_detection
netleak importance -d os_detection --rung R1 --model lgbm
netleak figures
netleak smoke
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from . import datasets, features, runner
from .download import download as download_dataset
from .download import find_source
from .load import inspect_dataset
from .models import DEFAULT_MODELS, MODELS
from .paths import Paths, default_paths
from .rungs import RUNG_ORDER, RUNGS
from .splits import SPLITS

app = typer.Typer(help="Feature-leakage audit harness for nPrint/pcapML benchmarks.",
                  no_args_is_help=True, add_completion=False)  # fmt: skip

Dataset = Annotated[str, typer.Option("--dataset", "-d", help=f"One of: {', '.join(datasets.REGISTRY)}")]
MaxPackets = Annotated[int | None, typer.Option(help="Packets per sample (default: the benchmark's).")]
MaxSamples = Annotated[int | None, typer.Option(help="Stratified subsample before splitting (memory).")]
Limit = Annotated[int | None, typer.Option(help="Only read the first N samples (development).")]
Seed = Annotated[int, typer.Option(help="Seed for subsampling, splits and models.")]
Root = Annotated[Path | None, typer.Option(help="Workspace root (default: repo or $NETLEAK_ROOT).")]


def _paths(root: Path | None) -> Paths:
    return Paths(root) if root else default_paths()


def _check(value: str, choices, what: str) -> str:
    if value not in choices:
        raise typer.BadParameter(f"unknown {what} {value!r}; choose from {', '.join(choices)}")
    return value


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")  # fmt: skip


@app.command()
def download(dataset: Dataset, force: bool = False, root: Root = None) -> None:
    """Fetch a dataset into data/<dataset>/ (synthetic is generated locally)."""
    typer.echo(download_dataset(datasets.get(dataset), _paths(root), force))


@app.command()
def inspect(dataset: Dataset, max_packets: MaxPackets = None, limit: Limit = None, root: Root = None) -> None:
    """Class balance, hosts per class and estimated feature size, before extracting."""
    spec = datasets.get(dataset)
    summary = inspect_dataset(spec, find_source(spec, _paths(root)), max_packets, limit)
    per_class = summary.pop("per_class")
    for key, value in summary.items():
        typer.echo(f"{key:>28}: {value:.2f}" if isinstance(value, float) else f"{key:>28}: {value}")
    typer.echo(per_class.to_string())


@app.command("features")
def build_features(dataset: Dataset, max_packets: MaxPackets = None, limit: Limit = None,
                   force: bool = False, root: Root = None) -> None:  # fmt: skip
    """Extract and cache nPrint bits and hand features for every sample."""
    spec, paths = datasets.get(dataset), _paths(root)
    typer.echo(features.build(spec, find_source(spec, paths), paths.cache, max_packets, limit, force))


@app.command()
def run(
    dataset: Dataset,
    rung: Annotated[str, typer.Option(help=f"One of: {', '.join(RUNG_ORDER)}")] = "R1",
    model: Annotated[str, typer.Option(help=f"One of: {', '.join(MODELS)}")] = "lgbm",
    split: Annotated[str, typer.Option(help=f"One of: {', '.join(SPLITS)}")] = "grouped",
    seed: Seed = 0,
    max_packets: MaxPackets = None,
    max_samples: MaxSamples = None,
    root: Root = None,
) -> None:
    """Train and evaluate one cell; writes results/<dataset>/<run_id>.json."""
    result = runner.run_one(
        datasets.get(dataset), _check(rung, RUNGS, "rung"), _check(model, MODELS, "model"),
        _check(split, SPLITS, "split"), paths=_paths(root), seed=seed,
        max_packets=max_packets, max_samples=max_samples,
    )  # fmt: skip
    typer.echo(f"balanced accuracy {result.balanced_accuracy:.3f}  macro-F1 {result.macro_f1:.3f}")


@app.command()
def grid(
    dataset: Dataset,
    model: Annotated[list[str] | None, typer.Option(help="Repeatable; default logreg, rf, lgbm.")] = None,
    seed: Seed = 0,
    max_packets: MaxPackets = None,
    max_samples: MaxSamples = None,
    force: Annotated[bool, typer.Option(help="Re-run cells that already have results.")] = False,
    root: Root = None,
) -> None:
    """Every rung x model x split (skips cells with up-to-date results)."""
    model_names = tuple(_check(m, MODELS, "model") for m in model) if model else DEFAULT_MODELS
    out = runner.grid(datasets.get(dataset), paths=_paths(root), model_names=model_names, seed=seed,
                      max_packets=max_packets, max_samples=max_samples, force=force)  # fmt: skip
    for r in out:
        typer.echo(f"{r.rung} {r.model:<7} {r.split:<8} {r.balanced_accuracy:.3f}")


@app.command()
def importance(
    dataset: Dataset,
    rung: str = "R1",
    model: str = "lgbm",
    split: Annotated[str | None, typer.Option(help="Default: the dataset's first split.")] = None,
    seed: Seed = 0,
    max_packets: MaxPackets = None,
    max_samples: MaxSamples = None,
    root: Root = None,
) -> None:
    """Field-level permutation importance for one cell."""
    df = runner.importance(
        datasets.get(dataset), _check(rung, RUNGS, "rung"), _check(model, MODELS, "model"),
        split and _check(split, SPLITS, "split"), paths=_paths(root), seed=seed,
        max_packets=max_packets, max_samples=max_samples,
    )  # fmt: skip
    typer.echo(df.head(15).to_string(index=False))


@app.command()
def figures(root: Root = None) -> None:
    """Render results/figures/ from every result JSON."""
    from . import plots

    for path in plots.all_figures(_paths(root)):
        typer.echo(path)


@app.command("capture")
def capture_session(
    label: Annotated[str, typer.Option(help="Intended service, e.g. youtube; not a packet label.")],
    interface: Annotated[str, typer.Option(help="Capture interface from dumpcap -D, e.g. en0.")],
    seconds: Annotated[int, typer.Option(min=1, max=600)] = 120,
    content_url: str = "",
    notes: str = "",
    condition: Annotated[str, typer.Option(help="Capture condition, e.g. natural or ipv4_tcp.")] = "natural",
    root: Root = None,
) -> None:
    """Record a timed pilot into data/fresh_video/ and summarize protocol coverage."""
    from .capture import record_session

    typer.echo(
        record_session(
            _paths(root).data / "fresh_video",
            label=label,
            interface=interface,
            seconds=seconds,
            content_url=content_url,
            notes=notes,
            condition=condition,
        )
    )


@app.command()
def smoke(root: Root = None) -> None:
    """End-to-end check on a synthetic dataset in a temp dir; no downloads."""
    root = root or Path(tempfile.mkdtemp(prefix="netleak-smoke-"))
    out = runner.smoke(root)
    typer.echo(f"smoke OK: {len(out)} runs, figures in {Paths(root).figures}")
