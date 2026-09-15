"""Pure-Python nPrint encoder for IPv4 + TCP, and the R3 hand features.

nPrint (Holland et al., CCS '21) gives every header bit its own column: 1 or 0 when the
bit exists in the packet, -1 when it does not (absent header, unused option space,
padding packets). Column names are `<field>_<bit>` in the same order as `nprint -4 -t`,
so feature importances read the same as in the nPrint paper and leaderboard.

A sample of `max_packets` packets becomes one row: the packets' bit vectors concatenated,
columns named `pkt<i>_<field>_<bit>`. Samples with fewer packets are padded with -1.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

import numpy as np

#: Bump whenever encoder output changes; feature caches built by other versions are rebuilt.
ENCODER_VERSION = "1"
FILL = -1

IPV4_FIELDS: tuple[tuple[str, int], ...] = (
    ("ipv4_ver", 4), ("ipv4_hl", 4), ("ipv4_tos", 8), ("ipv4_tl", 16), ("ipv4_id", 16),
    ("ipv4_rbit", 1), ("ipv4_dfbit", 1), ("ipv4_mfbit", 1), ("ipv4_foff", 13),
    ("ipv4_ttl", 8), ("ipv4_proto", 8), ("ipv4_cksum", 16), ("ipv4_src", 32),
    ("ipv4_dst", 32), ("ipv4_opt", 320),
)  # fmt: skip
TCP_FIELDS: tuple[tuple[str, int], ...] = (
    ("tcp_sprt", 16), ("tcp_dprt", 16), ("tcp_seq", 32), ("tcp_ackn", 32), ("tcp_doff", 4),
    ("tcp_res", 3), ("tcp_ns", 1), ("tcp_cwr", 1), ("tcp_ece", 1), ("tcp_urg", 1),
    ("tcp_ackf", 1), ("tcp_psh", 1), ("tcp_rst", 1), ("tcp_syn", 1), ("tcp_fin", 1),
    ("tcp_wsize", 16), ("tcp_cksum", 16), ("tcp_urp", 16), ("tcp_opt", 320),
)  # fmt: skip
FIELDS = IPV4_FIELDS + TCP_FIELDS
IPV4_BITS = sum(n for _, n in IPV4_FIELDS)  # 480 = 60-byte max header
TCP_BITS = sum(n for _, n in TCP_FIELDS)  # 480 = 60-byte max header
PACKET_BITS = IPV4_BITS + TCP_BITS

PACKET_COLUMNS: tuple[str, ...] = tuple(f"{name}_{i}" for name, n in FIELDS for i in range(n))
PACKET_COLUMN_FIELDS: tuple[str, ...] = tuple(name for name, n in FIELDS for _ in range(n))

_BOUNDS: dict[str, tuple[int, int]] = {}
_offset = 0
for _name, _n in FIELDS:
    _BOUNDS[_name] = (_offset, _offset + _n)
    _offset += _n

TCP_OPT_START = _BOUNDS["tcp_opt"][0]
TS_VALUE_BITS = 64  # TCP timestamp option: 32-bit TSval + 32-bit TSecr


def field_bounds(field: str) -> tuple[int, int]:
    """(start, stop) bit positions of `field` within one packet's vector."""
    return _BOUNDS[field]


def column_name(index: int) -> str:
    """Name of a column in a flattened sample row, e.g. 1442 -> 'pkt1_ipv4_ttl_...'."""
    packet, bit = divmod(index, PACKET_BITS)
    return f"pkt{packet}_{PACKET_COLUMNS[bit]}"


def field_of(column: str) -> str:
    """`pkt3_tcp_wsize_7` -> `tcp_wsize`. Hand-feature names are returned unchanged."""
    if column.startswith("pkt") and column[3:4].isdigit():
        return column.split("_", 1)[1].rsplit("_", 1)[0]
    return column


# --- link layer ---------------------------------------------------------------------------

LINKTYPE_ETHERNET = 1
LINKTYPE_LINUX_SLL = 113
_RAW_IP_LINKTYPES = frozenset({0, 12, 14, 101, 228})
_VLAN_ETHERTYPES = frozenset({0x8100, 0x88A8, 0x9100})
_ETHERTYPE_IPV4 = 0x0800


def ipv4_bytes(frame: bytes, link_type: int) -> bytes | None:
    """Strip the link layer; return the IPv4 packet, or None if the frame is not IPv4."""
    payload: bytes | None = None
    if link_type == LINKTYPE_ETHERNET and len(frame) >= 14:
        ethertype, off = struct.unpack_from("!H", frame, 12)[0], 14
        while ethertype in _VLAN_ETHERTYPES and len(frame) >= off + 4:
            ethertype, off = struct.unpack_from("!H", frame, off + 2)[0], off + 4
        payload = frame[off:] if ethertype == _ETHERTYPE_IPV4 else None
    elif link_type == LINKTYPE_LINUX_SLL and len(frame) >= 16:
        payload = frame[16:] if struct.unpack_from("!H", frame, 14)[0] == _ETHERTYPE_IPV4 else None
    elif link_type in _RAW_IP_LINKTYPES:
        payload = frame
    if payload is None or len(payload) < 20 or payload[0] >> 4 != 4:
        return None
    return payload


