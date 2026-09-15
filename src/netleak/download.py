"""Fetch benchmark datasets into data/<dataset>/ and locate the pcapML file.

Downloads come from the Google Drive links on the nPrint benchmark pages. If gdown is
blocked (Drive quotas), download by hand and put the .pcapng (or its archive) in
data/<dataset>/; `find_source` will pick it up.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import lzma
import shutil
from pathlib import Path

from . import synthetic
from .datasets import DatasetSpec
from .paths import Paths

log = logging.getLogger(__name__)
_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2")


def dataset_dir(spec: DatasetSpec, paths: Paths) -> Path:
    return paths.data / spec.name


def find_source(spec: DatasetSpec, paths: Paths) -> Path:
    """The single .pcapng file for `spec`, extracting a downloaded archive if needed."""
    root = dataset_dir(spec, paths)
    candidates = sorted(root.rglob("*.pcapng"))
    if not candidates:
        for archive in root.glob("*"):
            _extract(archive)
        candidates = sorted(root.rglob("*.pcapng"))
    if not candidates:
        raise FileNotFoundError(
            f"no .pcapng under {root}. Run `netleak download -d {spec.name}`, or download it "
            f"manually from {spec.benchmark_url} into {root}/"
        )
    if len(candidates) > 1:
        raise RuntimeError(f"expected one .pcapng under {root}, found {[str(c) for c in candidates]}")
    return candidates[0]


def download(spec: DatasetSpec, paths: Paths, force: bool = False) -> Path:
    root = dataset_dir(spec, paths)
    root.mkdir(parents=True, exist_ok=True)
    if spec.gdrive_id is None:
        return synthetic.write_dataset(root / f"{spec.name}.pcapng")
    if not force:
        try:
            return find_source(spec, paths)
        except FileNotFoundError:
            pass

    import gdown

    fetched = gdown.download(id=spec.gdrive_id, output=f"{root}/", quiet=False)
    if fetched is None:
        raise RuntimeError(f"gdown could not fetch {spec.name}; download manually from {spec.benchmark_url}")
    source = find_source(spec, paths)
    manifest = {"file": source.name, "bytes": source.stat().st_size, "sha256": _sha256(source)}
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    log.info("downloaded %s -> %s", spec.name, source)
    return source


def _extract(archive: Path) -> None:
    name = archive.name.lower()
    if name.endswith(_ARCHIVE_SUFFIXES):
        log.info("extracting %s", archive)
        shutil.unpack_archive(archive, archive.parent)
    elif name.endswith((".pcapng.gz", ".pcapng.xz")):  # how the benchmark files ship
        log.info("decompressing %s", archive)
        opener = gzip.open if name.endswith(".gz") else lzma.open
        with opener(archive) as src, open(archive.with_suffix(""), "wb") as dst:
            shutil.copyfileobj(src, dst)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
