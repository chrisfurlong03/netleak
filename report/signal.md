# What carries the surviving signal

Permuting 96,000 bit columns one at a time is neither feasible nor interpretable, so importance is
computed per **header field**: every bit of a field is shuffled together across samples, and the
drop in balanced accuracy is that field's score.

## Streaming video services

```{include} _generated/importance_video_services.md
```

![Field importance at R1 for video services](_generated/figures/importance_video_services_R1_lgbm_grouped_p10_s0.png)

TCP options dominate, followed by TTL. Both plausibly encode the operating system and network path
of the *client*, which is consistent with the host sensitivity seen in the results: even at the
benchmark-legal rung, part of what the model uses describes the machine rather than the service.

Third is `ipv4_id` — a per-host counter, and an identifier-like field that the benchmark permits.
That is precisely the kind of residual leakage R2 was defined to remove.

## OS detection

```{include} _generated/importance_os_detection.md
```

The ranking splits cleanly in two. The top three fields — TTL (+40.9 points), TCP window size
(+22.3) and the TCP option block (+21.2) — are exactly the stack characteristics a classical OS
fingerprinter uses. At the benchmark-legal rung, most of what the model relies on is legitimate
behavioural signal.

Below them sit `ipv4_id` (+7.2) and `ipv4_cksum` (+6.0): the two fields R2 removes. Their combined
contribution is close to the 14-point R1-to-R2 drop, which is a useful consistency check — the
information those fields carry is not recoverable from the rest of the header, or retraining at R2
would have made it back.

`ipv4_cksum` is the unambiguous one. An IPv4 header checksum is a function of the header, including
both addresses, so a model that reads it is reading a compressed form of the source and destination
the benchmark forbids. Its importance here — six points of balanced accuracy — is direct evidence
that the disallowed list does not achieve what it was designed to achieve. This is why R2 removes
both checksums, and the measurement confirms the hypothesis rather than assuming it.

`ipv4_id` is the larger of the two and the more interesting, because it is genuinely two things at
once. It is a per-host counter, and it is also a real OS fingerprint: stacks differ in how
they generate it, with some randomising and others incrementing. Permuting it costs seven points,
but we cannot attribute that cleanly to leakage. See [](limitations.md).

## A caveat on reading these numbers

Fields that carry the same information mask one another. If TTL and window size both identify the
class, permuting either alone costs nothing and both can score near zero. A near-zero importance
means "redundant given the others", not "uninformative" — on our synthetic fixture, TTL scores zero
even though it alone determines the label. Error bars, where shown, are the spread over three
shuffles: they describe the permutation, not uncertainty over datasets, splits or model fits.
