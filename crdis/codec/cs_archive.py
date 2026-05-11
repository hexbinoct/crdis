"""Parser for CSLib300 ``CSRecordArchive`` TLV record streams.

Each record on disk is:
  byte 0..1 : flag word (low byte = flags + 2 high bits of tag)
              bit 7 : wide-length flag       (combined with bit 6)
              bit 6 : has-length-byte flag   (combined with bit 7)
              bit 5 : section-changed-from-default (read 2 more bytes)
              bit 4 : "another" flag (sets archive+0x50=1; meaning unconfirmed)
              bit 3 : useSimpleEncryption     (XOR running mask by byte(tag))
              bit 2 : extended-tag (read 2 more bytes for tag, big-endian)
              bits 1,0 : if not extended, high 2 bits of 10-bit tag
              high byte = low 8 bits of tag (when not extended)
  [byte 2..3]: extended tag (only if bit 2 set), big-endian-on-disk
  [byte X..]: section (only if bit 5 set), 2 bytes big-endian-on-disk
  [byte X..]: length, 0 / 1 / 2 / 4 bytes big-endian-on-disk
  [byte X..]: value bytes, length given above

Length-width encoding from (bit 7, bit 6):
  (0,0) -> 0   (0,1) -> 1   (1,0) -> 2   (1,1) -> 4

Running XOR mask: every byte read/written via storeBlock/loadBlock is XOR'd
by archive->mask (a single byte). startRecord flips it by XOR'ing with
``byte(tag)`` *iff* useSimpleEncryption was active for that record;
endRecord undoes the same XOR.

This parser tracks the mask while walking and returns *unmasked* value
bytes. It also optionally recurses into nested records when a value's
bytes look like another record header.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Record:
    tag: int
    section: int
    flags: int
    has_simple_enc: bool
    length: int
    value: bytes  # unmasked value bytes (this record's mask state applied)
    children: list["Record"] = field(default_factory=list)
    tail: bytes = b""  # value bytes after the (single) nested child, if any
    raw_value_offset: int = 0  # for cross-reference back to the source stream


class CSArchiveParser:
    BIT_WIDE_LEN = 0x80
    BIT_HAS_LEN = 0x40
    BIT_SECTION = 0x20
    BIT_FLAG_50 = 0x10
    BIT_SIMPLE_ENC = 0x08
    BIT_EXT_TAG = 0x04

    def __init__(self, data: bytes, *, initial_mask: int = 0, default_section: int = 0):
        self.data = data
        self.pos = 0
        self.mask = initial_mask
        self.default_section = default_section

    # mask-aware reads
    def _read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise EOFError(f"need {n} at pos {self.pos}; have {len(self.data) - self.pos}")
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return bytes(b ^ self.mask for b in raw)

    def _read_uint_be(self, n: int) -> int:
        return int.from_bytes(self._read(n), "big")

    def parse_record(self, *, recurse: bool = False) -> Record:
        flag_word = self._read(2)
        flags = flag_word[0]
        tag_low8 = flag_word[1]

        bit_wide = bool(flags & self.BIT_WIDE_LEN)
        bit_has = bool(flags & self.BIT_HAS_LEN)
        bit_section = bool(flags & self.BIT_SECTION)
        bit_simple = bool(flags & self.BIT_SIMPLE_ENC)
        bit_ext = bool(flags & self.BIT_EXT_TAG)

        if bit_wide:
            length_width = 4 if bit_has else 2
        else:
            length_width = 1 if bit_has else 0

        if bit_ext:
            tag = self._read_uint_be(2)
        else:
            # cleared low byte (bits 7..2) shifts to high; original byte 1 stays low
            tag = ((flags & 0x03) << 8) | tag_low8

        section = self._read_uint_be(2) if bit_section else self.default_section
        length = self._read_uint_be(length_width) if length_width else 0

        # Mask transition for value bytes
        if bit_simple:
            self.mask ^= (tag & 0xFF)

        raw_value = self.data[self.pos:self.pos + length]
        value = bytes(b ^ self.mask for b in raw_value)
        raw_value_offset = self.pos
        self.pos += length

        rec = Record(
            tag=tag, section=section, flags=flags, has_simple_enc=bit_simple,
            length=length, value=value, raw_value_offset=raw_value_offset,
        )

        if recurse and length > 0 and looks_like_nested(value):
            # Empirical model: a wrapper record contains exactly ONE nested
            # record at the start of its value, followed by raw tail bytes
            # (typically a 4-byte-aligned data region). Parse one nested
            # record and capture the remainder as `tail`. If the single
            # parse fails or produces an obviously degenerate result, treat
            # the whole value as raw (no children, no tail).
            sub = CSArchiveParser(value, initial_mask=0, default_section=section)
            try:
                child = sub.parse_record(recurse=True)
                # Sanity gates: child must have consumed at least its own
                # header, and its length must fit within the parent's value.
                if sub.pos > 0 and sub.pos <= len(value):
                    rec.children = [child]
                    rec.tail = value[sub.pos:]
            except (EOFError, ValueError):
                pass

        # Undo mask
        if bit_simple:
            self.mask ^= (tag & 0xFF)

        return rec

    def parse_all(self, *, recurse: bool = False) -> list[Record]:
        out = []
        while self.pos < len(self.data):
            try:
                out.append(self.parse_record(recurse=recurse))
            except EOFError:
                break
        return out


def looks_like_nested(value: bytes) -> bool:
    """Heuristic: does the unmasked value start with what looks like a real record header?

    Rejects all-zero data (zero flags + zero tag does parse as a record but is
    almost always raw padding inside a parent's value, not actual nested TLVs).
    """
    if len(value) < 8:
        return False
    flags = value[0]
    if flags == 0:  # all-zero is raw padding, not a record header
        return False
    bit_wide = bool(flags & 0x80)
    bit_has = bool(flags & 0x40)
    bit_ext = bool(flags & 0x04)
    bit_section = bool(flags & 0x20)
    length_width = (4 if bit_has else 2) if bit_wide else (1 if bit_has else 0)
    pos = 2
    if bit_ext: pos += 2
    if bit_section: pos += 2
    pos += length_width
    if pos > len(value): return False
    return True


def dump_records(records: list[Record], depth: int = 0, max_show: int = 30) -> None:
    indent = "  " * depth
    for i, r in enumerate(records[:max_show]):
        suffix = ""
        if r.children:
            suffix += f"  [child + tail({len(r.tail)} B)]"
        print(f"{indent}#{i:3d} tag=0x{r.tag:04x}({r.tag:5d})  sec={r.section:5d}  "
              f"flags=0x{r.flags:02x}  simple={int(r.has_simple_enc)}  len={r.length:6d}  "
              f"val[:32]={r.value[:32].hex()}{suffix}")
        if r.children:
            dump_records(r.children, depth + 1, max_show=max_show)
            if r.tail:
                print(f"{indent}  tail[:32]={r.tail[:32].hex()}"
                      f"{'...' if len(r.tail) > 32 else ''} ({len(r.tail)} B)")
    if len(records) > max_show:
        print(f"{indent}... ({len(records) - max_show} more)")
