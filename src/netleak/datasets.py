"""Dataset registry: the only place dataset facts live.

To add a dataset, append a `DatasetSpec` to `REGISTRY`. Nothing else in the harness
hard-codes a dataset name, sample length, label format or leaderboard number.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

#: How to recover host identity for grouped splits.
#: - "src_ip": most common IPv4 source address in the sample.
#: - "syn_initiator": most common source of pure SYNs (the client), else "src_ip".
GroupBy = Literal["src_ip", "syn_initiator"]


def _identity(label: str) -> str:
    return label


def _hard_label(label: str) -> str:
    """OS-detection labels are `easylabel_hardlabel`; the benchmark task is the hard label."""
    return label.split("_", 1)[1] if "_" in label else label


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    title: str
    benchmark_url: str
    gdrive_id: str | None  # None = generated locally (synthetic)
    max_packets: int  # packets per sample, as defined by the benchmark
    n_classes: int
    group_by: GroupBy
    leaderboard_bacc: float | None  # best published balanced accuracy
    label_from_metadata: Callable[[str], str] = _identity
    splits: tuple[str, ...] = ("grouped", "block", "random")  # split kinds valid for this data


OS_DETECTION = DatasetSpec(
    name="os_detection",
    title="nPrint OS detection (13 classes)",
    benchmark_url="https://nprint.github.io/benchmarks/os_detection/nprint_os_detection.html",
    gdrive_id="1hlyGHqCgxPofS0HvCCl-ToKR-XbBtuPV",
    max_packets=100,
    n_classes=13,
    group_by="src_ip",
    leaderboard_bacc=0.771,
    label_from_metadata=_hard_label,
    # Each OS class was captured from exactly one source IP (13 hosts, 13 classes), so a
    # host-grouped split would hold out whole classes. Block and random splits only.
    splits=("block", "random"),
)

VIDEO_SERVICES = DatasetSpec(
    name="video_services",
    title="nPrint streaming video services (4 classes)",
    benchmark_url=(
        "https://nprint.github.io/benchmarks/application_identification/streaming_video_services.html"
    ),
    gdrive_id="13E6bte1cXut_XqxyCdBLWX97zeEm-MXR",
    # The release keeps every SYN / SYN-ACK of a session (median ~140); the benchmark
    # task uses the first 10, which is exactly what truncation to max_packets does.
    max_packets=10,
    n_classes=4,
    group_by="syn_initiator",
    leaderboard_bacc=0.779,
)

SYNTHETIC = DatasetSpec(
    name="synthetic",
    title="Synthetic fixture (3 classes, used by tests and `netleak smoke`)",
    benchmark_url="",
    gdrive_id=None,
    max_packets=10,
    n_classes=3,
    group_by="src_ip",
    leaderboard_bacc=None,
)

REGISTRY: dict[str, DatasetSpec] = {s.name: s for s in (OS_DETECTION, VIDEO_SERVICES, SYNTHETIC)}


def get(name: str) -> DatasetSpec:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown dataset {name!r}; choose from {sorted(REGISTRY)}") from None
