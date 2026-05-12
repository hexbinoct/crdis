"""Hard-coded AES-128-CFB-128 test vector against the cslibu (non-FIPS) cipher.

This vector is the first 32 plaintext bytes recovered from sample 001's
Contents stream. The plaintext begins with the zlib magic ``78 5e`` —
which is the expected output of decrypting the AES layer before zlib
inflate.

This test exists to catch a specific failure mode: someone replacing
`crdis.codec.cslibu_aes` with stock `Crypto.Cipher.AES` / PyCryptodome.
The cslibu cipher uses byte-permuted ShiftRows/MixColumns indexing in
its T-tables; standard FIPS-197 AES will NOT match this vector.

Provenance: vector derived from `samples/001_empty/report.rpt` by
  iv = body[16:32] XOR 0xff
  ct = body[34:66]
  pt = cfb128_decrypt(expand_key(FIXED_KEY), iv, ct)
"""
from __future__ import annotations

from crdis.codec.cslibu_aes import FIXED_KEY, cfb128_decrypt, expand_key

KEY_HEX = "11dd1896bd4a15cdbff2543503e6760f"
IV_HEX  = "18742f8498a9863832dd43d7495f8ff7"
CT_HEX  = "03263064ad818654a1b0e99453b32d5e2757f770235739e41575ca5026a086a3"
PT_HEX  = "785ecd574b6f1b55149eb1e33876ecb4a3c413a6f1c4695295c8a99a4a8d88dd"


def test_fixed_key_matches_constant():
    """Guard against the canonical CR-13 fixed key being edited."""
    assert FIXED_KEY.hex() == KEY_HEX


def test_cslibu_aes_cfb_known_vector():
    key = bytes.fromhex(KEY_HEX)
    iv = bytes.fromhex(IV_HEX)
    ct = bytes.fromhex(CT_HEX)
    expected = bytes.fromhex(PT_HEX)

    pt = cfb128_decrypt(expand_key(key), iv, ct)
    assert pt == expected
    assert pt[:2] == b"\x78\x5e", "plaintext must start with the zlib magic header"
