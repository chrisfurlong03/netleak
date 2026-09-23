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

## A caveat on reading these numbers

Fields that carry the same information mask one another. If TTL and window size both identify the
class, permuting either alone costs nothing and both can score near zero. A near-zero importance
means "redundant given the others", not "uninformative" — on our synthetic fixture, TTL scores zero
even though it alone determines the label. Error bars, where shown, are the spread over three
shuffles: they describe the permutation, not uncertainty over datasets, splits or model fits.
