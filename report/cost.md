# What the features cost

An accuracy axis alone flatters packet-level representations. The same results carry a cost axis:
how many columns each rung produces, and how long a model takes to fit them.

```{include} _generated/cost.md
```

![Training time against rung, log scale](_generated/figures/cost.png)

The striking entry is R3. Twelve summary features match all 2,409 R2 bits on the video task —
73.8% against 73.7% for LightGBM on a random split — and on OS detection they *beat* the 36,890
behaviour-only bits of R2, 69.7% against 66.5%, while fitting in 47 seconds instead of 570.

Cost scales with the representation, not with the difficulty of the task. An OS sample is 100
packets rather than 10, so R1 carries 41,690 columns against the video task's 2,697, and the 13-class
problem trains one tree per class per boosting iteration: 5,200 trees against 1,600. Those multiply,
and a single LightGBM cell that takes under a minute on video takes about 17 minutes on OS detection.

Most of those columns carry very little. A 100-packet sample is 96,000 bit-columns, the majority of
them near-constant option and padding bits that survive the constant-column filter and then consume
full histogram and gradient cost. For any deployment where inference or retraining cost matters,
the twelve-feature baseline is the honest comparison point.

## Were 100 packets ever necessary?

The OS benchmark defines a sample as 100 packets. Re-running the whole grid at 20 packets tests
whether that length earns its cost.

```{include} _generated/ablation.md
```

At the benchmark-legal rung, four fifths of the packets can go for **less than one point** of
balanced accuracy, with five times fewer columns and a fit that takes 210 seconds instead of 800.
The shorter sample costs more at R2 and R3, where the surviving signal is thinner and the per-sample
summaries get noisier — so packet count matters most exactly where the representation is weakest.

This is an ablation, not part of the headline grid: `plots.primary_runs` keeps these runs out of
every reported table and figure, and they are stored alongside the main results under their own
`p20` run identifiers.
