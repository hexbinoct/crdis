meta:
  id: crystal_line_element
  title: Crystal Reports "Line" element — 5-record block decoded layout
  endian: be
  ks-version: 0.10
doc: |
  Decoded layout of one Line element inside a Crystal Reports .rpt
  CSRecordArchive plaintext stream (the post-decrypt, post-inflate inner
  stream, see `spec/contents.ksy` for the outer envelope).

  ## Why this is a "post-decode" spec

  CSRecordArchive bytes on disk are XOR-masked with a running mask whose
  state transitions are tag-dependent. Modeling the running mask in pure
  Kaitai is awkward (it threads state across records the spec can't see).
  This spec therefore models the **unmasked** value bytes of each of the
  five records that make up a Line element — i.e. the values returned by
  `crdis.codec.cs_archive.CSArchiveParser` after it has applied the mask.

  ## The 5-record block

  Every Line element occupies exactly 5 consecutive top-level records in
  the inner stream, in this fixed order:

      idx   tag    role                                Kaitai type below
      ----- ------ ----------------------------------- ----------------------
       0    0xAA   line container (wraps 0xA9 → 0x9E)  rec_aa_value
       1    0xBE   element placement (left, top)       rec_be_value
       2    0xFD   formatting template (wraps 0xFC)    rec_fd_value
       3    0xED   line-style container (wraps 0xEC)   rec_ed_value
       4    0xAB   end-of-element terminator (empty)   rec_ab_value (zero-byte)

  Together these fully describe the line's geometry, name, style and
  thickness. Confirmed by paired-sample diffing of sample 008's two
  inline-defined lines (`samples/008_two_lines_only/`).
types:
  rec_aa_value:
    doc: |
      Value bytes of the 0xAA record. The 0xAA record carries no fields of
      its own; it is a wrapper around a single nested 0xA9 record plus a
      2-byte tail. Total length observed: 94 B (10 B inner header + 84 B
      inner value + 2 B tail).
    seq:
      - id: inner_header
        size: 10
        doc: |
          Inner CSRecordArchive TLV header for the 0xA9 nested record:
          flags=0xf8, tag=0x00a9, section=0x0700, length=0x0054 (=84).
      - id: inner
        type: rec_a9_value
        size: 84
        doc: Nested 0xA9 line-geometry record.
      - id: aa_tail
        contents: [0x00, 0x01]
        doc: |
          Two-byte trailer after the nested record. Observed identical
          (`00 01`) across both Line samples in 008; treat as constant.
  rec_a9_value:
    doc: |
      Value bytes of the 0xA9 record (84 B), the line-geometry container.
      Wraps a single nested 0x9E record plus an 8-byte tail. The tail is
      where the line's *endpoint* (right, bottom) lives.
    seq:
      - id: inner_header
        size: 10
        doc: |
          Inner CSRecordArchive TLV header for the 0x9E nested record:
          flags=0xf8, tag=0x009e, section=0x0700, length=0x0044 (=68).
      - id: inner
        type: rec_9e_value
        size: 68
        doc: Nested 0x9E element-metadata record.
      - id: marker_pre
        contents: [0x00, 0x02]
        doc: |
          Two-byte marker preceding the endpoint pair. Observed constant
          `00 02` across both lines — possibly a "format version" or "kind"
          field; meaning unconfirmed.
      - id: right
        type: u2
        doc: |
          X-coordinate of the line's end point, in twips.

          Verified for both lines in sample 008:
            Line#1 single  -> 5550 (Designer-reported `right=5550`)
            Line#2 dotted  -> 5700 (Designer-reported `right=5700`)
      - id: bottom
        type: u2
        doc: |
          Y-coordinate of the line's end point, in twips.
          Line#1 -> 240, Line#2 -> 870.  Pairs with `right` to give the
          (right, bottom) corner of the line's bounding box. (left, top)
          comes from the 0xBE record — see rec_be_value.
      - id: trailing_pad
        contents: [0x00, 0x00]
        doc: Two trailing zero bytes; padding (likely 4-byte align).
  rec_9e_value:
    doc: |
      Value bytes of the 0x9E record (68 B). Holds the element's bounding
      box width, its name, and a tail of additional fields whose semantics
      are not yet fully decoded.
    seq:
      - id: width
        type: u4
        doc: |
          Bounding-box width in twips (right - left).

          Sample 008 lines:
            Line#1 single  width = 4500 (5550 - 1050)  ✓ 0x00001194
            Line#2 dotted  width = 3990 (5700 - 1710)  ✓ 0x00000f96
      - id: reserved_4_to_20
        size: 16
        contents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        doc: |
          16 zero bytes. Reserved / padding. Possibly an aligned 4×u4
          block that defaults to all-zero for ordinary lines; needs samples
          with non-default behaviour to differentiate.
      - id: name
        type: pascal_u4_string
        doc: |
          Element name as authored in Designer (e.g. "Line1", "Line2").
          Encoded with the same 4-byte BE length-prefix + UTF-8 + NUL
          convention used by tag 0xC2's text content (see rec_c2_value
          in the eventual text-object ksy).
      - id: tail
        size-eos: true
        doc: |
          Remaining bytes (~34 B for a 6-byte name). Begins with `ff ff
          ff ff` then a sequence of structured fields that are identical
          across the two sample-008 lines (e.g. `39 51 07 00` and
          `f9 65 07 00` — possibly element/section IDs). Decoding parked
          until samples that vary one of these vs. the other land.
  rec_be_value:
    doc: |
      Value bytes of the 0xBE record (4 B). Element placement — the
      (left, top) start of the line's bounding box.

      Verified for both lines in sample 008 and across other element
      types (Text Object, Image) — see research/format_notes.md.
    seq:
      - id: left
        type: u2
        doc: X-coordinate in twips.
      - id: top
        type: u2
        doc: Y-coordinate in twips.
  rec_fd_value:
    doc: |
      Value bytes of the 0xFD record (165 B). Static formatting template:
      wraps a 0xFC sub-record (45 B) + 112 B of repeated `00 00 00 01 00
      00 ff ff` 8-byte entries (14 copies). Observed byte-identical for
      both lines in sample 008 and across element types — likely a shared
      default-properties block populated by Designer regardless of element
      kind. Not modelled in detail until a sample modifies it.
    seq:
      - id: inner_header
        size: 10
      - id: inner_value
        size: 45
        doc: 0xFC sub-record value; not decoded yet.
      - id: default_array
        size-eos: true
        doc: 14× 8-byte entries `00 00 00 01 00 00 ff ff`.
  rec_ed_value:
    doc: |
      Value bytes of the 0xED record (130 B). Line-style container: wraps
      a 0xEC sub-record (34 B) + 88 B of repeated `00 00 00 01 00 00 ff
      ff` default entries (same pattern as rec_fd_value).
    seq:
      - id: inner_header
        size: 10
      - id: inner
        type: rec_ec_value
        size: 34
      - id: default_array
        size-eos: true
        doc: 11× 8-byte entries `00 00 00 01 00 00 ff ff`.
  rec_ec_value:
    doc: |
      Value bytes of the 0xEC record (34 B). Encodes the line's style and
      thickness. This is the smoking-gun record for line-style decoding.
    seq:
      - id: pad_0_2
        contents: [0x00, 0x00]
      - id: style
        type: u1
        enum: line_style
        doc: |
          Line style enum. Confirmed values:
            * Line#1 single -> 0x01  (crLineStyleSingle)
            * Line#2 dotted -> 0x04  (crLineStyleDotted)
          The 0/2/3 mappings (None/Double/Dashed) are inferred from the
          published Crystal Reports `LineStyle` enum and are pending
          confirmation from a follow-up sample.
      - id: pad_3_14
        size: 11
        doc: 11 zero bytes; reserved.
      - id: marker_14_18
        contents: [0xff, 0xff, 0xff, 0xff]
        doc: Four 0xff bytes. Observed constant.
      - id: thickness
        type: u4
        doc: |
          Line thickness, in twips. Default thin line = 20 (= 1pt = 1/72").

          Hypothesis: holds the line's stroke thickness for stroked
          styles (Single/Double/Dashed) and zero for non-stroked dotted
          rendering. Observations so far:
            Line#1 single  -> 20 (0x14)
            Line#2 dotted  ->  0 (0x00)
          Needs paired-thickness samples (e.g. 1pt single vs 2pt single)
          to confirm units and rule out coupling with style.
      - id: trailing
        size: 12
        doc: |
          12 trailing bytes, observed constant across the two lines:
          `01 00 00 02 00 00 00 00 00 00 00 00`. The `01` and `02` here
          may be additional style flags or a "version 2" marker.
  rec_ab_value:
    doc: |
      0xAB end-of-element terminator. Zero-length record value.
    seq: []
  # ---- shared building blocks ----
  pascal_u4_string:
    doc: |
      String encoding used by Crystal Reports for object names and text
      content: a big-endian u4 length followed by `length` UTF-8 bytes
      including a trailing NUL. (i.e. `length = strlen(s) + 1`.)
      Same convention as tag 0xC2 (text-object content).
    seq:
      - id: len
        type: u4
      - id: chars
        size: len
        doc: UTF-8 bytes including the trailing NUL.
enums:
  line_style:
    0: none
    1: single
    2: double
    3: dashed
    4: dotted
