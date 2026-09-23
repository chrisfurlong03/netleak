# Results

Balanced accuracy on held-out test sessions. Every figure below is regenerated from `results/`.

![Balanced accuracy against restriction rung, for both datasets and every split](_generated/figures/headline.png)

## Streaming video services

```{include} _generated/scores_video_services.md
```

Three things to read off this table.

**Identifier fields are worth about 15 points.** LightGBM on a random split falls from 91.5% at R0
to 76.0% at R1 — that gap is what the six disallowed fields were contributing. The R1 figure sits
just under the published 77.9%, with untuned off-the-shelf models, which suggests the benchmark-legal
rung is a fair reproduction of the leaderboard setting rather than a weakened one.

**Holding out hosts costs twice as much as restricting features.** The same R1 LightGBM model drops
from 76.0% on a random split to 45.5% when no client host is shared between train and test. Even at
R0, with every identifier bit available, the grouped split reaches only 56.4%. Whatever the
benchmark rewards, a large part of it does not survive a change of capture environment.

**The block split behaves like the random split**, differing by about a point. Neighbouring
sessions are therefore not the source of the inflation; hosts are.

![Confusion matrix for video services at R1 under a host-grouped split](_generated/figures/confusion_video_services.png)

Under the grouped split the model collapses onto the two largest services: Netflix and YouTube
absorb almost every prediction, Twitch retains 46% recall, and Amazon — with only 9 test sessions
in this fold — is never predicted at all. The mechanism is visible in the features: TTL, window
size and option length vary far more between capture hosts (TTL 61 to 133 across hosts) than between
services on the same host (within about one TTL count). The held-out host's signature resembles
training hosts that only ever served Netflix and YouTube, and the predictions follow.

## OS detection

```{include} _generated/scores_os_detection.md
```

R0 reaching a perfect score is the dataset speaking, not the model: with one host per class, the
source address alone determines the label. Logistic regression gets 99.8% there, which says the 13
classes are nearly linearly separable once the address is visible. The informative comparisons are
below it.

**The benchmark-legal rung is not a weakened one.** LightGBM reaches 80.7% at R1, above the
published 77.1%. Our split implementation, feature pipeline and model differ from the benchmark's,
so this is not a matched reproduction and we do not claim to beat it — but it does mean that what
follows is measured against a strong R1, not a handicapped one.

**Removing the fields the benchmark still permits costs 14 points.** R1 to R2 drops LightGBM from
80.7% to 66.5% and random forest from 76.7% to 63.1%. On the video task the same step costs about
two points. Whatever the disallowed list was designed to catch, it leaves substantially more
host-linked signal on OS detection than on video — see [](signal.md) for which fields, and
[](limitations.md) for why the OS case is not purely leakage.

**Twelve summary features beat 36,890 behaviour-only bits.** R3 reaches 69.7% against R2's 66.5%.
A representation three thousand times smaller is *more* accurate here, which is hard to reconcile
with the idea that the value of packet-level features lies in their breadth.

**The block split matches the random split** to within 1.5 points at every rung, so contiguity
between neighbouring samples is not inflating these numbers. Host grouping, the control that did
matter on video, cannot be run here at all.
