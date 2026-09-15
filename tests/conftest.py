from pathlib import Path

import pytest

from netleak import features, synthetic
from netleak.datasets import SYNTHETIC
from netleak.paths import Paths


@pytest.fixture(scope="session")
def behaviour_pcapng(tmp_path_factory) -> Path:
    return synthetic.write_dataset(tmp_path_factory.mktemp("data") / "behaviour.pcapng")


@pytest.fixture(scope="session")
def port_canary_paths(tmp_path_factory) -> Paths:
    """Workspace whose synthetic dataset carries its label only in the TCP source port."""
    paths = Paths(tmp_path_factory.mktemp("canary"))
    source = synthetic.write_dataset(paths.data / "synthetic" / "synthetic.pcapng", signal="port")
    features.build(SYNTHETIC, source, paths.cache)
    return paths


@pytest.fixture(scope="session")
def behaviour_paths(tmp_path_factory, behaviour_pcapng) -> Paths:
    paths = Paths(tmp_path_factory.mktemp("behaviour"))
    features.build(SYNTHETIC, behaviour_pcapng, paths.cache)
    return paths
