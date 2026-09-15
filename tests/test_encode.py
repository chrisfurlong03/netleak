"""The encoder must agree bit-for-bit with an independent parser (scapy)."""

import ipaddress

import numpy as np
import pytest

from netleak import encode, synthetic

scapy_all = pytest.importorskip("scapy.all")
ARP, Ether, IP, TCP, UDP = (scapy_all.ARP, scapy_all.Ether, scapy_all.IP, scapy_all.TCP,
                            scapy_all.UDP)  # fmt: skip

TCP_OPTIONS = [
    ("MSS", 1460),
    ("SAckOK", b""),
    ("Timestamp", (123, 456)),
    ("NOP", None),
    ("WScale", 7),
]


def encoded(frame: bytes, link_type: int = 1) -> tuple[np.ndarray, int]:
    bits = np.full(encode.PACKET_BITS, encode.FILL, dtype=np.int8)
    offset = encode.encode_packet(encode.ipv4_bytes(frame, link_type), bits)
    return bits, offset


def value(bits: np.ndarray, field: str) -> int:
    start, stop = encode.field_bounds(field)
    chunk = bits[start:stop]
    assert set(np.unique(chunk)) <= {0, 1}, f"{field} has fill bits"
    return int("".join(str(int(b)) for b in chunk), 2)


@pytest.fixture
def syn_ack() -> bytes:
    return bytes(
        Ether()
        / IP(src="10.1.2.3", dst="192.0.2.9", ttl=64, id=0x1234, flags="DF", tos=0x10)
        / TCP(
            sport=443,
            dport=51515,
            seq=1000,
            ack=2000,
            flags="SA",
            window=29200,
            options=TCP_OPTIONS,
        )
    )


def test_column_layout():
    assert encode.IPV4_BITS == encode.TCP_BITS == 480
    assert len(set(encode.PACKET_COLUMNS)) == encode.PACKET_BITS == 960
    assert encode.PACKET_COLUMNS[0] == "ipv4_ver_0"
    assert encode.PACKET_COLUMNS[480] == "tcp_sprt_0"
    assert encode.column_name(960 + 480) == "pkt1_tcp_sprt_0"
    assert encode.field_of("pkt12_tcp_wsize_3") == "tcp_wsize"
    assert encode.field_of("ttl_mean") == "ttl_mean"


def test_header_fields_match_scapy(syn_ack):
    bits, _ = encoded(syn_ack)
    ip, tcp = Ether(syn_ack)[IP], Ether(syn_ack)[TCP]
    expected = {
        "ipv4_ver": ip.version, "ipv4_hl": ip.ihl, "ipv4_tos": ip.tos, "ipv4_tl": ip.len,
        "ipv4_id": ip.id, "ipv4_dfbit": 1, "ipv4_mfbit": 0, "ipv4_foff": ip.frag,
        "ipv4_ttl": ip.ttl, "ipv4_proto": ip.proto, "ipv4_cksum": ip.chksum,
        "ipv4_src": int(ipaddress.ip_address(ip.src)), "ipv4_dst": int(ipaddress.ip_address(ip.dst)),
        "tcp_sprt": tcp.sport, "tcp_dprt": tcp.dport, "tcp_seq": tcp.seq, "tcp_ackn": tcp.ack,
        "tcp_doff": tcp.dataofs, "tcp_syn": 1, "tcp_ackf": 1, "tcp_fin": 0, "tcp_rst": 0,
        "tcp_wsize": tcp.window, "tcp_cksum": tcp.chksum, "tcp_urp": tcp.urgptr,
    }  # fmt: skip
    for field, want in expected.items():
        assert value(bits, field) == want, field


def test_unused_option_space_is_fill(syn_ack):
    bits, _ = encoded(syn_ack)
    ipv4_opt, tcp_opt = encode.field_bounds("ipv4_opt"), encode.field_bounds("tcp_opt")
    assert (bits[ipv4_opt[0] : ipv4_opt[1]] == -1).all()
    options_bits = 20 * 8  # the options above pad to 20 bytes
    assert set(np.unique(bits[tcp_opt[0] : tcp_opt[0] + options_bits])) <= {0, 1}
    assert (bits[tcp_opt[0] + options_bits : tcp_opt[1]] == -1).all()


def test_timestamp_offset_points_at_tsval(syn_ack):
    bits, offset = encoded(syn_ack)
    assert offset == 64  # MSS (4 bytes) + SAckOK (2) + kind/len (2)
    start = encode.TCP_OPT_START + offset
    tsval = int("".join(str(b) for b in bits[start : start + 32]), 2)
    tsecr = int("".join(str(b) for b in bits[start + 32 : start + 64]), 2)
    assert (tsval, tsecr) == (123, 456)


def test_udp_has_no_tcp_bits():
    bits, offset = encoded(bytes(Ether() / IP() / UDP(sport=53, dport=53)))
    assert value(bits, "ipv4_proto") == 17
    assert (bits[encode.IPV4_BITS :] == -1).all()
    assert offset == -1


def test_non_ip_frame_is_all_fill():
    bits, _ = encoded(bytes(Ether() / ARP()))
    assert (bits == -1).all()


def test_raw_ip_linktype_matches_ethernet():
    packet = IP(src="10.0.0.1", dst="10.0.0.2") / TCP(sport=1, dport=2)
    eth_bits, _ = encoded(bytes(Ether() / packet))
    raw_bits, _ = encoded(bytes(packet), link_type=101)
    np.testing.assert_array_equal(eth_bits, raw_bits)


def test_encode_sample_pads_and_truncates():
    ip = encode.ipv4_bytes(bytes(IP() / TCP()), 101)
    row, ts = encode.encode_sample([ip, ip, ip], max_packets=5)
    assert row.shape == (5 * encode.PACKET_BITS,) and ts.shape == (5,)
    assert (row[3 * encode.PACKET_BITS :] == -1).all()
    assert (row[: encode.PACKET_BITS] != -1).any()
    row, _ = encode.encode_sample([ip] * 9, max_packets=2)
    assert row.shape == (2 * encode.PACKET_BITS,)


def test_synthetic_frames_parse_in_scapy():
    frame = synthetic.ipv4_tcp_frame(src="10.0.0.1", dst="192.0.2.1", sport=40000, dport=443,
                                     ttl=128, window=8192, mss=1380, timestamp=(7, 8), ip_id=99)  # fmt: skip
    packet = Ether(frame)
    assert (packet[IP].ttl, packet[IP].id, packet[TCP].window) == (128, 99, 8192)
    assert dict(packet[TCP].options)["MSS"] == 1380
    recomputed = IP(bytes(packet[IP]))
    del recomputed.chksum
    assert IP(bytes(recomputed)).chksum == packet[IP].chksum


def test_hand_features():
    ips = [encode.ipv4_bytes(synthetic.ipv4_tcp_frame(src="10.0.0.1", dst="10.0.0.2", sport=1,
                                                      dport=2, ttl=64, window=w, mss=1460), 1)
           for w in (1000, 3000)]  # fmt: skip
    values = dict(zip(encode.HAND_COLUMNS, encode.hand_features(ips, [0.0, 0.5]), strict=True))
    assert values["ttl_mean"] == 64 and values["ttl_std"] == 0
    assert values["tcp_window_mean"] == 2000 and values["tcp_window_std"] == 1000
    assert values["tcp_options_len_mean"] == 4
    assert values["iat_median"] == pytest.approx(0.5) and values["iat_iqr"] == 0
