"""Stream samples out of a pcapML file.

pcapML stores `<sample_id>,<label>` as a per-packet pcapng comment and writes each
sample's packets contiguously. `pcapml.iter_packets` parses the pcapng and
`pcapml.parse_comment` the comment; this module adds label normalisation (per
`DatasetSpec`), the host key used for grouped splits, and a contiguity check.
It deliberately avoids `pcapml.samples()`, which builds a DataFrame per sample.
"""

from __future__ import annotations

import socket
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pcapml

from .datasets import DatasetSpec, GroupBy
from .encode import PACKET_BITS, ipv4_bytes


@dataclass
class SampleRecord:
    sid: str
    label: str
    group: str  # host identity for grouped splits; never used as a feature
    ips: list[bytes | None]  # IPv4 packets (None for non-IPv4 frames), truncated to max_packets
    timestamps: list[float]
    n_packets: int  # before truncation


def iter_samples(
    spec: DatasetSpec, path: Path, max_packets: int | None = None, limit: int | None = None
) -> Iterator[SampleRecord]:
    """Yield one `SampleRecord` per pcapML sample, in file order."""
    max_packets = max_packets or spec.max_packets
    seen: set[str] = set()
    sid: str | None = None
    label = ""
    ips: list[bytes | None] = []
    timestamps: list[float] = []
    emitted = 0

    def record() -> SampleRecord:
        return SampleRecord(
            sid=sid or "",
            label=spec.label_from_metadata(label),
            group=group_key(ips, spec.group_by),
            ips=ips[:max_packets],
            timestamps=timestamps[:max_packets],
            n_packets=len(ips),
        )

    for pkt in pcapml.iter_packets(str(path)):
        pkt_sid, pkt_label, *_ = pcapml.parse_comment(pkt.comment)
        if pkt_sid is None or pkt_label is None:
            raise ValueError(f"packet without a pcapML 'sid,label' comment in {path}")
        if pkt_sid != sid:
            if sid is not None:
                yield record()
                emitted += 1
                if limit is not None and emitted >= limit:
                    return
            if pkt_sid in seen:
                raise ValueError(f"sample {pkt_sid} is not contiguous in {path}; run `pcapml sort` first")
            seen.add(pkt_sid)
            sid, label, ips, timestamps = pkt_sid, pkt_label, [], []
        ips.append(ipv4_bytes(pkt.data, pkt.link_type))
        timestamps.append(pkt.timestamp)

    if sid is not None:
        yield record()


def group_key(ips: list[bytes | None], how: GroupBy) -> str:
    """Host identity: most common IPv4 source (of pure SYNs, for "syn_initiator")."""
    counts: Counter[str] = Counter()
    for ip in ips:
        if ip is None:
            continue
        if how == "syn_initiator":
            ihl = (ip[0] & 0x0F) * 4
            is_pure_syn = ip[9] == 6 and len(ip) > ihl + 13 and ip[ihl + 13] & 0x12 == 0x02
            if not is_pure_syn:
                continue
        counts[socket.inet_ntoa(ip[12:16])] += 1
    if not counts:
        return group_key(ips, "src_ip") if how == "syn_initiator" else "unknown"
    return counts.most_common(1)[0][0]


def inspect_dataset(
    spec: DatasetSpec, path: Path, max_packets: int | None = None, limit: int | None = None
) -> dict:
    """Summarise a dataset before paying for feature extraction."""
    max_packets = max_packets or spec.max_packets
    rows = [
        (r.label, r.group, r.n_packets, sum(ip is None for ip in r.ips))
        for r in iter_samples(spec, path, max_packets, limit)
    ]
    df = pd.DataFrame(rows, columns=["label", "group", "n_packets", "non_ipv4"])
    per_class = df.groupby("label").agg(samples=("group", "size"), hosts=("group", "nunique"))
    n = len(df)
    return {
        "samples": n,
        "classes": int(df["label"].nunique()),
        "hosts": int(df["group"].nunique()),
        "hosts_in_multiple_classes": int((df.groupby("group")["label"].nunique() > 1).sum()),
        "packets_per_sample": df["n_packets"].describe().round(1).to_dict(),
        "non_ipv4_packet_fraction": float(
            df["non_ipv4"].sum() / max(1, df["n_packets"].clip(upper=max_packets).sum())
        ),
        "per_class": per_class.sort_values("samples", ascending=False),
        "nprint_cache_gb": n * max_packets * PACKET_BITS / 1e9,
        "float32_train_matrix_gb": 0.8 * n * max_packets * PACKET_BITS * 4 / 1e9,
    }
