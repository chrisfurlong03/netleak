# The data, and two things wrong with it

Both datasets are pcapML-encoded releases from the
[pcapML benchmark suite](https://nprint.github.io/benchmarks/). pcapML stores each sample's label
as a per-packet pcapng comment, which makes the ground truth unambiguous and lets one loader serve
both tasks.

| | OS detection | Streaming video services |
|---|---|---|
| Task | operating system of the sending host, 13 classes | which of four services generated a session |
| Sample | 100 packets, taken sequentially per source IP | the first 10 SYN / SYN-ACK packets of a session |
| Samples | 12,439 | 20,884 |
| Class balance | 1,000 each, except kali-linux at 439 | YouTube 9,410 · Netflix 6,253 · Twitch 3,352 · Amazon 1,869 |
| Hosts | **13 — one per class** | 13 clients, 12 of them appearing in several classes |
| Published best (AutoGluon) | 77.1% | 77.9% |
| Chance | 7.7% | 25% |

Two properties of these releases shaped the study. Neither is documented on the benchmark pages,
and both are findings in their own right.

## OS detection has one host per class

Every operating system in the OS benchmark was captured from exactly one source IP: 13 addresses,
13 labels, a perfect one-to-one correspondence. The consequence is structural, not statistical.

A host-grouped evaluation is impossible on this dataset, because holding out a host means holding
out an entire class. There is therefore **no way to test, on this benchmark, whether a model has
learned "Windows 10" or "the machine at 10.x.x.x"**. Our harness refuses the split instead of
printing a meaningless number, and uses contiguous-block and random splits for this task.

This also explains the R0 result for OS detection, which reaches a perfect score: with the source
address available, the address *is* the label. That number is a measurement of the dataset's
construction, not of any model's ability.

## The timestamps are unusable

Absolute capture times in both releases are implausible — the OS release places packets in the year
~206,000 — and about half of all samples contain a jump of exactly 2³² microseconds, the signature
of a wrapped 32-bit counter. Only the ordering of packets within a sample survives.

Two consequences follow. Inter-arrival time in R3 is summarised with a median and interquartile
range rather than a mean and standard deviation, because one wrap would otherwise dominate the
feature. And no split in this report is chronological: the `block` split holds out a contiguous
block in *file order*, which is a control against neighbouring, overlapping samples, **not** a test
of behaviour over time.