# --- nPrint bits --------------------------------------------------------------------------


def encode_packet(ip: bytes | None, out: np.ndarray) -> int:
    """Write one packet's nPrint bits into `out` (length PACKET_BITS, pre-filled with FILL).

    Returns the bit offset of the TCP timestamp option's value within the `tcp_opt` field,
    or -1 if there is none. R2 uses it to zero host clock values (see `rungs`).
    """
    if ip is None:
        return -1
    ihl = (ip[0] & 0x0F) * 4
    _put_bits(out, 0, ip[: min(max(ihl, 20), 60, len(ip))])
    if ihl < 20 or ip[9] != 6 or len(ip) <= ihl:
        return -1
    tcp = ip[ihl:]
    doff = (tcp[12] >> 4) * 4 if len(tcp) > 12 else 20
    header_len = min(max(doff, 20), 60, len(tcp))
    _put_bits(out, IPV4_BITS, tcp[:header_len])
    return _timestamp_offset(tcp[20:header_len])


def _put_bits(out: np.ndarray, start: int, header: bytes) -> None:
    bits = np.unpackbits(np.frombuffer(header, dtype=np.uint8))
    out[start : start + bits.size] = bits


def _timestamp_offset(options: bytes) -> int:
    i = 0
    while i < len(options):
        kind = options[i]
        if kind == 0:  # end of option list
            break
        if kind == 1:  # no-op
            i += 1
            continue
        if i + 1 >= len(options) or options[i + 1] < 2:
            break
        length = options[i + 1]
        if kind == 8 and length == 10 and i + 10 <= len(options):
            return (i + 2) * 8
        i += length
    return -1


def encode_sample(ips: Sequence[bytes | None], max_packets: int) -> tuple[np.ndarray, np.ndarray]:
    """Encode a sample's first `max_packets` IPv4 packets.

    Returns (row of length max_packets * PACKET_BITS, int16 timestamp offsets per packet).
    """
    row = np.full(max_packets * PACKET_BITS, FILL, dtype=np.int8)
    ts_offsets = np.full(max_packets, -1, dtype=np.int16)
    for p, ip in enumerate(ips[:max_packets]):
        ts_offsets[p] = encode_packet(ip, row[p * PACKET_BITS : (p + 1) * PACKET_BITS])
    return row, ts_offsets


# --- R3 hand features ---------------------------------------------------------------------

#: Per-packet values and how each is summarised per sample. Inter-arrival time uses
#: median/IQR: the benchmark captures' timestamps carry 2^32-microsecond jumps that
#: would dominate a mean.
HAND_STATS: dict[str, tuple[str, str]] = {
    "ttl": ("mean", "std"),
    "tcp_window": ("mean", "std"),
    "tcp_flags": ("mean", "std"),
    "tcp_options_len": ("mean", "std"),
    "ip_len": ("mean", "std"),
    "iat": ("median", "iqr"),
}
HAND_BASE = tuple(HAND_STATS)
HAND_COLUMNS: tuple[str, ...] = tuple(f"{b}_{s}" for b, stats in HAND_STATS.items() for s in stats)


def hand_features(ips: Sequence[bytes | None], timestamps: Sequence[float]) -> np.ndarray:
    """The R3 feature vector (float32, len(HAND_COLUMNS)); NaN where a value is unavailable."""
    per_packet = np.full((len(ips), len(HAND_BASE) - 1), np.nan)
    for i, ip in enumerate(ips):
        if ip is None:
            continue
        ihl = (ip[0] & 0x0F) * 4
        per_packet[i, 0] = ip[8]
        per_packet[i, 4] = struct.unpack_from("!H", ip, 2)[0]
        if ip[9] == 6 and len(ip) >= ihl + 20:
            tcp = ip[ihl:]
            per_packet[i, 1] = struct.unpack_from("!H", tcp, 14)[0]
            per_packet[i, 2] = tcp[13]
            per_packet[i, 3] = (tcp[12] >> 4) * 4 - 20
    iat = np.diff(np.asarray(timestamps, dtype=float)) if len(timestamps) > 1 else np.zeros(1)

    columns = [per_packet[:, j] for j in range(per_packet.shape[1])] + [iat]
    out = np.full(len(HAND_COLUMNS), np.nan, dtype=np.float32)
    for j, (values, stats) in enumerate(zip(columns, HAND_STATS.values(), strict=True)):
        values = values[~np.isnan(values)]
        if not values.size:
            continue
        if stats == ("mean", "std"):
            out[2 * j], out[2 * j + 1] = values.mean(), values.std()
        else:
            q1, median, q3 = np.percentile(values, [25, 50, 75])
            out[2 * j], out[2 * j + 1] = median, q3 - q1
    return out
