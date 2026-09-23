# Limitations, and what we would do next

We would rather state these plainly than have a reader find them.

**The grouped results rest on one partition of 13 hosts.** With four services and 13 client hosts,
a single fold leaves as few as 9 Amazon test sessions. One prediction moves that class's recall by
11 points and four-class balanced accuracy by nearly 3. The direction of the effect is large and
consistent, but the exact numbers are noisy. Leave-one-host-out, averaged over all 13 folds, would
be the defensible version and is the first thing we would add.

**Logistic regression does not converge on the OS matrix.** It stops at the 1,000-iteration cap, so
those cells report the state of an optimiser that was still moving, not a fitted model. Its
standardisation step also inflates rare bits — one host's address bit becomes a large value — which
is why it can behave erratically under a grouped split. Read the tree models first.

**No result here is chronological.** The timestamps are unusable, so the `block` split holds out a
contiguous block in file order. It controls for neighbouring, overlapping samples; it is not a test
of drift over time.

**Cross-host generalisation is untestable on OS detection.** One host per class means the question
cannot be asked of this benchmark at all. That limits the central claim: the two-task comparison
holds for feature restriction, but the split axis could only be measured on the video task.

**On OS detection, R2 removes fields that are identifying *and* behavioural.** IP ID generation and
TCP timestamp clock behaviour are classic OS-fingerprinting signals — the same ones tools like p0f
use — and they are also host-linked. So the 14-point R1-to-R2 drop on this task cannot be read as
"14 points of leakage removed"; part of it is real OS signal removed along with the identifiers.
The checksum component is unambiguous leakage, and the video task, where the same step costs about
two points, is the cleaner measurement. R2 is the right rung for asking *what survives without
host-linked fields*; it is not a measurement of what an OS classifier legitimately knows.

**Permutation importance shows redundancy, not causation.** See the caveat in
[](signal.md).

**One fresh-capture pilot is not a drift measurement.** The ten recent sessions in the video
notebook show that frozen historical models transfer poorly to traffic captured today, but client,
browser, network path, CDN and service implementation all differ simultaneously. It indicates a
direction and justifies a larger collection; it does not isolate a cause.

## Next

The most valuable additions, in order: leave-one-host-out evaluation on the video task to replace
the single grouped fold; a packet-count ablation (`--max-packets 20`) to test whether the
benchmark's 100-packet samples were ever necessary; and a properly designed fresh-traffic collection
with established service attribution, following the protocol in `docs/fresh-captures.md`.
