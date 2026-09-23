# Does the classifier know the service, or the machine?

**Winston Li and Chris Furlong** · CMSC 25422, Machine Learning for Computer Systems

Reported accuracies on network traffic-classification benchmarks sit close to ceiling. It is not
always clear what the model learned. Packet-level representations such as
[nPrint](https://nprint.github.io/nprint/) expose every header bit, including fields that identify
the *host* rather than its *behaviour*: source and destination addresses, ports, TCP sequence and
acknowledgment numbers. A classifier that keys on those fields scores well on a held-out split
drawn from the same capture and then fails on any other network.

The nPrint OS-detection benchmark already disallows exactly those fields, which is an
acknowledgment that the risk is real. The size of the effect has not been measured, and it is not
known whether other tasks on the leaderboard share the problem. This report measures it on two
tasks with one shared pipeline, along two axes at once: **which header fields the model may see**,
and **how the test set is chosen**.

Three results, stated plainly:

1. Removing the disallowed identifier fields costs a large, measurable share of benchmark accuracy
   on both tasks.
2. On streaming video, *how the test set is chosen* matters more than *which features are removed*.
   Holding out whole client hosts costs roughly twice what the feature restriction does.
3. Twelve hand-picked header features match thousands of nPrint bits on the video task, at a small
   fraction of the training cost.

```{include} _generated/coverage.md
```

```{toctree}
:maxdepth: 2
:caption: Report

question
data
method
results
cost
signal
limitations
```

```{toctree}
:maxdepth: 1
:caption: Notebooks

notebooks/01_os_detection
notebooks/02_video_services
```

## Reproducing this report

```bash
git clone https://github.com/chrisfurlong03/netleak && cd netleak
make setup && make test    # 37 tests, ~30 s, no data required
make all                   # downloads both datasets, runs every cell, renders figures
make report                # rebuilds this site from results/
```

Every number and figure here is generated from `results/`, one JSON file per experiment. Nothing
in this report is typed in by hand.

## Acknowledgements

Datasets: the [pcapML benchmarks](https://nprint.github.io/benchmarks/) for OS detection and
streaming video services. The video sessions derive from Bronzino et al. (2019), filtered by
Holland et al. (2021); nPrint is Holland et al., CCS 2021.

AI tools: Claude Code (Anthropic) assisted with planning, implementing and testing the harness, and
with drafting this report; Codex assisted with the fresh-capture pilot. The experimental design,
the interpretation and the conclusions are ours.
