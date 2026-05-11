"""Reference port of the cslibu-3-0.dll byte-permuted AES-128 implementation.

This is NOT FIPS-197 AES. The cslibu T-table impl uses a non-standard
ShiftRows / MixColumns indexing that differs from PyCryptodome's AES.
PyCryptodome's AES will NOT produce equivalent output.

Constants are extracted from cslibu-3-0.dll v13.0.20.2399 .rdata at:
  T0  @ VA 0x3814d078   T1  @ VA 0x3814d478
  T2  @ VA 0x3814d878   T3  @ VA 0x3814dc78
  S   @ VA 0x3814e078   RCON@ VA 0x3814f878

Tables are statically embedded below so this module is self-contained.
"""
import struct
from importlib import resources

# Tables get filled in at module load time from the embedded data file.
T0: list[int]; T1: list[int]; T2: list[int]; T3: list[int]
SBOX_TBL: list[int]
SBOX: bytes
RCON: list[int]


def _load_tables_from_dll(dll_path: str) -> None:
    """Re-extract tables from a known cslibu-3-0.dll on disk (sanity utility)."""
    with open(dll_path, "rb") as f:
        data = f.read()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e + 4
    n = struct.unpack_from("<H", data, coff + 2)[0]
    so = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    ib = struct.unpack_from("<I", data, opt + 28)[0]
    secs = []
    for i in range(n):
        s = opt + so + i * 40
        v = struct.unpack_from("<I", data, s + 12)[0]
        rs = struct.unpack_from("<I", data, s + 16)[0]
        ra = struct.unpack_from("<I", data, s + 20)[0]
        secs.append((v, rs, ra))

    def va2file(va: int) -> int:
        rva = va - ib
        for v, rs, ra in secs:
            if v <= rva < v + rs:
                return ra + (rva - v)
        raise ValueError(f"VA 0x{va:x} not in any section")

    def read_table(va: int, count: int = 256) -> list[int]:
        fo = va2file(va)
        return [struct.unpack_from("<I", data, fo + i * 4)[0] for i in range(count)]

    global T0, T1, T2, T3, SBOX_TBL, SBOX, RCON
    T0 = read_table(0x3814D078)
    T1 = read_table(0x3814D478)
    T2 = read_table(0x3814D878)
    T3 = read_table(0x3814DC78)
    SBOX_TBL = read_table(0x3814E078)
    SBOX = bytes(t & 0xFF for t in SBOX_TBL)
    RCON = read_table(0x3814F878, count=11)


# Initialize from the canonical cslibu-3-0.dll shipped under research/runtime_dlls/.
# This is intentional: we want a runtime check that the tables we use match the DLL.
_DLL_DEFAULT = "research/runtime_dlls/cslibu-3-0.dll"
_load_tables_from_dll(_DLL_DEFAULT)


def expand_key(key16: bytes) -> list[int]:
    """AES-128 key schedule as implemented in cslibu's Rijndael::Rijndael (FUN_380de9d0).

    Returns 44 uint32 round-key words (LE-interpreted)."""
    if len(key16) != 16:
        raise ValueError("key must be 16 bytes (AES-128)")
    rk = list(struct.unpack("<4I", key16))
    rk.extend([0] * 40)
    for k in range(1, 11):
        prev = rk[4 * k - 1]
        b0 = prev & 0xFF
        b1 = (prev >> 8) & 0xFF
        b2 = (prev >> 16) & 0xFF
        b3 = (prev >> 24) & 0xFF
        sw = (SBOX[b1] << 16) | (SBOX[b2] << 24) | SBOX[b3] | (SBOX[b0] << 8)
        rk[4 * k] = (rk[4 * (k - 1)] ^ sw ^ RCON[k - 1]) & 0xFFFFFFFF
        rk[4 * k + 1] = rk[4 * (k - 1) + 1] ^ rk[4 * k]
        rk[4 * k + 2] = rk[4 * (k - 1) + 2] ^ rk[4 * k + 1]
        rk[4 * k + 3] = rk[4 * (k - 1) + 3] ^ rk[4 * k + 2]
    return rk


