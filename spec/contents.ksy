meta:
  id: crystal_contents_stream
  title: Crystal Reports (CRforVS 13.x) "Contents" OLE-CFB stream
  endian: be
  ks-version: 0.10
doc: |
  The `Contents` stream of a Crystal Reports `.rpt` (CRforVS 13.x) file holds
  the encrypted, compressed report definition. This spec models the outer
  framing that wraps the encrypted body.

  Stream layout:

    +-------------------------------------------------------------+
    | 0..9   : CSRecordArchive TLV header for the outer record    |
    | 10..33 : 24 value bytes (XOR-masked by 0xff)                |
    |          = 6 framing bytes + 16-byte IV + 2 trailing bytes  |
    | 34..N  : AES-128-CFB-128 ciphertext over a zlib stream      |
    +-------------------------------------------------------------+

  Decryption (CR-13 product-wide constants):
    * Cipher : AES-128-CFB-128, **non-FIPS** cslibu byte-permuted T-table
               variant. Standard PyCryptodome / OpenSSL AES will NOT match —
               see `crdis/codec/cslibu_aes.py` for the port.
    * Key    : 11dd1896bd4a15cdbff2543503e6760f
               (cslibu-3-0.dll .rdata @ x86 VA 0x3813a750; replicated 8× each
                in crpe32.dll and craxddrt.dll across the SAP BO 4.0 tree).
    * IV     : `body[16:32] XOR 0xff`. Equivalently, after this spec parses
               the outer record, `value.iv` IS the AES IV (the `process:
               xor(0xff)` step has already been applied).

  Inner plaintext (after AES-decrypt + zlib-inflate) is a `CSRecordArchive`
  TLV record stream. That inner stream is NOT modelled in this ksy yet
  (Round-10 work in progress); see `crdis/codec/cs_archive.py` for the
  reference parser.

  XOR-mask rationale: in CSRecordArchive, every value-byte read is XOR'd by
  a running mask that flips by `tag & 0xff` on entering a record (when the
  `useSimpleEncryption` flag bit is set). The outer record has tag 0xffff
  and the flag bit is set, so its mask flips from 0 to 0xff and stays 0xff
  for the 24 value bytes. The TLV header bytes [0..9] are read at mask = 0
  (i.e. raw).
seq:
  - id: outer_record
    type: outer_tlv
    doc: |
      The single TLV record that wraps the ciphertext. Its value region
      contains the AES IV.
  - id: ciphertext
    size-eos: true
    doc: |
      AES-128-CFB-128 ciphertext, starting immediately after the 34-byte
      outer record. Decryption recovers a zlib stream (header `78 5e ...`,
      32K window, default compression) whose plaintext is the
      `CSRecordArchive` record stream.
types:
  outer_tlv:
    doc: |
      Outer CSRecordArchive TLV record. Encoded at mask = 0 for the 10-byte
      header and mask = 0xff for the 24 value bytes (per the running-XOR
      scheme; tag 0xffff flips the mask from 0 to 0xff on entry).

      Header bytes [0..9] decode as:
        offset  raw           field         meaning
        ------  ------------  ------------  ------------------------------
         0      0xfc          flags         all 6 framing bits set
                                            (wide_len | has_len | section |
                                             flag_50 | simple_enc | ext_tag)
         1      0x00          tag_low8      ignored; ext_tag bit -> use
                                            tag_ext below
         2..3   0xffff        tag_ext       full record tag (BE u16)
         4..5   0x0700        section       BE u16
         6..9   0x00000018    length        BE u32 = 24 value bytes follow
    seq:
      - id: flags
        contents: [0xfc]
        doc: |
          Frame-byte. Bits set: wide_len(0x80), has_len(0x40), section(0x20),
          flag_50(0x10), simple_enc(0x08), ext_tag(0x04). Verified constant
          across observed CR-13 samples.
      - id: tag_low8
        contents: [0x00]
        doc: Low byte of tag; superseded by `tag_ext` because the ext_tag bit is set.
      - id: tag_ext
        type: u2
        valid: 0xffff
        doc: Extended tag = 0xffff (the outer record's class identifier).
      - id: section
        type: u2
        valid: 0x0700
        doc: Section field. Constant 0x0700 in all observed samples.
      - id: length
        type: u4
        valid: 24
        doc: |
          Length of the value region in bytes. Always 24 in observed CR-13
          files: 6 framing + 16 IV + 2 framing trailer.
      - id: value_raw
        size: 24
        process: xor(0xFF)
        type: outer_value
        doc: |
          24 value bytes, read under the running XOR mask 0xff. After the
          XOR the bytes parse as `outer_value` below.
  outer_value:
    doc: |
      24 value bytes of the outer record, AFTER the XOR(0xff) running-mask
      has been applied. Of these, the 16 middle bytes are the AES-128 IV
      that decrypts the ciphertext starting at file offset 34.
    seq:
      - id: framing_head
        contents: [0x00, 0x01, 0x01, 0x00, 0x00, 0x01]
        doc: First 6 value bytes. Observed constant across samples 001..008.
      - id: iv
        size: 16
        doc: |
          AES-128 IV. This is the actual IV used by CFB-128 decryption —
          no further transformation is required because `process: xor(0xFF)`
          has already been applied to the whole 24-byte value region.
      - id: framing_tail
        contents: [0x00, 0x01]
        doc: Final 2 value bytes. Observed constant across samples 001..008.
