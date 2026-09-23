# Method

## The restriction ladder

Each rung removes a class of information from the same cached features. The definitions live in one
file, `src/netleak/rungs.py`, and every result records a hash of them (`rung_version`) so results
computed under different definitions can never be mixed.

| Rung | What the model sees | Why |
|---|---|---|
| **R0** unrestricted | every nPrint IPv4 + TCP bit | Deliberately illegal. Establishes the leakage ceiling. |
| **R1** benchmark-legal | R0 minus `ipv4_src`, `ipv4_dst`, `tcp_sprt`, `tcp_dprt`, `tcp_seq`, `tcp_ackn` | Exactly the benchmark's rule; comparable to the leaderboard. |
| **R2** behaviour only | R1 minus `ipv4_id` and both checksums, with TCP timestamp values zeroed | IP ID is a per-host counter; checksums are computed over the disallowed addresses and ports, so they smuggle them back in; TCP timestamps carry the host clock. |
| **R3** cheap baseline | 12 summary features: TTL, TCP window, flags, options length, IP length (mean and standard deviation), inter-arrival time (median and IQR) | A deliberately cheap alternative to thousands of bits. |

## How the test set is chosen

| Split | Held out | Controls for |
|---|---|---|
| `random` | a stratified 20% of sessions | nothing; the setting leaderboard numbers usually come from |
| `block` | the last 20% of each class, in capture order | neighbouring, overlapping sessions |
| `grouped` | whole hosts — no machine in both train and test | recognising a capture environment already seen |

`grouped` is impossible on OS detection, where each class is a single host; the harness refuses the
split rather than reporting a number computed on classes absent from training.

## Models

Three models with fixed, untuned settings, so differences come from the features and the split
rather than from tuning: multinomial logistic regression (median imputation, standardisation,
1,000 iterations), a 300-tree random forest, and LightGBM (400 trees, learning rate 0.05, 63
leaves, row fraction 0.8, column fraction 0.5). All weight classes by inverse frequency, because
the metric is balanced accuracy — the mean of the per-class recalls, which gives the smallest class
the same weight as the largest.

## Why the results can be trusted

The harness is tested, not just written. 37 tests run in about 30 seconds without downloading
anything:

- the encoder is checked bit-for-bit against an independent parser (scapy) for every header field;
- the rung masks are checked to be properly nested, and R1 is checked to contain none of the
  disallowed fields — a typo there would silently invalidate every number in this report;
- a **canary dataset** carries its label *only* in the TCP source port. A model must score near
  100% on it at R0 and near chance at R1. This proves the restriction switch actually removes the
  signal it claims to remove, rather than merely renaming columns;
- grouped splits are asserted to share no host between train and test.
