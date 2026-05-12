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
