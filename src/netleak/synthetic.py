"""A tiny synthetic pcapML dataset for tests and `netleak smoke` (no downloads needed).

Three classes of hosts. With `signal="behaviour"` the classes differ in TTL, TCP window
and MSS, as real operating systems do. With `signal="port"` they are identical except
for the TCP source port: a leakage canary that R0 can classify and R1 must not.
"""

from __future__ import annotations

import random
import socket
import struct
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

CLASSES = ("alpha", "beta", "gamma")
_BEHAVIOUR = {"alpha": (64, 29200, 1460), "beta": (128, 8192, 1380), "gamma": (255, 65535, 1200)}

TCP_SYN, TCP_ACK = 0x02, 0x10


def ipv4_tcp_frame(
    *,
    src: str,
    dst: str,
    sport: int,
    dport: int,
    ttl: int = 64,
    window: int = 29200,
    flags: int = TCP_ACK,
    seq: int = 0,
    ack: int = 0,
    ip_id: int = 0,
    mss: int | None = None,
    timestamp: tuple[int, int] | None = None,
    payload: bytes = b"",
) -> bytes:
    """An Ethernet/IPv4/TCP frame with a valid IPv4 checksum (TCP checksum left 0)."""
    options = b""
    if mss is not None:
        options += struct.pack("!BBH", 2, 4, mss)
    if timestamp is not None:
        options += b"\x01\x01" + struct.pack("!BBII", 8, 10, *timestamp)
    options += b"\x00" * (-len(options) % 4)
    doff = (20 + len(options)) // 4
    tcp = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, doff << 4, flags, window, 0, 0)
    tcp += options + payload
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), ip_id, 0x4000, ttl, 6, 0,
        socket.inet_aton(src), socket.inet_aton(dst),
    )  # fmt: skip
    ip = ip[:10] + struct.pack("!H", _checksum(ip)) + ip[12:]
    ethernet = b"\x02\x00\x00\x00\x00\x01" + b"\x02\x00\x00\x00\x00\x02" + b"\x08\x00"
    return ethernet + ip + tcp


def _checksum(header: bytes) -> int:
    total = sum(struct.unpack(f"!{len(header) // 2}H", header))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def write_pcapng(path: Path, packets: Iterable[tuple[float, bytes, str]], link_type: int = 1) -> Path:
    """Write (timestamp, frame, comment) triples as a pcapML-style pcapng file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<IIIHHqI", 0x0A0D0D0A, 28, 0x1A2B3C4D, 1, 0, -1, 28))
        f.write(struct.pack("<IIHHII", 1, 20, link_type, 0, 65535, 20))
        for ts, frame, comment in packets:
            micros = int(ts * 1e6)
            body = struct.pack("<IIIII", 0, micros >> 32, micros & 0xFFFFFFFF, len(frame), len(frame))
            body += frame + b"\x00" * (-len(frame) % 4)
            text = comment.encode()
            body += struct.pack("<HH", 1, len(text)) + text + b"\x00" * (-len(text) % 4)
            body += struct.pack("<HH", 0, 0)
            f.write(struct.pack("<II", 6, 12 + len(body)) + body + struct.pack("<I", 12 + len(body)))
    return path


def write_dataset(
    path: Path,
    *,
    signal: Literal["behaviour", "port"] = "behaviour",
    hosts_per_class: int = 6,
    samples_per_host: int = 5,
    packets_per_sample: int = 10,
    seed: int = 0,
) -> Path:
    """Write the synthetic dataset; each host's samples are labelled with its class.

    "behaviour" randomises IDs, sequence numbers and timestamps like real traffic. "port"
    holds them constant so the source port is the only class signal (the host address and
    IPv4 checksum still vary per host, but not per class).
    """
    rng = random.Random(seed)
    noisy = signal == "behaviour"

    def rand(bits: int) -> int:
        return rng.randrange(2**bits) if noisy else 0

    def records() -> Iterable[tuple[float, bytes, str]]:
        sid, clock = 0, 1.7e9
        for class_index, label in enumerate(CLASSES):
            for _ in range(hosts_per_class):
                src = f"10.{rng.randrange(256)}.{rng.randrange(256)}.{rng.randrange(1, 255)}"
                for _ in range(samples_per_host):
                    for k in range(packets_per_sample):
                        if noisy:
                            ttl, window, mss = _BEHAVIOUR[label]
                            sport = rng.randrange(1024, 65536)
                        else:
                            ttl, window, mss = 64, 29200, 1460
                            sport = 40000 + class_index
                        frame = ipv4_tcp_frame(
                            src=src,
                            dst=f"192.0.2.{rng.randrange(1, 255) if noisy else 1}",
                            sport=sport,
                            dport=443,
                            ttl=ttl,
                            window=window,
                            flags=TCP_SYN if k == 0 else TCP_ACK,
                            seq=rand(32),
                            ack=rand(32),
                            ip_id=rand(16),
                            mss=mss,
                            timestamp=(rand(32), rand(32)),
                        )
                        clock += rng.uniform(0.001, 0.05)
                        yield clock, frame, f"{sid},{label}"
                    sid += 1

    return write_pcapng(path, records())
