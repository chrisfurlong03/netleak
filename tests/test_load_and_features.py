import numpy as np
import pytest

from netleak import features, synthetic
from netleak.datasets import SYNTHETIC
from netleak.encode import HAND_COLUMNS, PACKET_BITS
from netleak.load import inspect_dataset, iter_samples


def test_iter_samples_reads_labels_and_hosts(behaviour_pcapng):
    records = list(iter_samples(SYNTHETIC, behaviour_pcapng))
    assert len(records) == 3 * 6 * 5
    assert {r.label for r in records} == set(synthetic.CLASSES)
    assert len({r.group for r in records}) == 3 * 6
    assert all(len(r.ips) == r.n_packets == 10 for r in records)
    # every host belongs to exactly one class
    host_labels = {}
    for r in records:
        host_labels.setdefault(r.group, set()).add(r.label)
    assert all(len(labels) == 1 for labels in host_labels.values())


def test_limit_and_truncation(behaviour_pcapng):
    records = list(iter_samples(SYNTHETIC, behaviour_pcapng, max_packets=4, limit=7))
    assert len(records) == 7 and all(len(r.ips) == 4 and r.n_packets == 10 for r in records)


def test_non_contiguous_samples_are_rejected(tmp_path):
    frame = synthetic.ipv4_tcp_frame(src="10.0.0.1", dst="10.0.0.2", sport=1, dport=2)
    interleaved = [(1.0, frame, "0,a"), (2.0, frame, "1,b"), (3.0, frame, "0,a")]
    path = synthetic.write_pcapng(tmp_path / "bad.pcapng", interleaved)
    with pytest.raises(ValueError, match="not contiguous"):
        list(iter_samples(SYNTHETIC, path))


def test_inspect(behaviour_pcapng):
    summary = inspect_dataset(SYNTHETIC, behaviour_pcapng)
    assert (summary["samples"], summary["classes"], summary["hosts"]) == (90, 3, 18)
    assert summary["hosts_in_multiple_classes"] == 0


def test_feature_cache_shapes_and_reuse(behaviour_pcapng, behaviour_paths):
    fs = features.load(SYNTHETIC, behaviour_paths.cache)
    assert fs.nprint.shape == (90, 10 * PACKET_BITS)
    assert fs.ts_offsets.shape == (90, 10)
    assert list(fs.hand.columns) == list(HAND_COLUMNS)
    assert len(fs.meta) == 90 and set(fs.meta.columns) == {"sid", "label", "group", "n_packets"}

    before = (fs.root / "nprint.i8").stat().st_mtime_ns
    features.build(SYNTHETIC, behaviour_pcapng, behaviour_paths.cache)
    assert (fs.root / "nprint.i8").stat().st_mtime_ns == before


def test_matrix_drops_constant_columns(behaviour_paths):
    fs = features.load(SYNTHETIC, behaviour_paths.cache)
    X, names = fs.matrix("R0", np.arange(10))
    full, _ = fs.matrix("R0", np.arange(10), drop_constant=False)
    assert X.dtype == np.int8 and X.shape == (10, len(names))
    assert X.shape[1] < full.shape[1]
    hand, hand_names = fs.matrix("R3", np.arange(10))
    assert hand.shape == (10, len(HAND_COLUMNS)) and hand_names == list(HAND_COLUMNS)
