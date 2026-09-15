import json

import numpy as np
import pytest
from typer.testing import CliRunner

from netleak import runner, splits
from netleak.cli import app
from netleak.datasets import SYNTHETIC


def test_grouped_split_keeps_hosts_apart():
    labels = np.repeat(["a", "b", "c"], 30)
    groups = np.array([f"host{i // 5}" for i in range(90)])
    train, test = splits.make_split(labels, groups, "grouped", seed=3)
    assert not set(groups[train]) & set(groups[test])
    assert len(train) + len(test) == 90


def test_grouped_split_rejects_single_host_classes():
    labels = np.repeat(["a", "b", "c", "d", "e"], 10)  # OS detection: one host per class
    with pytest.raises(ValueError, match="test set"):
        splits.make_split(labels, labels, "grouped")


def test_block_split_holds_out_the_tail_of_each_class():
    labels = np.array(["a", "b"] * 50)  # interleaved in file order
    train, test = splits.make_split(labels, labels, "block", test_size=0.2)
    for label in ("a", "b"):
        members = np.flatnonzero(labels == label)
        np.testing.assert_array_equal(np.intersect1d(test, members), members[-10:])
    assert len(train) == 80


def test_random_split_is_stratified():
    labels = np.repeat(["a", "b"], 50)
    train, test = splits.make_split(labels, labels, "random", test_size=0.2)
    assert len(test) == 20 and (labels[test] == "a").sum() == 10


def test_subsample_is_stratified():
    labels = np.repeat(["a", "b"], [80, 20])
    kept = splits.subsample(labels, 50, seed=0)
    assert len(kept) == 50 and (labels[kept] == "b").sum() == 10


def test_port_canary(port_canary_paths):
    """Label lives only in the TCP source port: R0 must find it, R1 must not.

    Random forest: with a host-grouped split, standardised logistic regression latches onto
    the rare per-host address bits instead of the port and fails even at R0.
    """
    r0 = runner.fit_one(SYNTHETIC, "R0", "rf", "grouped", paths=port_canary_paths).result
    r1 = runner.fit_one(SYNTHETIC, "R1", "rf", "grouped", paths=port_canary_paths).result
    assert r0.balanced_accuracy >= 0.9
    assert r1.balanced_accuracy <= 0.6


def test_behaviour_survives_restriction(behaviour_paths):
    for rung in ("R1", "R2", "R3"):
        result = runner.fit_one(SYNTHETIC, rung, "rf", "grouped", paths=behaviour_paths).result
        assert result.balanced_accuracy >= 0.9, rung


def test_smoke_cli(tmp_path):
    outcome = CliRunner().invoke(app, ["smoke", "--root", str(tmp_path)])
    assert outcome.exit_code == 0, outcome.output
    result_files = sorted((tmp_path / "results" / "synthetic").glob("*.json"))
    assert len(result_files) == 4 * 3 * len(SYNTHETIC.splits)
    record = json.loads(result_files[0].read_text())
    assert {"balanced_accuracy", "rung_version", "confusion_matrix"} <= record.keys()
    assert (tmp_path / "results" / "figures" / "headline.png").exists()
    assert list((tmp_path / "results" / "synthetic" / "importance").glob("*.csv"))
