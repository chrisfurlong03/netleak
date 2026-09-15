"""The feature-restriction ladder R0-R3: the single source of truth for what each rung sees.

    R0  unrestricted     every nPrint IPv4+TCP bit, including the disallowed fields
    R1  benchmark-legal  R0 minus DISALLOWED_FIELDS (the OS-detection benchmark's rule)
    R2  behaviour only   R1 minus IDENTIFIER_FIELDS, TCP timestamp-option values zeroed
    R3  cheap baseline   the hand features in `encode.HAND_COLUMNS`

Changing anything here changes `rung_version()`, which every result records; re-run the
grid afterwards so results/ never mixes definitions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .encode import FIELDS, HAND_COLUMNS, PACKET_COLUMN_FIELDS

#: Forbidden by the nPrint OS-detection benchmark: they identify the host or connection.
DISALLOWED_FIELDS = frozenset({"ipv4_src", "ipv4_dst", "tcp_sprt", "tcp_dprt", "tcp_seq", "tcp_ackn"})

#: Also removed at R2. IP ID is a per-host counter; both checksums are computed over the
#: disallowed addresses and ports, so they carry that information into R1.
IDENTIFIER_FIELDS = frozenset({"ipv4_id", "ipv4_cksum", "tcp_cksum"})


@dataclass(frozen=True)
class Rung:
    name: str
    description: str
    source: Literal["nprint", "hand"]
    drop_fields: frozenset[str] = frozenset()
    mask_tcp_timestamps: bool = False  # zero TSval/TSecr bits (they encode the host clock)


RUNGS: dict[str, Rung] = {
    r.name: r
    for r in (
        Rung("R0", "Unrestricted: all nPrint IPv4+TCP bits", "nprint"),
        Rung("R1", "Benchmark-legal: disallowed fields removed", "nprint", DISALLOWED_FIELDS),
        Rung(
            "R2",
            "Behaviour only: identifiers, checksums and TCP timestamps removed",
            "nprint",
            DISALLOWED_FIELDS | IDENTIFIER_FIELDS,
            mask_tcp_timestamps=True,
        ),
        Rung("R3", "Cheap baseline: six hand-picked header features", "hand"),
    )
}
RUNG_ORDER: tuple[str, ...] = tuple(RUNGS)


def get(rung: str | Rung) -> Rung:
    if isinstance(rung, Rung):
        return rung
    try:
        return RUNGS[rung]
    except KeyError:
        raise KeyError(f"unknown rung {rung!r}; choose from {list(RUNGS)}") from None


def packet_mask(rung: str | Rung) -> np.ndarray:
    """Boolean keep-mask over one packet's nPrint columns (length PACKET_BITS)."""
    r = get(rung)
    if r.source != "nprint":
        raise ValueError(f"{r.name} does not use nPrint bits")
    return ~np.isin(np.array(PACKET_COLUMN_FIELDS), sorted(r.drop_fields))


def column_mask(rung: str | Rung, max_packets: int) -> np.ndarray:
    """Boolean keep-mask over a flattened sample row (length max_packets * PACKET_BITS)."""
    return np.tile(packet_mask(rung), max_packets)


def rung_version() -> str:
    """Short hash of the rung definitions, nPrint field layout and hand-feature names."""
    payload = {
        "rungs": [[r.name, r.source, sorted(r.drop_fields), r.mask_tcp_timestamps] for r in RUNGS.values()],
        "fields": FIELDS,
        "hand": HAND_COLUMNS,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
