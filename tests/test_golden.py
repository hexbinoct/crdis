"""Golden-fixture tests for all 8 paired samples.

For each `samples/00*/report.rpt`, assert four hashes/counts:
  - sha256 of the raw `Contents` stream bytes
  - sha256 of the inflated plaintext after `decrypt_contents_stream`
  - count of top-level records in the inner CSArchive
  - sha256 of the concatenation of every top-level `record.value`

Expected values are baked in below as constants, seeded from the current
known-good parser. A regression in either the cslibu AES port or the
CSArchive record parser will flip one or more of these.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from crdis.codec.cs_archive import CSArchiveParser
from crdis.codec.cslibu_aes import decrypt_contents_stream
from crdis.container import read_stream

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "samples"


# (sample_dir, raw_size, raw_sha256, plain_size, plain_sha256, record_count, concat_sha256)
GOLDEN = [
    ("001_empty",
     1406, "c8e0970711c114197de6e2f7a51d3e6d8ab9fd41bd01f93492b0c8d77230f22a",
     5163, "800d3bc9b6275dfe1ec009a6039a216b6262c6f1591ed5ada194af364d3a3d88",
     126,  "7fad249c4b0a9710cbcaa70c5ce62a59863e8cc9eefb7887aaef971dff18d879"),
    ("002_one_label",
     1633, "454459322d536bbc2f81870305cca7875ae3f17be584fddabc5bc4e416078fe0",
     5758, "6ceb83af9d3cdf07c6682ddddcbee4e6308c1dab2ab7555e8352e0d89411471c",
     138,  "7cf6af12af4daa9bcd85d2a234fd5a239cd829923142b884fd95497e0e1c3719"),
    ("003_two_labels_hello_world",
     1666, "ecc7564a168ed64df3e5cadf5467e95c346df8be5e5fe5866f3763f48126bd4a",
     6353, "114162bce6507c0b3058b469b44ef6038d2ed8d0ae335d93b1718351610bf8c9",
     150,  "174c0b72c30f60e15730a6d5fc510fcd9d2df2cd6c41581b6e65c20fee6ea771"),
    ("004_two_labels_greetings_someone",
     1677, "5539202c10446464e8bfe0b57cf7f1a4b1a17782a6b6a3f14050cc1aebf7acde",
     6359, "b1b99d53d1013ab9e71d347f67b0f7496355766cb0a05fc2d28dbb1a5e31de8e",
     150,  "7b0e42d5ce5f57d93d7cb33697956da28d8f00446b16ef0a7f18fbc3cd5a4ba1"),
    ("005_image_in_page_header",
     1793, "bb08b238c8bbd72a6847a427a1240d9258d88290fd42160bb0a44715acbfa0d8",
     6849, "70c851f48451f6ffc0263ef143036f8f655893ea33080454c0056c6b8832a09f",
     157,  "df8f0d3f38de2be2e8f8874b9f62c248bfb187e89e0c25ea95372e4624700cb4"),
    ("006_image_in_details",
     1790, "5e8252fed9093b97b7e5a6b58c50795b0d1d06ebdedab15ede21f89cf1897621",
     6849, "7d311c1ef26d50216db2bca8eab5b13451592e5c31b283777ce59f91c04322d2",
     157,  "da2a902b49a21f400a2dd15b1a983359041dca87b3719b3d1dc1958faae5e3c6"),
    ("007_image_and_line",
     1884, "74010b40a439d7b4af0d2f285d79e0b50b2df4e75e2ea5da11a86707ce54673d",
     7278, "fa9b6a9707360472c7bc1772106e009754dd80319261aa5d29ebdfe637f5a08e",
     162,  "4065ab900d6128d263e9893347c576a709ba490a9b279483d3140bdd71169ba0"),
    ("008_two_lines_only",
     1604, "f7f61c5c5e0c499fff2b3f388bb1dc169d8457efb006e62d303b80502602771d",
     6021, "d6ea536570c1ff0269dbccd3821addf2b9e44f4aff02d3bea9238515c075f0c4",
     136,  "50b36802456ba69b3ed75bd99d7361979b7ebc07e988e63079de37973e07b236"),
]


@pytest.fixture(scope="module")
def parsed():
    """One full parse per sample, shared across the four golden assertions."""
    cache = {}
    for entry in GOLDEN:
        name = entry[0]
        body = read_stream(SAMPLES / name / "report.rpt", "Contents")
        plain = decrypt_contents_stream(body)
        records = CSArchiveParser(plain).parse_all()
        cache[name] = (body, plain, records)
    return cache


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e[0])
def test_raw_contents_stream(entry, parsed):
    name, raw_size, raw_sha, *_ = entry
    body, _, _ = parsed[name]
    assert len(body) == raw_size
    assert hashlib.sha256(body).hexdigest() == raw_sha


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e[0])
def test_inflated_plaintext(entry, parsed):
    name = entry[0]
    plain_size, plain_sha = entry[3], entry[4]
    _, plain, _ = parsed[name]
    assert len(plain) == plain_size
    assert hashlib.sha256(plain).hexdigest() == plain_sha


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e[0])
def test_top_level_record_count(entry, parsed):
    name = entry[0]
    expected = entry[5]
    _, _, records = parsed[name]
    assert len(records) == expected


@pytest.mark.parametrize("entry", GOLDEN, ids=lambda e: e[0])
def test_record_value_concat_sha(entry, parsed):
    name = entry[0]
    expected = entry[6]
    _, _, records = parsed[name]
    concat = b"".join(r.value for r in records)
    assert hashlib.sha256(concat).hexdigest() == expected
