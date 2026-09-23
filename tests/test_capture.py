import json
import shutil
from pathlib import Path

import pytest

from netleak import capture, synthetic


def test_failed_capture_is_recorded_without_claiming_a_labelled_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_tool", lambda name: "/usr/bin/false")
    with pytest.raises(RuntimeError, match="Capture failed"):
        capture.record_session(tmp_path, label="youtube", interface="test0", seconds=1)
    record = json.loads(next(tmp_path.rglob("session.json")).read_text())
    assert record["status"] == "failed"
    assert record["ended_at_utc"]
    assert record["benchmark_ready"] is False
    assert record["playback_verified"] is False


def test_capture_rejects_paths_in_labels_before_creating_files(tmp_path):
    with pytest.raises(ValueError, match="Label"):
        capture.record_session(tmp_path, label="../outside", interface="test0")
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(
    not shutil.which("tshark") and not Path("/Applications/Wireshark.app/Contents/MacOS/tshark").exists(),
    reason="Wireshark is an optional capture tool",
)
def test_summary_distinguishes_handshakes_from_other_packets(tmp_path):
    packets = []
    for index, flags in enumerate((2, 18, 16)):
        frame = synthetic.ipv4_tcp_frame(
            src="192.0.2.1", dst="198.51.100.1", sport=40000, dport=443, flags=flags
        )
        packets.append((1700000000 + index, frame, "pilot,youtube"))
    path = synthetic.write_pcapng(tmp_path / "synthetic.pcapng", packets)
    summary = capture.summarize(path)
    assert summary["packets"] == summary["ipv4"] == summary["tcp"] == 3
    assert summary["ipv4_syn"] == 2
    assert summary["udp"] == summary["ipv6"] == summary["truncated_packets"] == 0
    assert summary["observed_span_seconds"] == 2
