# What the features cost

An accuracy axis alone flatters packet-level representations. The same results carry a cost axis:
how many columns each rung produces, and how long a model takes to fit them.

```{include} _generated/cost.md
```

![Training time against rung, log scale](_generated/figures/cost.png)

The striking entry is R3. Twelve summary features match all 2,409 R2 bits on the video task —
73.8% against 73.7% for LightGBM on a random split — and come within about eight points of the full
benchmark-legal representation on OS detection, while training in well under a second.

Cost scales with the representation, not with the difficulty of the task. An OS sample is 100
packets rather than 10, so R1 carries 41,690 columns against the video task's 2,697, and the 13-class
problem trains one tree per class per boosting iteration: 5,200 trees against 1,600. Those multiply,
and a single LightGBM cell that takes under a minute on video takes about 17 minutes on OS detection.

Most of those columns carry very little. A 100-packet sample is 96,000 bit-columns, the majority of
them near-constant option and padding bits that survive the constant-column filter and then consume
full histogram and gradient cost. For any deployment where inference or retraining cost matters,
the twelve-feature baseline is the honest comparison point.