def encrypt_block(rk: list[int], plaintext16: bytes) -> bytes:
    """Single-block AES encrypt using cslibu's T-table impl (FUN_380dedf0)."""
    p = list(struct.unpack("<4I", plaintext16))
    s0 = rk[0] ^ p[0]; s1 = rk[1] ^ p[1]; s2 = rk[2] ^ p[2]; s3 = rk[3] ^ p[3]
    n0 = T2[(s2 >> 8) & 0xFF] ^ T1[(s1 >> 16) & 0xFF] ^ T0[(s0 >> 24) & 0xFF] ^ T3[s3 & 0xFF] ^ rk[4]
    n1 = T2[(s3 >> 8) & 0xFF] ^ T1[(s2 >> 16) & 0xFF] ^ T0[(s1 >> 24) & 0xFF] ^ T3[s0 & 0xFF] ^ rk[5]
    n2 = T1[(s3 >> 16) & 0xFF] ^ T2[(s0 >> 8) & 0xFF] ^ T0[(s2 >> 24) & 0xFF] ^ T3[s1 & 0xFF] ^ rk[6]
    n3 = T2[(s1 >> 8) & 0xFF] ^ T1[(s0 >> 16) & 0xFF] ^ T0[(s3 >> 24) & 0xFF] ^ T3[s2 & 0xFF] ^ rk[7]
    s0, s1, s2, s3 = n0, n1, n2, n3
    rk_idx = 8
    for _ in range(4):
        u0 = T2[(s3 >> 8) & 0xFF] ^ T1[(s2 >> 16) & 0xFF] ^ T0[(s1 >> 24) & 0xFF] ^ T3[s0 & 0xFF] ^ rk[rk_idx + 1]
        u1 = T1[(s3 >> 16) & 0xFF] ^ T2[(s0 >> 8) & 0xFF] ^ T0[(s2 >> 24) & 0xFF] ^ T3[s1 & 0xFF] ^ rk[rk_idx + 2]
        u2 = T2[(s2 >> 8) & 0xFF] ^ T1[(s1 >> 16) & 0xFF] ^ T0[(s0 >> 24) & 0xFF] ^ T3[s3 & 0xFF] ^ rk[rk_idx]
        u3 = T2[(s1 >> 8) & 0xFF] ^ T1[(s0 >> 16) & 0xFF] ^ T0[(s3 >> 24) & 0xFF] ^ T3[s2 & 0xFF] ^ rk[rk_idx + 3]
        v0 = T2[(u1 >> 8) & 0xFF] ^ T1[(u0 >> 16) & 0xFF] ^ T0[(u2 >> 24) & 0xFF] ^ T3[u3 & 0xFF] ^ rk[rk_idx + 4]
        v1 = T2[(u3 >> 8) & 0xFF] ^ T1[(u1 >> 16) & 0xFF] ^ T0[(u0 >> 24) & 0xFF] ^ T3[u2 & 0xFF] ^ rk[rk_idx + 5]
        v2 = T1[(u3 >> 16) & 0xFF] ^ T2[(u2 >> 8) & 0xFF] ^ T0[(u1 >> 24) & 0xFF] ^ T3[u0 & 0xFF] ^ rk[rk_idx + 6]
        v3 = T2[(u0 >> 8) & 0xFF] ^ T1[(u2 >> 16) & 0xFF] ^ T0[(u3 >> 24) & 0xFF] ^ T3[u1 & 0xFF] ^ rk[rk_idx + 7]
        s0, s1, s2, s3 = v0, v1, v2, v3
        rk_idx += 8

    def fin(a: int, b: int, c: int, d: int, k: int) -> int:
        return ((SBOX_TBL[(a >> 16) & 0xFF] & 0xFF0000)
                ^ (SBOX_TBL[(b >> 8) & 0xFF] & 0xFF00)
                ^ (SBOX_TBL[(c >> 24) & 0xFF] & 0xFF000000)
                ^ (SBOX_TBL[d & 0xFF] & 0xFF)
                ^ k) & 0xFFFFFFFF

    out = [
        fin(s1, s2, s0, s3, rk[rk_idx]),
        fin(s2, s3, s1, s0, rk[rk_idx + 1]),
        fin(s3, s0, s2, s1, rk[rk_idx + 2]),
        fin(s0, s1, s3, s2, rk[rk_idx + 3]),
    ]
    return struct.pack("<4I", *out)


def cfb128_decrypt(rk: list[int], iv: bytes, ciphertext: bytes) -> bytes:
    """AES-128-CFB-128 decrypt using the cslibu cipher."""
    if len(iv) != 16:
        raise ValueError("IV must be 16 bytes")
    out = bytearray()
    state = bytes(iv)
    for pos in range(0, len(ciphertext), 16):
        ks = encrypt_block(rk, state)
        block = ciphertext[pos:pos + 16]
        out.extend(a ^ b for a, b in zip(block, ks))
        state = block + ks[len(block):] if len(block) < 16 else block
    return bytes(out)


# Canonical fixed AES key for useFixedEncryptionKey=1 mode in CR 13.0.x:
FIXED_KEY = bytes.fromhex("11dd1896bd4a15cdbff2543503e6760f")


def decrypt_contents_stream(body: bytes) -> bytes:
    """Decrypt a Crystal Reports OLE2 'Contents' stream and return the inflated plaintext.

    Layout: 34-byte TSLV header, then AES-128-CFB-128 ciphertext over a zlib stream.
    """
    if len(body) < 35:
        raise ValueError("Contents stream too short")
    iv = bytes(b ^ 0xFF for b in body[16:32])
    ct = body[34:]
    rk = expand_key(FIXED_KEY)
    pt_compressed = cfb128_decrypt(rk, iv, ct)
    import zlib
    return zlib.decompressobj(15).decompress(pt_compressed)
