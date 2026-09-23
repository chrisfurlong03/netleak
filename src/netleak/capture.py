"""Record one fresh traffic session; raw captures are not labelled benchmark samples."""

from __future__ import annotations

import json
import re
import shutil
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _tool(name: str) -> str:
    installed = shutil.which(name)
    bundled = Path("/Applications/Wireshark.app/Contents/MacOS") / name
    if installed:
        return installed
    if bundled.is_file():
        return str(bundled)
    raise FileNotFoundError(f"{name} is missing; install Wireshark before recording.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(path: Path, record: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(path)


def summarize(path: Path) -> dict:
    """Count protocol coverage over the entire capture, including background traffic."""
    command = [_tool("tshark"), "-n", "-r", str(path), "-T", "fields"]
    fields = ("frame.time_epoch", "frame.len", "frame.cap_len", "frame.protocols", "tcp.flags.syn")
    for field in fields:
        command.extend(["-e", field])
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    counts = dict.fromkeys(
        ("packets", "wire_bytes", "truncated_packets", "ipv4", "ipv6", "tcp", "udp", "quic", "ipv4_syn"),
        0,
    )
    times = []
    for line in completed.stdout.splitlines():
        timestamp, length, captured, protocols, syn = line.split("\t")
        protocol_set = set(protocols.split(":"))
        counts["packets"] += 1
        counts["wire_bytes"] += int(length)
        counts["truncated_packets"] += int(int(captured) < int(length))
        for name, protocol in (
            ("ipv4", "ip"),
            ("ipv6", "ipv6"),
            ("tcp", "tcp"),
            ("udp", "udp"),
            ("quic", "quic"),
        ):
            counts[name] += int(protocol in protocol_set)
        syn_is_set = any(value.lower() in ("1", "true") for value in syn.split(","))
        counts["ipv4_syn"] += int("ip" in protocol_set and syn_is_set)
        times.append(float(timestamp))
    counts["observed_span_seconds"] = round(max(times) - min(times), 3) if times else 0.0
    counts["file_bytes"] = path.stat().st_size
    return counts


def record_session(
    output: Path,
    *,
    label: str,
    interface: str,
    seconds: int = 120,
    content_url: str = "",
    notes: str = "",
    condition: str = "natural",
) -> Path:
    """Record for a bounded duration. Browser playback is controlled separately."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", label):
        raise ValueError("Label must use lowercase letters, digits and underscores.")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", condition):
        raise ValueError("Condition must use lowercase letters, digits and underscores.")
    if not 1 <= seconds <= 600:
        raise ValueError("Session length must be between 1 and 600 seconds.")
    dumpcap = _tool("dumpcap")
    _tool("tshark")
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    directory = output / condition / label / session_id
    directory.mkdir(parents=True, mode=0o700)
    capture_path = directory / "traffic.pcapng"
    manifest_path = directory / "session.json"
    record = {
        "session_id": session_id,
        "intended_service": label,
        "condition": condition,
        "content_url": content_url,
        "interface": interface,
        "requested_seconds": seconds,
        "max_file_kb": 250000,
        "started_at_utc": _now(),
        "status": "recording",
        "playback_verified": False,
        "benchmark_ready": False,
        "scope": "All traffic on the interface; service attribution is not established.",
        "notes": notes,
    }
    _save(manifest_path, record)
    command = [
        dumpcap,
        "-i",
        interface,
        "-p",
        "-q",
        "-a",
        f"duration:{seconds}",
        "-a",
        "filesize:250000",
        "-w",
        str(capture_path),
    ]
    print(f"Session: {directory}", flush=True)
    print("Wait for dumpcap's 'File:' message, then open and play the video.", flush=True)
    # Keep stderr visible: dumpcap confirms readiness and reports permission errors here.
    try:
        with subprocess.Popen(command, start_new_session=True) as process:
            try:
                code = process.wait()
            except KeyboardInterrupt:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                record["status"] = "interrupted"
                raise
        if code:
            raise RuntimeError(f"Capture failed (exit {code}); see dumpcap's message above.")
        record["summary"] = summarize(capture_path)
        record["status"] = "captured" if record["summary"]["packets"] else "empty"
    except Exception as error:
        record["status"] = "failed"
        record["error"] = str(error)
        raise
    finally:
        record["ended_at_utc"] = _now()
        _save(manifest_path, record)
    print(json.dumps(record["summary"], indent=2), flush=True)
    print(f"Saved {manifest_path}; playback and service attribution still need verification.", flush=True)
    return directory
