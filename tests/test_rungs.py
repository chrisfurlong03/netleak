"""Leakage invariants. If one of these fails, every downstream number is suspect."""

import numpy as np

from netleak import encode, features
from netleak.datasets import SYNTHETIC
from netleak.rungs import (
    DISALLOWED_FIELDS,
    IDENTIFIER_FIELDS,
    RUNG_ORDER,
    RUNGS,
    column_mask,
    packet_mask,
    rung_version,
)

FIELD_NAMES = {name for name, _ in encode.FIELDS}


def kept_fields(rung: str) -> set[str]:
    return {f for f, keep in zip(encode.PACKET_COLUMN_FIELDS, packet_mask(rung), strict=True) if keep}


def test_restricted_fields_exist_in_the_encoder():
    # A typo here would silently leave a disallowed field in R1.
    assert DISALLOWED_FIELDS <= FIELD_NAMES
    assert IDENTIFIER_FIELDS <= FIELD_NAMES


def test_ladder_order():
    assert RUNG_ORDER == ("R0", "R1", "R2", "R3")
    assert RUNGS["R3"].source == "hand"


def test_r0_keeps_everything():
    assert packet_mask("R0").all()


def test_benchmark_rungs_exclude_disallowed_fields():
    for rung in ("R1", "R2"):
        assert not kept_fields(rung) & DISALLOWED_FIELDS, rung


def test_r2_excludes_identifier_fields():
    assert not kept_fields("R2") & IDENTIFIER_FIELDS
    assert RUNGS["R2"].mask_tcp_timestamps


def test_rungs_nest():
    r0, r1, r2 = (packet_mask(r) for r in ("R0", "R1", "R2"))
    assert (r1 <= r0).all() and (r2 <= r1).all()
    assert r2.sum() < r1.sum() < r0.sum()


def test_column_mask_tiles_packets():
    mask = column_mask("R1", 3)
    assert mask.shape == (3 * encode.PACKET_BITS,)
    np.testing.assert_array_equal(mask, np.tile(packet_mask("R1"), 3))


def test_rung_version_is_stable():
    assert rung_version() == rung_version() and len(rung_version()) == 12


def test_selected_matrices_have_no_restricted_columns(behaviour_paths):
    fs = features.load(SYNTHETIC, behaviour_paths.cache)
    for rung in ("R1", "R2"):
        _, names = fs.matrix(rung, drop_constant=False)
        leaked = {encode.field_of(n) for n in names} & DISALLOWED_FIELDS
        assert not leaked, (rung, leaked)
    _, names = fs.matrix("R2", drop_constant=False)
    assert not {encode.field_of(n) for n in names} & IDENTIFIER_FIELDS


def test_r2_zeroes_tcp_timestamp_values(behaviour_paths):
    fs = features.load(SYNTHETIC, behaviour_paths.cache)
    sample, packet = np.argwhere(fs.ts_offsets >= 0)[0]
    offset = int(fs.ts_offsets[sample, packet])
    ts_names = {f"pkt{packet}_tcp_opt_{bit}" for bit in range(offset, offset + encode.TS_VALUE_BITS)}

    x1, names1 = fs.matrix("R1", [sample], drop_constant=False)
    x2, names2 = fs.matrix("R2", [sample], drop_constant=False)
    r1_bits = x1[0, [i for i, n in enumerate(names1) if n in ts_names]]
    r2_bits = x2[0, [i for i, n in enumerate(names2) if n in ts_names]]
    assert len(r2_bits) == encode.TS_VALUE_BITS
    assert r1_bits.any() and not r2_bits.any()
