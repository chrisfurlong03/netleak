# AGENTS.md

Guide for coding agents (Claude Code, Codex, Cursor, ...) and for people working like
them. Read this file in full before changing anything. README.md covers the project for a
human reader; this file covers how to work in the code without breaking the experiment.

## What this repo is

A harness that measures how much accuracy on two nPrint/pcapML traffic-classification
benchmarks survives when identifier-like header fields are removed. Every result is one
cell of **dataset × rung × model × split**:

- datasets: `os_detection` (Chris), `video_services` (Winston); `synthetic` for tests
- rungs: `R0` all nPrint bits · `R1` benchmark-legal · `R2` behaviour only · `R3` hand features
- models: `logreg`, `rf`, `lgbm` (default grid); `autogluon` (optional extra)
- splits: `grouped` (no host in both train and test) · `block` (per-class contiguous tail) · `random`

## Setup and verification

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # or: make setup
.venv/bin/pytest -q        # ~30 s, no network, no data. Must pass before you say "done".
.venv/bin/netleak smoke    # end-to-end on synthetic data in a temp dir, < 1 min
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
```

Use Python 3.10-3.12 (`python3.11` on Chris's machine; plain `python3` there is 3.14 and
unsupported). Always call tools from `.venv/bin/`.

## Commands

```bash
netleak download   -d video_services          # data/<dataset>/ (Google Drive via gdown)
netleak inspect    -d video_services          # classes, hosts per class, feature size
netleak features   -d video_services          # cache/<dataset>/p<packets>/ (~15 s)
netleak run        -d video_services --rung R1 --model lgbm --split grouped
netleak grid       -d video_services          # all rungs × default models × dataset splits
netleak importance -d video_services --rung R1 --model lgbm
netleak figures                               # results/figures/*.png + results/summary.csv
make all                                      # everything, both datasets
```

From Python (notebooks should do this, not shell out):

```python
from netleak import datasets, runner
spec = datasets.get("video_services")
result = runner.run_one(spec, "R1", "lgbm", "grouped")   # saves results/video_services/*.json
fitted = runner.fit_one(spec, "R2", "rf", "block")        # same, but returns the model, no save
```

## Module map (`src/netleak/`)

| Module | Owns |
|---|---|
| `datasets.py` | `DatasetSpec` registry: download id, packets per sample, label parsing, host key, valid splits, leaderboard number. **The only place dataset facts live.** |
| `download.py` | Fetch/decompress into `data/<dataset>/`, locate the `.pcapng` |
| `load.py` | Stream pcapML samples (`SampleRecord`); host key for grouped splits; `inspect_dataset` |
| `encode.py` | nPrint field table, IPv4+TCP bit encoder, TCP-timestamp offsets, R3 hand features |
| `features.py` | Build/load the feature cache; `FeatureSet.matrix(rung, rows)` → X |
| `rungs.py` | R0-R3 definitions, `DISALLOWED_FIELDS`, `IDENTIFIER_FIELDS`, `rung_version()`. **The only place restrictions live.** |
| `splits.py` | `grouped` / `block` / `random` splits, feasibility check, stratified subsample |
| `models.py` | `make_model(name)`: fixed, untuned hyperparameters |
| `results.py` | `RunResult` JSON schema, `run_id`, scoring, `load_all` |
| `runner.py` | `fit_one`, `run_one`, `grid`, `importance`, `smoke` |
| `importance.py` | Permutation importance grouped by header field |
| `plots.py` | Figures and `summary.csv`, read only from `results/` |
| `synthetic.py` | Synthetic pcapML writer (behaviour dataset and port-leak canary) |
| `cli.py` | `netleak` Typer app; no logic of its own |

## Invariants: do not break these

1. **Restrictions are defined only in `rungs.py`.** Never filter columns anywhere else
   (not in notebooks, models, or plots). R1 must never contain a `DISALLOWED_FIELDS` field;
   `tests/test_rungs.py` enforces this. Don't weaken those tests to make a change pass.
2. **Changing `rungs.py` or the encoder changes `rung_version` / `ENCODER_VERSION`.** Bump
   `ENCODER_VERSION` in `encode.py` whenever encoder output changes, then re-run
   `netleak features --force` and `netleak grid --force` so `results/` never mixes versions.
3. **Never hand-edit `results/`.** Regenerate with the CLI. Results are committed; `data/`
   and `cache/` are not (both gitignored and reproducible).
4. **Host identity (`meta.group`) is for splitting only**, never a feature.
5. **No per-rung or per-dataset tuning** in `models.py`. The comparison relies on fixed settings.
6. **Seeds are explicit** (`seed=0` default) and flow into subsampling, splits and models.
7. **Splits must be valid for the dataset.** Use `spec.splits`; `make_split` raises
   rather than evaluating on classes absent from training.

## Dataset facts that bite

- **OS detection: one host per class.** 13 source IPs, 13 labels, 1,000 samples each (kali
  439). A host-grouped split is impossible, since it would hold out whole classes, so
  `spec.splits = ("block", "random")`. Any "cross-host" claim for this dataset is untestable.
- **OS labels** are `easylabel_hardlabel` (`windows_windows-8.1`); the task is the hard label.
- **Video services:** each sample holds every SYN/SYN-ACK of a session (median ~140). The
  benchmark uses the first 10, which is what `max_packets=10` gives. 13 client hosts, and 12
  of them appear in several classes, so grouped splits are feasible.
- **Timestamps:** absolute times are garbage (year ~206,000) and about half of samples contain a
  2^32-microsecond jump. Only in-sample ordering is trustworthy. That is why IAT uses
  median/IQR, and why there is no timestamp-based split.
- **Size:** OS detection R0 is 12,439 × 96,000 int8 (1.2 GB cache). After dropping constant
  columns R0/R1/R2 keep 56,290 / 41,690 / 36,890 columns (~2.2 GB float32 at fit time); video
  keeps 4,297 / 2,697 / 2,409. Use `--max-samples` or `--max-packets` if memory is tight, and
  say so in results.
- **Runtime:** video's whole grid takes ~20 min on an M1 Pro. The full OS grid takes **~4-5 h**,
  mostly LightGBM (~35 min per cell at R0: 13 classes × 400 trees over 56k columns) and logistic
  regression (~10 min per cell). To iterate, use `--model rf` (minutes) or `--max-samples`. The
  run is resumable: finished cells are skipped.
- **Reading logreg results:** standardising {-1, 0, 1} bits turns rare bits (e.g. one host's
  address) into large values. Under a grouped split, logistic regression can latch onto those
  bits and fall below chance. The port canary in `tests/test_experiments.py` fails with logreg
  for exactly this reason, which is why it uses rf. Compare models before drawing conclusions
  from a single one.
- **Reading importance:** fields that carry the same information mask each other in
  permutation importance, so a near-zero score means "redundant given the others", not
  "uninformative". On the synthetic data, TTL scores 0 even though it identifies the class.

## Recipes

**Add a dataset.** Append a `DatasetSpec` in `datasets.py` (run `netleak inspect` first to
choose `group_by` and `splits`). Add it to `DATASETS` in the Makefile. Nothing else should
need to change; if something does, that is a harness bug.

**Add a model.** Add a branch to `make_model` and its name to `MODELS` (and to
`DEFAULT_MODELS` only if the grid should run it), plus a colour/label in `plots.py`. It must
accept float32 X and string labels.

**Add or change a rung.** Edit `RUNGS` in `rungs.py`, and add a test in `tests/test_rungs.py`
stating the new invariant. Then follow invariant 2.

**Add a hand feature.** Extend `HAND_STATS` and `hand_features` in `encode.py`, bump
`ENCODER_VERSION`, update `tests/test_encode.py::test_hand_features`.

**Add a figure.** Add a function to `plots.py` that reads the results DataFrame, and call it
from `all_figures`. Keep text in ink colours, models in the fixed `MODEL_COLORS` order.

## Collaboration

- `notebooks/01_os_detection.ipynb` is Chris's; `notebooks/02_video_services.ipynb` is
  Winston's. Don't edit the other person's notebook: open an issue or PR comment instead.
- `report/` (Sphinx) is Winston's.
- Work on a branch (`chris/<topic>`, `winston/<topic>`), open a PR, and have the other person
  review. Run `pytest -q` and `ruff` before pushing.
- Harness changes that alter results (rungs, encoder, splits, models) need a PR description
  that says so and a regenerated `results/`.
