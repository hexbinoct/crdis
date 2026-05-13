"""Ground-truth decoder tests.

These translate each sample's `notes.md` prose into executable assertions
against the parsed record stream. Failing means a field decoder regressed
or a sample's ground truth has drifted from the file.

Field decoder reference (all confirmed in Round 10, see CLAUDE.md):
  - 0xC2 (Text Object string):
      `<u4 BE byte-length> <utf8 bytes including NUL> <4 zero pad>`
  - 0xBE (position):
      `<u2 BE left> <u2 BE top>`  (twips)
  - 0xAA (Line outer) -> nested 0xA9 -> nested 0x9E (Line name/width):
      0x9E.value[0:4] u4 BE  = width (twips)
      0x9E.value[19]         = name length (counts NUL)
      0x9E.value[20:20+nlen] = name + NUL pad
      0xA9.tail[2:4] u2 BE   = right (twips)
      0xA9.tail[4:6] u2 BE   = bottom (twips)
  - 0xED (Line style/thickness) -> nested 0xEC:
      0xEC.value[2]          = LineStyle enum (1=single, 4=dotted)
      0xEC.value[18:22] u4 BE = thickness
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest

from crdis.codec.cs_archive import CSArchiveParser, Record
from crdis.codec.cslibu_aes import decrypt_contents_stream
from crdis.container import read_stream

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "samples"


def _parse(sample_dir: str, *, recurse: bool = False) -> list[Record]:
    body = read_stream(SAMPLES / sample_dir / "report.rpt", "Contents")
    plain = decrypt_contents_stream(body)
    return CSArchiveParser(plain).parse_all(recurse=recurse)


def _extract_c2_string(rec: Record) -> str:
    nbytes = int.from_bytes(rec.value[0:4], "big")
    return rec.value[4:4 + nbytes].rstrip(b"\x00").decode("utf-8")


# -------- 001: empty report has no element-class records --------


def test_001_has_no_element_records():
    """Empty report should contain no Text Object (0xA5), Line (0xAA), or Image (0xAF) blocks."""
    recs = _parse("001_empty")
    tags = {r.tag for r in recs}
    assert 0xA5 not in tags, "empty report should not have a Text Object (0xA5)"
    assert 0xAA not in tags, "empty report should not have a Line (0xAA)"
    assert 0xAF not in tags, "empty report should not have an Image (0xAF)"


# -------- 002/003/004: 0xC2 string extraction --------


@pytest.mark.parametrize(
    "sample, expected",
    [
        ("002_one_label", ["HELLO"]),
        ("003_two_labels_hello_world", ["HELLO", "WORLD"]),
        ("004_two_labels_greetings_someone", ["GREETINGS", "SOMEONE"]),
    ],
)
def test_text_object_strings(sample: str, expected: list[str]):
    """Each 0xC2 record holds a length-prefixed UTF-8 string + NUL + 4-byte pad."""
    recs = _parse(sample)
    strings = [_extract_c2_string(r) for r in recs if r.tag == 0xC2]
    assert strings == expected


# -------- 002/003/004: Text Object geometry (width + height + name + left + top) --------

# Text Object block: [0xA5, 0xBE, 0xFD, 0xED, 0xC0, 0xC2, 0x101, 0x08, 0x102, 0xC3, 0xC1, 0xA6]
# Schema (decoded 2026-05-13):
#   0xA5 -> 0x9E.value[0:4]   u4 BE = width  (twips)
#           0x9E.value[4:8]   u4 BE = height (twips)
#           0x9E.value[19]    u1    = name length (counts NUL; same as Line)
#           0x9E.value[20:..] UTF-8 + NUL
#   0xBE.value[0:2] u2 BE = left  (twips)
#   0xBE.value[2:4] u2 BE = top   (twips)
#   0xC2.value     length-prefixed UTF-8 + NUL + 4-byte zero pad

TEXT_BLOCK_TAGS = [0xA5, 0xBE, 0xFD, 0xED, 0xC0, 0xC2, 0x101, 0x08, 0x102, 0xC3, 0xC1, 0xA6]


class TextExpect(NamedTuple):
    name: str
    width: int
    height: int
    left: int
    top: int
    text: str


SAMPLE_TEXT_OBJECTS: dict[str, list[TextExpect]] = {
    "002_one_label": [
        TextExpect("Text1", 1869, 221, 100, 100, "HELLO"),
    ],
    "003_two_labels_hello_world": [
        TextExpect("Text1", 1869, 221, 100, 100, "HELLO"),
        TextExpect("Text2", 1869, 221, 2055, 100, "WORLD"),
    ],
    "004_two_labels_greetings_someone": [
        TextExpect("Text1", 1869, 221, 100, 100, "GREETINGS"),
        TextExpect("Text2", 1869, 221, 2055, 100, "SOMEONE"),
    ],
}


def _decode_text_objects(records: list[Record]) -> list[TextExpect]:
    out = []
    L = len(TEXT_BLOCK_TAGS)
    for i in range(len(records) - L + 1):
        if [records[i + k].tag for k in range(L)] != TEXT_BLOCK_TAGS:
            continue
        a5, be, _, _, _, c2, *_ = records[i:i + L]
        nine_e = a5.children[0]
        v = nine_e.value
        width = int.from_bytes(v[0:4], "big")
        height = int.from_bytes(v[4:8], "big")
        nlen = v[19]
        name = v[20:20 + nlen].rstrip(b"\x00").decode("utf-8")
        left = int.from_bytes(be.value[0:2], "big")
        top = int.from_bytes(be.value[2:4], "big")
        text = _extract_c2_string(c2)
        out.append(TextExpect(name, width, height, left, top, text))
    return out


@pytest.mark.parametrize("sample", list(SAMPLE_TEXT_OBJECTS))
def test_text_object_block_fields(sample: str):
    recs = _parse(sample, recurse=True)
    decoded = _decode_text_objects(recs)
    assert decoded == SAMPLE_TEXT_OBJECTS[sample]


# -------- 005/006/007: Image geometry (width + height + name + left + top) --------

# Image block: [0xAF, 0xBE, 0xFD, 0xED, 0x09, 0xBD, 0xB0]
# 0xAF wraps 0xAE wraps 0x9E (three-level nesting, same depth as Lines).
# 0x9E uses the universal schema: [0:4]=width, [4:8]=height,
# [16:20]=name_length (u4 BE), [20:..]=name+NUL.
#
# Note: the file decodes the image name as "Picture1" (Designer's auto-name).
# Sample notes.md files say "Pic1" — that's a notes-side abbreviation;
# the file is authoritative. Tests assert "Picture1".

IMAGE_BLOCK_TAGS = [0xAF, 0xBE, 0xFD, 0xED, 0x09, 0xBD, 0xB0]


class ImageExpect(NamedTuple):
    name: str
    width: int
    height: int
    left: int
    top: int


SAMPLE_IMAGES: dict[str, list[ImageExpect]] = {
    "005_image_in_page_header": [
        ImageExpect("Picture1", 2445, 2371, 2128, 76),
    ],
    "006_image_in_details": [
        ImageExpect("Picture1", 2445, 2371, 4028, 76),
    ],
    "007_image_and_line": [
        ImageExpect("Picture1", 2445, 2371, 4028, 76),
    ],
}


def _decode_images(records: list[Record]) -> list[ImageExpect]:
    out = []
    L = len(IMAGE_BLOCK_TAGS)
    for i in range(len(records) - L + 1):
        if [records[i + k].tag for k in range(L)] != IMAGE_BLOCK_TAGS:
            continue
        af, be, *_ = records[i:i + L]
        # 0xAF -> 0xAE -> 0x9E (parser recurses one level by default;
        # re-parse 0xAE.value to get the 0x9E child).
        ae = af.children[0]
        nine_e_list = CSArchiveParser(ae.value).parse_all(recurse=False)
        v = nine_e_list[0].value
        width = int.from_bytes(v[0:4], "big")
        height = int.from_bytes(v[4:8], "big")
        nlen = v[19]
        name = v[20:20 + nlen].rstrip(b"\x00").decode("utf-8")
        left = int.from_bytes(be.value[0:2], "big")
        top = int.from_bytes(be.value[2:4], "big")
        out.append(ImageExpect(name, width, height, left, top))
    return out


@pytest.mark.parametrize("sample", list(SAMPLE_IMAGES))
def test_image_block_fields(sample: str):
    recs = _parse(sample, recurse=True)
    decoded = _decode_images(recs)
    assert decoded == SAMPLE_IMAGES[sample]


# -------- 007/008: Line geometry / style / thickness --------


class LineExpect(NamedTuple):
    name: str
    width: int
    left: int
    top: int
    right: int
    bottom: int
    style: int       # 1=single, 4=dotted
    thickness: int


# Sample 007: notes.md states right=5325; an earlier session reported a
# decode of 5565 from the same file. With the current parser the file
# decodes to 5325, matching notes. Test encodes file truth.
SAMPLE_LINES: dict[str, list[LineExpect]] = {
    "007_image_and_line": [
        LineExpect(name="Line2", width=4200, left=1125, top=675,
                   right=5325, bottom=675, style=1, thickness=20),
    ],
    "008_two_lines_only": [
        LineExpect(name="Line1", width=4500, left=1050, top=240,
                   right=5550, bottom=240, style=1, thickness=20),
        LineExpect(name="Line2", width=3990, left=1710, top=870,
                   right=5700, bottom=870, style=4, thickness=0),
    ],
    # Sample 009: five single-style lines, varying only by thickness.
    # 1.0 / 1.5 / 2.0 / 2.5 / 3.0 pt -> 20 / 30 / 40 / 50 / 60 twips.
    # Decoded values lock the thickness encoding (u4 BE, twips, 1pt=20).
    "009_five_lines_thickness": [
        LineExpect(name="Line1", width=5610, left=1920, top=690,
                   right=7530, bottom=690, style=1, thickness=20),
        LineExpect(name="Line2", width=4590, left=1950, top=1800,
                   right=6540, bottom=1800, style=1, thickness=30),
        LineExpect(name="Line4", width=4665, left=2400, top=2790,
                   right=7065, bottom=2790, style=1, thickness=40),
        LineExpect(name="Line6", width=4125, left=2025, top=3555,
                   right=6150, bottom=3555, style=1, thickness=50),
        LineExpect(name="Line8", width=4020, left=3585, top=4245,
                   right=7605, bottom=4245, style=1, thickness=60),
    ],
}


def _decode_lines(records: list[Record]) -> list[LineExpect]:
    """Walk the record stream, decode every Line block found."""
    out = []
    for i, r in enumerate(records):
        if r.tag != 0xAA:
            continue
        # Block layout (top-level): [AA, BE, FD, ED, AB]
        be = records[i + 1]
        ed = records[i + 3]
        assert be.tag == 0xBE
        assert ed.tag == 0xED

        a9 = r.children[0]
        nine_e = a9.children[0]
        v = nine_e.value
        nlen = v[19]
        name = v[20:20 + nlen].rstrip(b"\x00").decode("utf-8")
        width = int.from_bytes(v[0:4], "big")

        left = int.from_bytes(be.value[0:2], "big")
        top = int.from_bytes(be.value[2:4], "big")

        tail = a9.tail
        right = int.from_bytes(tail[2:4], "big")
        bottom = int.from_bytes(tail[4:6], "big")

        ec = ed.children[0]
        style = ec.value[2]
        thickness = int.from_bytes(ec.value[18:22], "big")

        out.append(LineExpect(name, width, left, top, right, bottom, style, thickness))
    return out


@pytest.mark.parametrize("sample", list(SAMPLE_LINES))
def test_line_block_fields(sample: str):
    recs = _parse(sample, recurse=True)
    decoded = _decode_lines(recs)
    assert decoded == SAMPLE_LINES[sample]
