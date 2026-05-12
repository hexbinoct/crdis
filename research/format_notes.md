# CRforVS .rpt format — running RE notes

Append-mostly. Each entry: date, sample(s), hypothesis, evidence, status.

Status legend: `hypothesis` (untested) · `supported` (1+ samples agree) ·
`confirmed` (encoded in spec, multiple samples agree) · `falsified` (rejected,
left here as a trail).

---

## What we believe before seeing any bytes

Stuff we expect to find based on prior public knowledge of the format
generation. None of this is verified yet — listed so we can confirm or
falsify it as samples come in.

- **Container:** likely a custom binary layout (not OLE compound document
  in the v13.x era; older v8.x / v9.x versions allegedly were).
- **String encoding:** UTF-16LE for most user-facing strings (label text,
  field names, formulas, SQL).
- **Embedded images:** stored as raw PNG/JPEG/BMP blobs with the format's
  native magic bytes intact (`89 50 4E 47`, `FF D8 FF`, `42 4D`).
- **Coordinate units:** twips (1/1440 inch) is the historical CR
  convention — to verify against Designer's reported numbers in sample 001.
- **Endianness:** little-endian throughout (Windows-native format).

---

## Findings

### 2026-05-08 — Sample pair 001/002: container is OLE Compound File Binary (CFB)

**Samples:** `001_empty/report.rpt` (16384 B), `002_one_label/report.rpt` (16384 B). Both produced by CRforVS 13.x. 002 = 001 + one Text Object "HELLO" in Details, Designer-reported geometry: Left=100, Top=100, Width=1869, Height=221.

**Findings (status: confirmed unless noted):**

1. **The `.rpt` container IS Microsoft Compound File Binary (CFB / OLE Compound Document).** Magic bytes `D0 CF 11 E0 A1 B1 1A E1` at offset 0; CFB v3, 512-byte sectors, little-endian, mini-stream cutoff 4096. This is fully publicly specified (`MS-CFB`); we use `olefile` (pure Python) to enumerate streams. **Earlier prior-knowledge guess that v13.x was a custom binary, not CFB, is FALSIFIED.**

2. **Both files contain exactly 5 streams, with stable names:**
   - `\x05SummaryInformation` — 433/437 B (Δ +4)
   - `Contents` — 1406/1633 B (Δ **+227**) ← carries the report definition
   - `CrystalReportDesignerStream` — 114/114 B, **byte-identical**
   - `QESession` — 64/64 B, differs (high-entropy noise — see #4)
   - `ReportInfo` — 58/58 B, **byte-identical**

3. **Sample-pair size delta (Contents +227 B) is where adding one Text Object lives.** This is the prize stream for Phase 1.

4. **`QESession` is high-entropy random data**, even between two reports with no DB binding. 42 of 64 bytes differ; bytes 0x16–0x3F look uniformly random. Hypothesis: per-save session GUID / salt / nonce. **Ignored for parsing purposes.**

5. **`SummaryInformation` is a standard MS Office property set** (`OLEPS`) — not Crystal-specific. The +4 byte delta is most likely a `LastSavedTime` field update. Trivial to parse (existing libraries handle it).

6. **The `Contents` stream body is encrypted / non-trivially scrambled.** Status: **strongly supported** (multiple consistent negative results).
   - First 16 bytes of `Contents` are identical between both files: `fc 00 ff ff 07 00 00 00 00 18 ff fe fe ff ff fe`. This is a fixed header / magic / format-version block.
   - From offset 0x10 to end-of-stream, the bodies diverge **and never re-converge** (common-tail length = 0). This is not a localized insert; the entire body is content-dependent.
   - Entropy of body ≈ 7.10–7.27 bits/byte across 256-byte windows, ≈ 7.89 overall. (8.0 = random; >7.5 strongly suggests compression or encryption.)
   - **Search for plaintext "HELLO" (UTF-16LE, UTF-16BE, ASCII) across the entire stream: zero hits.**
   - Search for the geometry values 100, 1869, 221 as u16-LE/u32-LE/u16-BE/u32-BE across the entire stream: zero hits.
   - Decompression attempts at offsets 0, 0x10, 0x20, 0x40 with zlib (with/without raw deflate), gzip, lzma: all fail.
   - Single-byte XOR scan across all 256 keys looking for "HELLO": zero hits.
   - Known-plaintext XOR-key recovery on UTF-16LE "HELLO" (10 bytes) at every offset, looking for derived keys with repeating period ≤ 8: zero candidates.
   - Even/odd byte-position distribution is essentially flat (top byte ~9/700 in each parity class) — rules out trivial "XOR every byte with constant K" or "every other byte" schemes.

   **Implication:** The body is either (a) genuinely encrypted (likely a stream cipher with the key in `crpe32.dll` or its v13.x successor), (b) a non-trivial custom scrambling, or (c) compressed with a non-standard codec. Cleartext-format hypothesis is rejected.

**What we DO have, free of charge:**
- Full container parsing (CFB) — can enumerate streams in any `.rpt` cross-platform.
- `CrystalReportDesignerStream` (114 B, identical across our pair) and `ReportInfo` (58 B, identical) — small, low-information static metadata, easy to reverse later.
- `SummaryInformation` — standard Office property set, parseable today.

**Paths forward (open question — requires user direction):**
- **A.** Static RE of the CR runtime DLL (`crpe32.dll` / managed engine assemblies) to find the decryption routine and key. Most thorough; multi-week effort.
- **B.** Dynamic analysis: attach a debugger to a running CR/VS report-loader process, breakpoint on stream read, capture the algorithm at runtime. Often fastest path to a crypto recovery.
- **C.** Search prior community work — older RE forums (woodmann, reverseengineering.SE), GitHub abandonware. We may not be the first to crack this for v13.x.
- **D.** Reverse the older (CR 8.5 / 9 / XI) format, where the Contents stream is reportedly cleartext, to learn the *logical* structure, then come back to v13.x with that knowledge to constrain the decryption hunt. Out of user's primary scope (their files are 13.x) but a strong intelligence multiplier.

### 2026-05-08 — Phase-1 scaffold operational

`crdis` package installable (`pip install -e .`). Three subcommands working today:
- `crdis info FILE` — lists streams (size, sha256, role) + cleartext summary properties.
- `crdis dump FILE -o DIR` — extracts every stream as a separate `.bin` for offline analysis.
- `crdis summary-json FILE` — emits parsed summary as JSON.

Notable extracted facts from samples 001/002:
- `creating_application = "Crystal Reports"` (matches expectation).
- `revision_number` 9 → 10 across the pair (sample 002 was saved one more time than 001).
- Real `create_time` / `last_saved_time` timestamps, sub-second precision.
- `olefile` over-reads `VT_LPSTR` properties past the NUL terminator in CR-written
  property sets — defensive NUL-trim added in `crdis.summary._clean`. Worth revisiting
  if we ever need the trailing bytes (they may carry packed extra properties).

- Container "likely custom binary, not OLE": **FALSIFIED** — it IS OLE/CFB.

---

## Session boundary — 2026-05-08 → next session (macOS M4)

Project being relocated from Windows to macOS M4 for continuation. Status at handoff:

- Phase 1 scaffold complete and tested on Windows (CLI + container + summary parsers).
- Sample pair 001/002 fully analysed; `Contents` confirmed encrypted.
- `research/runtime_dlls/{crpe32_x86,crpe32_x64,crqe_x86}.dll` copied locally for
  upcoming Ghidra static analysis. SHA256s recorded in that directory's README.

**Immediate next step on resume:** install GhidraMCP (LaurieWired's recommended)
on the Mac, point Ghidra at `crpe32_x86.dll`, run auto-analysis, then start
the string-xref hunt on `"Contents"` and on the header magic
`fc 00 ff ff 07 00 00 00 00 18 ff fe fe ff ff fe` to locate the decryption
routine. Detailed install + hunt strategy in `CLAUDE.md`.

No new findings to record — this is a logistics checkpoint only.


- "UTF-16LE strings, embedded PNG/JPEG/BMP magic intact, twips coordinates": **DEFERRED** — none of these are visible in the stream because the body is scrambled. Twips is still the likely *plaintext* unit (Designer reports raw values consistent with twips), but unverifiable until decryption.
- "Little-endian throughout": **supported** — CFB header confirms LE byte order; nothing yet contradicts it.


---

### 2026-05-08 — Ghidra hunt round 1: `Contents` is **compressed**, not encrypted

**Tooling:** GhidraMCP driving Ghidra against `research/runtime_dlls/crpe32_x86.dll`. Auto-analysis complete.

**What I went looking for:** the `Contents`-stream decryption routine. What I actually found rewrites the hypothesis: the body is **compressed by a custom Crystal Decisions algorithm**, with optional encryption layered on top.

**Evidence trail:**

1. UTF-16 string `"Contents"` lives at `crpe32_x86.dll!0x37ed8ac0`. It has 3 xrefs, all in `rptdoc.cpp` per embedded `__FILE__` strings:
   - `FUN_37d21fe0` — **load path** (rptdoc.cpp line ~6043)
   - `FUN_37d19290` — **save path** (rptdoc.cpp line ~5922)
   - (third xref is a duplicate from the same load function)

2. **Load path skeleton** (`FUN_37d21fe0`):
   ```
   CSLib300::CSOleStreamFile::openStream(stg, L"Contents", 0x10, ...)
   CSLib300::CSRecordArchive ar(file, 0x700, 0)        // mode 0x700
   ar.vftable = RDReportFileArchive::vftable           // derived class
   if (ar.isCompressed(&flag)) { ... }                  // <-- decision branch
   if (!ar.isTSLVRecordOfType(100, ...)) {
       // legacy/uncompressed: wrap in CSMainArchive(file, 3, 0x1000) and call CSDoc::do_serialize
   } else {
       ar.loadStreamHeader();                           // reads the 16-byte preamble
       FUN_37d203e0(&ar, ...);                          // body deserializer
       ar.endDecompress();                              // flush decompression state
   }
   ```

3. **Save path skeleton** (`FUN_37d19290`):
   ```
   CSLib300::CSOleStreamFile::createStream(stg, L"Contents", 0x1012, ...)
   CSLib300::CSRecordArchive ar(file, 0x700, 0x1001)   // 0x1001 = "compress" flag
   ar.vftable = RDReportFileArchive::vftable
   ar.storeStreamHeader();                              // writes the 16-byte preamble
   (*vtable[0x180])(&ar, ...);                          // serialize doc tree
   ar.compress();                                       // CRC + flush compressed buffer
   if (m_isEncrypted) CSLib300::CSDoc::setIsEncrypted(this, 1);
   ```

4. The decompressor itself is `CSLib300::CSZCompressor::decompress(...)` (visible as an import thunk at `0x37db380e` — 11-arg signature, includes IO file pointers and two `uchar*` buffer args, classic LZ-style state). Per-doc orchestrator: `CSLib300::CSDoc::decompressAllStreams` @ `0x37db3e8c`.

**Implications:**

- **The 16-byte fixed prefix `fc 00 ff ff 07 00 00 00 00 18 ff fe fe ff ff fe` is a `CSRecordArchive` stream-header / TSLV preamble, NOT a cipher IV.** Likely fields: a 2-byte marker (`fc 00`), a 32-bit "stream-header" tag (`ff ff 07 00`), a 32-bit version/length (`00 00 00 18` BE-ish or `18 00 00 00` LE — a `0x18`/24-byte expected payload would fit), and an 8-byte trailing pattern that's plausibly an initial dictionary / flag word.
- **High body entropy (7.10–7.27 b/B) is consistent with compressed output**, not encrypted output. We had previously *ruled out* zlib/gzip/lzma — the format is a Crystal-proprietary `CSZCompressor`. (A plausible candidate from the era: a hand-rolled LZ77/LZSS variant; Crystal's `CSLib300` predates wide adoption of zlib in their stack.)
- **Encryption is a separate, optional layer** keyed off `m_isEncrypted` (member offset `0x13a` on `CSDoc`). Set at save time via `setIsEncrypted`. Our current samples have it OFF (no password set in Designer), so we can ignore encryption for now and focus solely on the compression codec.
- **Implementation lives in a sibling DLL: `CSLib300`.** All the relevant symbols (`CSOleStreamFile`, `CSRecordArchive`, `CSZCompressor`, `CSDoc`) are imported, not defined here. **Next session needs to locate the `CSLib300.dll` (likely in the CRforVS install dir) and import it into Ghidra** to see the actual `decompress` body.

**Status updates to prior findings:**

- Finding "Contents body is encrypted/scrambled": **REVISED** to "compressed, with optional encryption layered on top." Encryption falsified for our two samples.
- Header magic 16-byte prefix: **identified** as a `CSRecordArchive` stream-header structure (TSLV preamble), produced by `storeStreamHeader` and consumed by `loadStreamHeader`. Not random, not a cipher IV.

**Next step:** find `CSLib300.dll` (or whatever runtime DLL exports `CSZCompressor::decompress`), import into Ghidra, decompile the actual `decompress` and `loadStreamHeader` to recover the codec and header layout.


---

### 2026-05-08 — Ghidra hunt round 2: `cslibu-3-0.dll` decompiled — header layout + AES recovered

**Tooling:** `cslibu-3-0.dll` imported into Ghidra, image base `0x38030000`. The `CSLib300` namespace is in fact `cslibu-3-0.dll` (CSLibU = CS Lib Unicode 3.0). User originally couldn't find `CSLib300.dll` because that name doesn't exist on disk; the C++ namespace and the on-disk filename diverge.

**Functions decompiled:**
- `CSLib300::CSRecordArchive::loadStreamHeader` @ `0x3809abf0`
- `CSLib300::CSRecordArchive::isCompressed` @ `0x38099f40`
- `CSLib300::CSRecordArchive::createCompressorForDecompressing` @ `0x38099800`
- `CSLib300::CSZCompressor::decompress` @ `0x380b6e40`

**`isCompressed` is a one-liner:** `return isTSLVRecordOfType(this, 0xffff, &outFlag);` — i.e., check whether the next record at the head of the stream has type marker `0xffff`. Type `0xffff` is the convention for "this is a stream/header record, not user data."

**`loadStreamHeader` — the 16-byte preamble decoded.** It reads a TSLV record of type `0xffff` subtype `0x65` (= 101) and pulls out the following fields *in order*:

```c
short isEncrypted;            // -> CSDoc::setIsEncrypted
short encryptionVersion;      // -> CSDoc::setEncryptionVersion
short useFixedEncryptionKey;  // -> CSDoc::setUseFixedEncryptionKey       (!!)
if (isEncrypted) {
    uchar key[16];            // -> stored at this+0xb4 .. this+0xc3
}
short trailingShort;          // -> this+0xc4 (likely a checksum/CRC seed)
```

Then it calls `initializeForDecompressing(this)`. Each `load()` call appears to be TLV-aware (length-prefixed within the outer record), which is why the literal 16 raw bytes don't decode as a flat C struct.

**`CSZCompressor::decompress` — the codec body.** The function is the orchestrator for chunked decompress with optional in-stream AES:

- Allocates two work buffers (`allocateBuffers`) — input and output staging, each of fixed chunk size.
- **Chunk size constant: `0xfc00` (= 64512 = 63 KiB).** This is the value `local_res8[0]` is initialized to and the size passed to subsequent buffer fills. **The `fc 00` first two bytes of the stream header are the chunk-size constant being mirrored into the header**, not an arbitrary magic.
- The decompress loop:
  1. Read up to `0xfc00` bytes from the input file via virtual `vtable[0x88]` on the compressor.
  2. **If `param_8 != 0`, run the chunk through `RijndaelEncryption` first (using a 16-byte key in `param_9`).** AES-128 confirmed — Rijndael with a 16-byte block.
  3. Call `FUN_380f7410(state, in, &consumed, out, &out_remaining)` repeatedly — this is the actual entropy-decoder step (LZ inflate-equivalent). State is initialized by `FUN_380f7680(&state)` and torn down by `FUN_380f7550(state)`. Likely: a Crystal-licensed third-party z-stream library, or a hand-rolled LZSS variant (TBD by decompiling these helpers).
  4. Flush decoded output to `outFile` via `FUN_3807e490` in `0xfc00`-sized chunks.
  5. Loop until the inflater returns `1` (end-of-stream).
- Returns total output length via `*param_5`.

**Confirmed major points:**

1. **Encryption primitive is AES-128 (Rijndael).** The `RijndaelEncryption` vftable is wired into the decompress loop unconditionally; whether it actually runs is gated on `param_8` (= `m_isEncrypted` propagated from the doc).
2. **The encryption key is 16 bytes**, stored in the stream header itself when `isEncrypted=1`. For password-protected reports this is presumably a wrapped/derived key.
3. **`useFixedEncryptionKey` flag is the smoking gun.** When set, the 16-byte key in the header is the *fixed* key — meaning Crystal embeds a hard-coded key in `cslibu-3-0.dll` that decrypts these reports. **If we can locate that constant, we can decrypt any report that uses fixed-key mode** — useful for the corpus of "encrypted but no user password" reports that older Crystal versions produced. **Open follow-up.**
4. **Chunk size `0xfc00` (63 KiB)** is the codec's working block size. Helpful: it bounds memory needs for our parser.
5. **Compression substrate is most likely a third-party stream codec** (the `FUN_380f7680` / `FUN_380f7410` / `FUN_380f7550` triplet has the shape of `inflateInit / inflate / inflateEnd`). Even though we ruled out *zlib's wire format* on the raw bytes, the *algorithm* could still be deflate-ish — the wire framing is just wrapped by Crystal's chunked-with-optional-AES layer that we now need to peel off. Decompiling those helpers next will tell us if it's deflate, LZS, LZSS, or hand-rolled.

**Status updates:**
- Header magic `fc 00 ff ff …` is now fully explained: `fc 00` = chunk size constant, `ff ff` = TSLV record-type marker for "stream header record", remaining bytes = TLV-encoded `isEncrypted/encryptionVersion/useFixedEncryptionKey/...`.
- Hypothesis "Contents body is a custom-only LZ scheme" → revised to "chunked framing (Crystal-specific) wrapping a generic stream codec, with optional AES per-chunk."

**Next concrete step:** decompile `FUN_380f7680` (init), `FUN_380f7410` (step), `FUN_380f7550` (end), and the chunk-emit `FUN_3807e490`. Determine whether the inner codec is deflate (look for fixed Huffman tables), LZSS (look for sliding-window code), or something else. Also locate the fixed-key constant referenced when `useFixedEncryptionKey=1` — start by xref'ing `RijndaelEncryption` constructor sites with constant key buffers.


---

### 2026-05-08 — Ghidra hunt round 3: codec stack identified end-to-end

**Tooling:** `cslibu-3-0.dll` decompiled exhaustively across the encrypt/decrypt/inflate path. Plus a cross-reference into the actual file imports via `objdump -p`.

**The complete codec stack is now known.** Each layer is identified, and we have:
- ✅ The exact algorithms (AES-128-CFB-128 over deflate)
- ✅ The fixed AES-128 key (extracted from `cslibu-3-0.dll` `.rdata`)
- ✅ The on-disk header layout up to and including the IV
- ❌ Empirical decryption + inflate still failing — see "outstanding mystery" below

**1. Inner codec is deflate, supplied by a sibling DLL `boezlib.dll`.**

`FUN_380f7680` calls `BO_inflateInit_(state, "1.2.3.f-Business-Objects", 0x58)`. The version string and 0x58 (= 88, the size of `z_stream` on x64) confirm the API is *literally* zlib. `objdump -p cslibu-3-0.dll` lists `boezlib.dll` as an imported DLL — that's "Business Objects Enterprise zlib", a sibling runtime-DLL fork of zlib 1.2.3. **Functions `BO_inflate / BO_inflateInit_ / BO_inflateEnd / BO_inflateReset` are imported from boezlib.dll**; cslibu wraps them in `FUN_380f7680/7410/7550`. The wire format is *raw* deflate (no zlib `78 9C` header, no Adler-32 trailer) — Crystal does its own framing.

**2. Encryption is AES-128 in CFB-128 mode (byte-stream).**

`FUN_380f9a30` is the per-byte process-block function. Walked carefully:
```c
if (state.pos == 16) {
    memcpy(input_register, output_buffer, 16);   // feedback last 16 ciphertext bytes
    AES_encrypt(input_register, output_buffer);   // re-keystream
    state.pos = 0;
}
ks = output_buffer[state.pos];
output_buffer[state.pos] = b;        // store input byte (== ciphertext on decrypt)
state.pos++;
*data_ptr = b XOR ks;
```

That's textbook **AES-128-CFB-128**: 16-byte block, full-block feedback. Construction (`FUN_380f86d0`) seeds the input register with the IV and runs AES once to populate the initial keystream block. Two CFB wrapper instances are created in `FUN_380b81f0` (slots `+0x90` and `+0x98` in the compressor) — almost certainly read-side and write-side, both seeded with the same IV but stateful independently from then on. CFB doesn't need 16-byte alignment of ciphertext (stream cipher).

**3. The fixed AES-128 key has been recovered from `cslibu-3-0.dll`.**

`CSDoc::CSDoc()` (default ctor at `0x38065360`) initializes the document's encryption-key field (offset `+0x2ee` in `CSDoc`) to a 16-byte constant living in `.rdata` at VA `0x381667f8` (file offset `0x1357f8` in our copy):

```
fixed AES-128 key = 11 dd 18 96 bd 4a 15 cd bf f2 54 35 03 e6 76 0f
```

This is the per-build-version fixed key used when `useFixedEncryptionKey=1`. **Note:** this exact key bytes are from the x64 build of `cslibu-3-0.dll` shipped with a CRforVS install dated `2018-01-09` (file mtime). The x86 build of the same DLL version *should* contain the same key (the constant is binary-identical across architectures of the same release), but we have not yet verified — secondary samples on the Windows side still fail to decrypt with this key, see below.

**4. The save path always writes `isEncrypted = 1` — there is no plaintext mode.**

`CSRecordArchive::storeStreamHeader` (`0x3809c860`) hardcodes `store(this, (short)1)` for the `isEncrypted` field. Every Crystal-saved `.rpt` is encrypted, regardless of whether the user set a password. Password-protection is presumably an *additional* layer keyed by user input rather than an alternative.

**5. Header layout — confirmed by sample diff.**

Diffing the `Contents` streams of sample 001 vs sample 002 (which differ only by adding one Text Object in Designer):

| Offset | Length | Identical? | Meaning |
|-------:|-------:|:-----------|:--------|
| 0..15  | 16     | ✓ identical | TSLV record preamble + isEncrypted/version/fixedKey shorts (see notes below) |
| 16..31 | 16     | ✗ all bytes differ | **AES-128 IV** (per-save random, generated by `srand(time()) + rand() % 255` loop) |
| 32..33 | 2      | ✓ identical (`ff fe`) | Trailing short or record terminator written by `endRecord` |
| 34+    | varies | ✗ differs   | AES-128-CFB-128 ciphertext of the deflate stream of the report body |

Constant 16-byte preamble for both samples: `fc 00 ff ff 07 00 00 00 00 18 ff fe fe ff ff fe`.

**6. Outstanding mystery — empirical decrypt+inflate still fails.**

With key + IV + ciphertext-start, attempted: `AES.new(KEY, MODE_CFB, iv=body[16:32], segment_size=128).decrypt(body[34:])` then `zlib.decompressobj(-15).decompress(...)`. Result: deflate fails with `invalid distance too far back` — meaning Huffman decoding succeeds for the first block but a back-reference points before the start of the LZ77 window. Tried offsets 32..79; no offset yields a clean inflate. Two remaining hypotheses (in priority order):

a. **Preset dictionary in BO_inflate.** Business Objects's "1.2.3.f" zlib fork may seed the LZ77 sliding window with a constant before the first inflate step. This is exactly what would cause "too far back" at the first non-trivial back-reference. The dictionary, if it exists, lives in `boezlib.dll` — not yet acquired.

b. **Wrong ciphertext start offset.** The header record's TLV preamble may be longer than 16 bytes if `endRecord` writes an additional terminator or checksum. Determining the exact offset requires decompiling `endRecord` and `FUN_37d203e0` (the post-header body deserializer in crpe32).

**Status of prior hypotheses:**
- "Header is exactly 16 bytes" → **REVISED**: the header is at least 32 bytes (TLV preamble 16 + IV 16); ciphertext likely starts at offset 34.
- "Encryption is optional" → **FALSIFIED**: save path hardcodes `isEncrypted=1`; all `Contents` streams are encrypted.

**Concrete next steps (open):**
1. Acquire `boezlib.dll` from the Crystal install, import into Ghidra, audit `BO_inflateInit_` for any `inflateSetDictionary`-equivalent call or constant blob being copied into the inflate state's window field.
2. Decompile `CSRecordArchive::endRecord` and `FUN_37d203e0` to nail down exactly where deflate input starts.
3. Once both are resolved: round-trip test on sample 001 (the smaller one, simpler ground truth: empty report).


---

### 2026-05-09 — Round 4: full header layout decoded; remaining blockers identified

**Header layout — every byte explained.** Decompiling `CSRecordArchive::endRecord` showed the back-patch for the length placeholder. Combined with `storeStreamHeader`'s field order, the on-disk layout of the encryption header record is:

| Bytes | Length | Content | Encoding |
|------:|-------:|:--------|:---------|
| 0..8  | 9      | TSLV preamble (record-tag `0xffff`, count, mask byte) | per `startRecord` framing |
| 9     | 1      | Length-of-value-bytes = `0x18` (= 24) | back-patched by `endRecord` |
| 10..11 | 2     | `isEncrypted` (always `1`) — stored as `ff fe` | **XOR'd with running mask** |
| 12..13 | 2     | `encryptionVersion` (`0x100`) — stored as `fe ff` | XOR'd |
| 14..15 | 2     | `useFixedEncryptionKey` (`1`) — stored as `ff fe` | XOR'd |
| 16..31 | 16    | per-stream IV (random per save) — XOR'd with mask | XOR'd |
| 32..33 | 2     | trailing short (`1`) — stored as `ff fe` | XOR'd |
| **34..end** | varies | **AES-128-CFB-128 ciphertext of raw deflate stream** | not XOR'd |

**The "running XOR mask" is `0xfe` per byte** (at least for the visible payload bytes). Empirical proof:
- `01 00` (=1) at offsets 10–11 appears as `ff fe` → `0x01^0xfe=0xff`, `0x00^0xfe=0xfe` ✓
- `00 01` (=0x100) at offsets 12–13 appears as `fe ff` ✓
- `01 00` (=1) at offsets 14–15 and 32–33 → `ff fe` ✓

So the recovered IV is `body[16:32] XOR 0xfe`. Tested empirically on sample 002 with `ct_start=34`: deflate begins parsing valid block structure but fails with "invalid distance too far back" — **the textbook preset-dictionary symptom**. This is the same error we'd seen earlier; now we know all the framing is correct, so the deflate-side preset dictionary is the only remaining cause.

**Remaining blocker #1 — preset dictionary in `boezlib.dll`.** The "1.2.3.f-Business-Objects" zlib fork most likely seeds the LZ77 sliding window with a constant before the first inflate step. We have no way to extract that dictionary without `boezlib.dll`.

**Remaining blocker #2 — fixed-key cross-build mismatch.** The cslibu we have is the **x64** build (`mfc140u.dll`, `MSVCP140.dll`, has `.pdata`/`.gfids` sections). Our samples were authored by **CRforVS 13.x x86** (MFC80, MSVCR80 toolchain). The fixed AES key constant is build-specific — it lives in `.rdata` of whichever cslibu binary did the encryption. The 16-byte constant at `0x381667f8` (`11dd1896bd4a15cdbff2543503e6760f`) is from the x64 build; the x86 build may have a *different* key. Sample 001 produced "invalid stored block lengths" rather than "too far back" at the structurally correct offset, which is consistent with the wrong key (random plaintext occasionally parses as a malformed stored block).

**Concrete next steps (revised):**
1. Acquire the **x86** `cslibu-3-0.dll` matching CRforVS 13.0.20.2399 — should sit alongside `crpe32_x86.dll` in the same `win32_x86\` directory. Re-extract the 16-byte fixed key from that binary's analogous `.rdata` location (find the same `CSDoc::CSDoc()` default constructor and follow the const memcpy). Compare with the x64 key — differences confirm build-specific keys.
2. Acquire `boezlib.dll` (x86 build for CRforVS 13.x, both architectures if available). Import into Ghidra; audit `inflateInit_` for any `inflateSetDictionary`-equivalent or `memcpy(state.window, const_blob, 32768)` pattern. Extract the dictionary blob if found.
3. With both x86-key and dictionary in hand: retry decryption + raw-deflate-with-preset-dictionary on sample 002 (ct_start=34, IV=body[16:32]^0xfe). Sample 002 chosen first because its body is non-empty and will produce decoded plaintext we can sanity-check against Designer-reported geometry (the "HELLO" Text Object at 100/100/1869/221).

**What's on disk so far in `research/runtime_dlls/`:** `crpe32_x86.dll`, `crpe32_x64.dll`, `crqe_x86.dll`, `cslibu-3-0.dll` (x64 — needs to be supplemented with x86 build).


---

### 2026-05-09 — Round 5: preset-dictionary hypothesis falsified; key mismatch is the blocker

**Tooling:** `boezlib.dll` (x64 build, image base `0x180000000`, ~80 KB) imported into Ghidra. This is the BO zlib fork that hosts `BO_inflate*`.

**Preset-dictionary hypothesis FALSIFIED.** Decompiled `BO_inflateInit_` and `BO_inflateInit2_`:

```c
void BO_inflateInit_(state, version, stream_size) {
    BO_inflateInit2_(state, 0xf, version, stream_size);  // windowBits=15
}

undefined8 BO_inflateInit2_(state, windowBits, version, stream_size) {
    if (version[0] != '1' || stream_size != 0x58) return Z_VERSION_ERROR;
    // allocates 0x2548 bytes of inflate state (default 32KB window included)
    // sets up alloc/free thunks
    // calls BO_inflateReset(state)
    return Z_OK;
}
```

`windowBits=15` is **stock raw deflate with 32 KB sliding window** — no preset dictionary, no special framing. There is **no `memcpy` from a `.rdata` blob into the inflate window** anywhere in `BO_inflateInit2_` or its callees during init. `BO_inflateSetDictionary` is exported but **never called from inside `boezlib.dll`** (xrefs are export-table-only). Therefore: the BO zlib fork is essentially **stock zlib 1.2.3 with vendor-prefixed symbols**. Algorithm-wise, raw deflate.

**With preset-dictionary ruled out, the remaining "invalid distance too far back" symptoms are explained as random-data noise.** Brute-force search across {IV: raw / xor 0xfe / xor 0xff / reversed / xor-index, mode: CFB-128 / CFB-8 / OFB / CTR / CBC, ct_start: 28..41, ct-mask: None / 0xfe / 0xff} on sample 002: zero results that decode meaningful output. The "too far back" hits at various offsets are consistent with random plaintext occasionally parsing as a valid first deflate block by chance.

**Conclusion: the AES key is wrong for our samples.** The 16-byte constant `11dd1896bd4a15cdbff2543503e6760f` extracted from x64 `cslibu-3-0.dll` does not match the key used to encrypt sample 001 / 002. Most likely cause: build-specific keys across CR product versions or architectures.

**Cross-version key context (per user 2026-05-09):**
- The original `crpe32_x86.dll` was copied from a Windows dev laptop whose installed CR version is unknown.
- The current `cslibu-3-0.dll` and `boezlib.dll` were copied from a *different* Windows machine that only has the x64 build of CR installed.
- These two CR installations may be different product versions (CRforVS 13.x vs. SAP Crystal Reports 2020+, etc.). The `cslibu-3-0.dll` filename is preserved across versions but the embedded key constant likely is not.

**Concrete next steps (tightened):**
1. **Locate the original CR install that authored sample 001 / 002.** This is probably the dev-laptop install matching `crpe32_x86.dll`'s `13.0.20.2399` version. The matching `cslibu-3-0.dll` (x86 build) lives alongside `crpe32_x86.dll` in that install's `win32_x86\` directory. Extract its key constant via the same `CSDoc::CSDoc()` ctor inspection. **This is the single highest-leverage next step.**
2. As a secondary cross-check: extract the same key field from the *x64* build of `crpe32` (`crpe32_x64.dll`, already on disk) by following the analogous path through whichever `cslibu` ships alongside it. If matching the x64 cslibu we already have, we know the current cslibu pairs with the x64 crpe32.
3. Once the matching key is recovered: full empirical decrypt of sample 002 should yield raw deflate of the report body. Round-trip back to sample 002's bytes confirms; visible plaintext (e.g., the literal string "HELLO" or twip values 100/100/1869/221) doubly confirms.

**Falsified hypotheses recorded:**
- "BO zlib uses a preset dictionary that seeds the LZ77 window" → falsified by direct decompilation of `BO_inflateInit2_`.
- "The x64-extracted key works for the x86-authored samples" → falsified by exhaustive brute-force search.

**Confirmed and stable across this round:**
- Codec stack: AES-128-CFB-128 over raw deflate (zlib 1.2.3 algorithm, vendor-prefixed).
- Header layout: 9-byte preamble, length byte at offset 9, 24 value-bytes (3 shorts XOR'd with running mask 0xfe + 16 raw IV bytes + 1 trailing short XOR'd), ciphertext at offset 34.
- Encryption is non-optional: every `Contents` stream is encrypted.


## Round 6 — x86 cslibu RE: corrects Round 4 framing, confirms standard AES-128-CFB-128, key still wrong

User pulled the matching x86 `cslibu-3-0.dll` and `boezlib.dll` from the original CR install. Reanalysis with the x86 build clears up several Round-4 errors and tightens the picture. The AES key extracted from `.rdata` is **identical to the x64 build** at the structurally analogous location, so the "build-mismatch" hypothesis from Round 5 is dead — the key really is the same blob. But it still doesn't decrypt our samples.

### Findings (high confidence)

- **Cipher is genuinely AES-128-CFB-128.** RTTI strings (`Rijndael`, `RijndaelEncryption`, `RijndaelDecryption`, `cfbEncryption != NULL`, `cfbDecryption != NULL`) plus full inspection of the cipher constructor (`FUN_380dfa20`) and the encrypt/decrypt routines (`FUN_380dfc00` / `FUN_380dfcc0`) leave no doubt. The CFB constructor sets `block_size = 0x10` and defaults `segment_size = 0x10` when caller passes `0` — i.e. CFB-128. The keystream-refill (`FUN_380dfac0`) does the standard CFB shift-register update.
- **Key expansion is standard FIPS-197 AES.** The S-box at `DAT_3814e078` is the canonical AES S-box (replicated 4× per dword for column-mask extraction), and the round-constant table at `DAT_3814f878` is the canonical RCON (`0x01, 0x02, 0x04, …, 0x36`, stored big-endian as dwords). The expansion code at `FUN_380de9d0` produces the standard schedule when bytes are interpreted as big-endian words (which is the FIPS convention) — no exotic byte permutation.
- **Key location:** `CSDoc + 0x12a` (16 bytes). Default ctor `CSLib300::CSDoc::CSDoc()` at `0x38049780` byte-copies `[0x3813a750..0x3813a760]` into `this+0x12a` via a 16-iteration loop. Bytes at that address: `11 dd 18 96 bd 4a 15 cd bf f2 54 35 03 e6 76 0f`. **Identical** to the x64 build's analogous location; the bytes immediately following are UTF-16LE `"Contents"`, confirming we're reading the right region.
- **Key is fetched at write time from `CSDoc + 0x12a` unconditionally.** Both `CSRecordArchive::compress()` (`0x38077d30`) and `initializeForDecompressing()` (`0x38077c60`) call `CSDoc::getEncryptionKey(this->csdoc, &local_key); FUN_38093330(this->compressor, &local_key, this+0x70)` — `useFixedEncryptionKey` does **not** gate which key is used; it's just metadata written to the header.
- **`setEncryptionKey` is exported but never called inside `cslibu`** (xrefs limited to export table). Likewise `setEncryptionKey` is **not in `crpe32_x86.dll`'s import table**, though `getEncryptionKey`, `getEncryptionIV`, `isEncrypted`, `setIsEncrypted` are imported (and called from ~14 sites in crpe32). So the key in `CSDoc+0x12a` is set only by the default ctor unless an as-yet-unidentified DLL/EXE in the CR stack overrides it.

### Round-4 framing corrections (these were wrong in earlier rounds)

- **Header values are stored big-endian, not little-endian.** `CSRecordArchive::store(unsigned short)` at `0x38076de0` and `store(long)` at `0x38076e00` byte-swap before writing (`CONCAT11(low, high)` then `storeBlock`). Single-byte `store(uchar)` at `0x38076dd0` does no swap.
- **Running XOR mask is `0xff`, not `0xfe`.** `CSRecordArchive` ctor (`0x38076ca0`) initializes `this[0x58] = 0`. `startRecord` updates the mask only when `useSimpleEncryption` is set: `this[0x58] ^= byte(recordTag)`. For the stream-header record (`recordTag = 0xffff`), the mask transitions `0 → 0xff` *after* startRecord's own writes are out, before the value-byte stores begin. Re-decoding header bytes 10..15 (`ff fe fe ff ff fe`) with mask `0xff` and **big-endian** shorts gives `0x0001, 0x0100, 0x0001` — `isEncrypted=1, encryptionVersion=0x100, useFixedEncryptionKey=1`. Round 4's "mask 0xfe, little-endian" was off in both halves and only happened to match for the value-shorts.
- **Bulk ciphertext (body[34:]) is not XOR-masked.** It bypasses `storeBlock` and is written via the `CSZFileBufferCompressor` pipeline directly to the underlying file buffer. Only the 34-byte header is mask-XOR'd.

### IV resolution

- Per-byte: `storeStreamHeader` at `0x38078550` generates IV bytes via `(rand() * 0xff) % 0x7fff` truncated to uchar, writes each via `store(uchar)` (single-byte XOR by mask).
- Memory IV at `CSRecordArchive + 0x70` = (file IV bytes at `body[16:32]`) **XOR `0xff`**.
- `CSRecordArchive` ctor pre-fills `this+0x70..+0x80` with 16 bytes from `DAT_38142660`, but those are all zeros and get overwritten by storeStreamHeader's random bytes before encryption uses them — irrelevant.

### Decrypt recipe attempted

```python
key = bytes.fromhex('11dd1896bd4a15cdbff2543503e6760f')
iv  = bytes(b ^ 0xff for b in body[16:32])
ct  = body[34:]
pt  = AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).decrypt(ct)
zlib.decompressobj(-15).decompress(pt)   # → "invalid code lengths" / "invalid stored block lengths"
```

Plaintext `pt[16:]` (which depends only on key + ct[0:16], not on IV) is high-entropy random — meaning the **key**, not the framing, is wrong. Sweeps of {key permutations: raw, full-reverse, per-word-reverse, XOR-0xfe, XOR-0xff} × {IV permutations: raw, full-reverse, per-word-reverse} × {modes: CFB-8/16/32/64/128, CBC, OFB, CTR} × {ct masks: raw, ^0xfe, ^0xff} all fail to produce inflatable plaintext.

### Web check (per user's prompt to look outside, 2026-05-10)

No prior independent reverse-engineering of the CR `.rpt` Contents-stream encryption surfaced. `dbatesx/CRDiff` (the most-cited "Crystal Reports binary parser" on GitHub) is in fact a thin C# wrapper over the proprietary `CrystalDecisions.CrystalReports.Engine` SDK — it loads reports via the SDK and serializes the SDK-exposed object graph; it does no direct binary parsing. Useful as a baseline if we ever want a "ground truth" oracle (run CRDiff on a sample and compare against our Kaitai-spec output), but contributes nothing to the cipher hunt.

### Brute-force scan of `.rdata` / `.data`

Scanned every byte-aligned 16-byte window in both crpe32 and cslibu's `.rdata` and `.data` sections as a candidate AES key, against sample 002 with all three plausible IV transforms. The validation predicate (`zlib raw-inflate ≥ 100 bytes`) is too weak — it surfaces ~20 false positives across both DLLs that all turn out to be degenerate streams emitting a repeating byte (deflate's "RLE filler" patterns). No real match. A stronger predicate (e.g. inflated size ≥ 1KB AND output entropy < 7.5 bits/byte AND contains `"\x00C\x00r\x00y\x00s\x00t"` or other Crystal-Reports-shaped UTF-16 markers) would tighten this dramatically — try that in Round 7 if static-only continues.

### Status as of 2026-05-10

We have a complete, structurally-verified picture of the encryption pipeline except for the 16-byte AES key. The key location in process memory (`CSDoc + 0x12a`) is known. Static analysis has run out of leverage — the .rdata constant doesn't match samples and `setEncryptionKey` has no internal callers in the two DLLs we've decompiled.

### Round 7 plan

Two productive directions, in order of expected leverage:

1. **Live process key dump (Windows).** Open a sample `.rpt` in CR Designer, attach a debugger (x64dbg, WinDbg) to `CRforVS.exe` (or the Designer host), break on `?getEncryptionKey@CSDoc@CSLib300@@QBEXQAE@Z`, dump the 16 bytes at `*(this+0x12a)`. This is decisive: whatever value is there at runtime is *the* key for that file. Same technique works on the read path (open the file, hit `getEncryptionKey` via `initializeForDecompressing`).

2. **Hunt for the upstream caller of `setEncryptionKey` across the rest of the CR DLL tree.** The Designer host EXE plus `crqe.dll`, `CrystalDecisions.*` (the .NET wrappers — but those just P/Invoke into the same C++ DLLs), and any `boe`/`sap` stubs. The exported mangled name `?setEncryptionKey@CSDoc@CSLib300@@QAEXQAE@Z` will appear as a string in whichever DLL calls it; `grep -rL` across the install tree narrows it fast.

If either path turns up a key that decrypts sample 002, lift it into a `crdis decrypt` CLI helper and start populating `spec/contents.ksy` for the 34-byte header (now fully understood: 7-byte record-header + 1-byte length-prefix + 1-byte length + 6-byte value-shorts (BE, masked 0xff) + 16-byte IV (masked 0xff) + 2-byte trailing short (BE, masked 0xff)).

## Round 7 — Cross-binary search (2026-05-10): the .rdata key really is the key

User pulled the full SAP BusinessObjects Enterprise XI 4.0 win32_x86 install tree (~2,236 DLLs) into `research/runtime_dlls/SAP BusinessObjects Enterprise XI 4.0/win32_x86/`. Identity check:
- `cslibu-3-0.dll` and `crpe32_x86.dll` in `runtime_dlls/` are byte-for-byte identical (sha256 match) to the SAP BO 4.0 copies. All three relevant binaries (cslibu, crpe32, craxddrt) report FileVersion `13.0.20.2399`.

### Cross-binary findings

**Search 1 — mangled symbol of `setEncryptionKey`** (`?setEncryptionKey@CSDoc@CSLib300@@QAEXQAE@Z`) across all 2,236 DLL/EXE files: **only `cslibu-3-0.dll` contains it**. Same is true for `setUseFixedEncryptionKey` and `setEncryptionVersion`. None of the related setters are imported by any other binary — they exist as exports of cslibu only, but nothing calls them. By contrast `setIsEncrypted` is referenced from `craxddrt.dll` and `crpe32.dll` (those binaries flip the encrypted flag, but never set the key).

**Search 2 — the 16-byte key constant `11dd1896bd4a15cdbff2543503e6760f`** as a raw byte pattern: appears in **3 binaries**:
- `cslibu-3-0.dll` ×1 (`.rdata @ 0x3813a750` — the constant we already extracted, used by the default `CSDoc::CSDoc()` ctor).
- `crpe32.dll` ×8 (8 copies in `.rdata`, scattered across distinct `.rdata` regions).
- `craxddrt.dll` ×8 (similar).

Each of the 8 occurrences in `crpe32.dll` is preceded by trailing UTF-16LE bytes from various `.rdata` strings (`...rass`, `...bject`, `...ure`, `...x.cpp`, `...gl`, etc.) and followed by `\x00 * 8` padding. This is the canonical 16-byte default-key constant being baked into multiple `CSDoc`-subclass ctors that each carry their own copy in `.rdata` (one per ctor or one per translation unit).

### Conclusion

The bytes `11dd1896bd4a15cdbff2543503e6760f` are the **product-wide canonical fixed AES key** for `useFixedEncryptionKey=1` mode in CR 13.0.20.2399. This is not a placeholder — it's the actual key. The Round-5 hypothesis that build-specific keys exist is dead.

The fact that decryption with this key still fails means the bug must be in our cipher implementation, **not** in key recovery.

### Outstanding hypothesis

`Rijndael::ProcessBlock` (the implementation behind `Rijndael::vftable[0]`, called by `FUN_380dfac0` to compute the AES block cipher output) very likely **byte-reverses each 4-byte word** on load from the input pointer and on store to the output pointer — a standard optimization for FIPS-AES on little-endian CPUs that interpret the spec's "byte position 0 is MSB of word" convention. This would silently produce a byte-permuted variant relative to PyCryptodome's plain-byte AES.

To verify and compensate, I need to decompile the `Rijndael::ProcessBlock` function (in cslibu) and inspect the byte-load order. The compensation would likely be to byte-reverse each 4-byte word of {key, IV, ciphertext} before feeding to PyCryptodome — but I tried *partial* combinations of this (key alone, key+IV) without success in Round 6, so it may be a more subtle scheme (different state-matrix layout, row-major vs column-major) rather than simple word-byte-reversal.

### Round 8 plan

1. **Switch Ghidra back to `cslibu-3-0.dll` (x86).** Decompile `Rijndael::vftable[0]` (the `ProcessBlock` method) and the surrounding `Rijndael` class. Verify whether byte-reversal-per-word is happening on input load and output store.
2. If yes: compute the byte-reversal-compensated decryption recipe and confirm against samples.
3. If no: the only remaining static-analysis lead is the round operations themselves — verify `MixColumns`, `ShiftRows`, and the state-matrix layout. After that, fall back to live process debugging on Windows.

### Notes on tooling (response to user 2026-05-10)

LaurieWired's GhidraMCP has no DLL load/unload tools — it operates on the program already open in whichever CodeBrowser tool has `GhidraMCPPlugin` enabled (HTTP server bound to port 8080 in that single process). Switching DLLs requires the user to close the current CodeBrowser and open a new one. Alternatives that could fix this for this project:
- `13bm/GhidraMCP` and `bethington/ghidra-mcp` — fork variants that may have programmatic open.
- A custom MCP wrapper around Ghidra's `analyzeHeadless` analyzer — would let the agent import + auto-analyze a DLL on demand.
- `symgraph/GhidrAssistMCP` and `starsong-consulting/GhydraMCP` — third-party MCP servers with broader feature sets.

For this project's small DLL set (cslibu, crpe32, boezlib, plus possibly craxddrt) the manual switching cost is low; not worth swapping MCP server mid-project.

## Round 8 — 2026-05-10: Cipher cracked. Plaintext extracted.

Switched Ghidra back to x86 cslibu and decompiled the actual `Rijndael::ProcessBlock` (vftable[0] of `RijndaelEncryption`). What looked like "standard FIPS-197 AES via T-tables" turned out to be a **byte-permuted variant**: the SubBytes/ShiftRows/MixColumns folded into the T-table lookup uses non-FIPS index positions. The byte-position picks within each round word ARE NOT the standard `(c+0, c+1, c+2, c+3)` diagonal under SubBytes+ShiftRows; they're a different permutation that's self-consistent across the schedule + rounds but produces a cipher that's distinct from PyCryptodome's AES.

### How the divergence shows up

For a single-block encrypt, the first-round computation in `FUN_380dedf0` is:

```
new_word_0 = T2[byte1(s2)] ^ T1[byte2(s1)] ^ T0[byte3(s0)] ^ T3[byte0(s3)] ^ rk[4]
```

Standard FIPS-197 AES (column-major state, T-table optimization) is:

```
new_word_0 = T0[byte0(s0)] ^ T1[byte1(s1)] ^ T2[byte2(s2)] ^ T3[byte3(s3)] ^ rk[4]
```

The byte indices and the T-table assignments are both rotated. Empirical proof: on the same key+IV, PyCryptodome AES gives `9be75eaefde9bee2af69e100a2c93e04`; the cslibu impl gives `66d4ccda34f29584c25131c9cab8406f`. Different ciphers.

### Resolution

Ported the cslibu T-table impl byte-for-byte into Python (`crdis/codec/cslibu_aes.py`). All four T-tables, S-box, and RCON extracted directly from cslibu-3-0.dll `.rdata`. With:

- key = `11dd1896bd4a15cdbff2543503e6760f` (the canonical fixed key from Round 7)
- IV  = `body[16:32] XOR 0xff` (per Round 6 framing)
- ct  = `body[34:]`

CFB-128 decrypt produces a plaintext that begins with `78 5e ...` — **the zlib magic bytes** (CMF=0x78, FLG=0x5e: 32K window, no preset dict, default compression). Round 6's "raw deflate" claim was wrong — the inner codec is **standard zlib (with header), not raw deflate**. We never saw the magic bytes earlier because the decryption was producing random output, so we falsely confirmed zlib-falsifying tests like "no preset dict in `BO_inflateInit2_`" and concluded "raw deflate". With the right cipher in place, plain `zlib.decompressobj(15).decompress(...)` (positive wbits = expect zlib header) inflates cleanly:

- `samples/002_one_label/report.rpt`: 1633 enc bytes → 5758 plaintext bytes
- `samples/001_empty/report.rpt`:    1406 enc bytes → 5163 plaintext bytes

### What the plaintext looks like

The decompressed plaintext is the **inner CSArchive record stream** — same TLV-record format used by the outer `Contents` header, but for the report body. It starts with a record header that mirrors the outer one's shape:

```
outer Contents header (decoded):  fc 00  ff ff  07 00  00 00 00  18  ...value bytes...
inner record stream  (raw):       f8 64  07 00  00 00 00 92      ...
```

The inner stream is *also* XOR-masked with a running per-record mask (large stretches of repeating `64` bytes are masked zeros). This is the next layer to decode; the same `CSRecordArchive` framing rules apply, just one level deeper.

### Falsified hypotheses corrected

- ~~"Inner codec is raw deflate"~~ → falsified. Inner codec is standard zlib (CMF/FLG header + Adler32 trailer).
- ~~"AES is FIPS-197 standard"~~ → falsified. cslibu uses a byte-permuted variant that produces a different cipher than any standard AES library. The variant is self-consistent (encrypt and decrypt sides match) but incompatible with PyCryptodome / OpenSSL / etc.

### Confirmed and stable

- Cipher: AES-128-CFB-128 with **byte-permuted T-table layout** (see `crdis/codec/cslibu_aes.py`).
- Fixed key: `11dd1896bd4a15cdbff2543503e6760f` (CR 13.0.x product-wide constant).
- IV recovery: `body[16:32] XOR 0xff` (header XOR mask is 0xff after the recordTag XOR in startRecord; values are big-endian on disk).
- Inner codec: zlib with header, default compression, 32K window.

### Round 9 plan

1. **Decode the inner CSArchive record stream.** Structurally identical to the outer header (which we now fully understand). Two open questions:
   - Initial XOR mask state for the inner stream — does it inherit the outer's 0xff, reset to 0, or start from somewhere else?
   - Record types and section IDs used inside the body vs. the few we've seen in the header.
2. **Populate `spec/contents.ksy`** with what we now know definitively: the 34-byte outer header (record framing, mask=0xff post-startRecord, big-endian shorts, zlib-encrypted body).
3. **Wire up `crdis decrypt FILE`** as a CLI (`tools/decrypt_sample.py` is the working prototype; promote into the main `crdis` entry points alongside `info`, `dump`, `summary-json`).
4. **CRDiff cross-check oracle** — once we can parse one record type from the inner stream, run `dbatesx/CRDiff` against the same sample on Windows for a JSON oracle to validate against.

## Round 9 — 2026-05-10: Inner CSArchive record stream parsed end-to-end

After Round 8 cracked the encryption, the decompressed plaintext is the report body written through the same `CSRecordArchive` TLV framing as the outer Contents header — just one level deeper. With the writer-side decompiles from Round 6 (`storeStreamHeader`, `store(short)`, `storeBlock`) plus the reader-side ones from this round (`loadStreamHeader`, `loadNextRecordHeader`, `loadTSLVHeader`, `endRecord`), the record format is now fully understood.

### Record format (finalized)

Each record on disk:

```
byte 0..1 : flag word (low byte = flags + 2 high bits of tag)
            bit 7  : wide-length    (with bit 6 → 4-byte length, alone → 2-byte)
            bit 6  : has-length     (with bit 7 → 4-byte, alone → 1-byte)
            bit 5  : section-changed (read 2 more bytes, big-endian-on-disk)
            bit 4  : sets archive+0x50=1 (semantic unconfirmed)
            bit 3  : useSimpleEncryption — XOR running mask by byte(tag)
            bit 2  : extended-tag (read 2 more bytes for the full tag)
            bits 1,0 : if not extended, the high 2 bits of a 10-bit tag
            high byte = low 8 bits of tag (when not extended)
[2 bytes ] : extended tag, big-endian (only if bit 2 set)
[2 bytes ] : section, big-endian (only if bit 5 set)
[0/1/2/4 ] : length, big-endian
[length  ] : value bytes (still XOR-masked by current archive mask)
```

Length width from `(bit7, bit6)`:
| bits | width |
|---|---|
| (0,0) | 0 |
| (0,1) | 1 |
| (1,0) | 2 |
| (1,1) | 4 |

Running XOR mask: `archive[+0x58]`, single byte. `startRecord` does `mask ^= byte(tag)` only when bit 3 was set in the flag word; `endRecord` undoes the same XOR. Multi-byte values written via `store(short)` / `store(long)` are byte-swapped before being passed to `storeBlock`, so they're big-endian on disk. Single-byte `store(uchar)` does no swap.

### Implementation

- `crdis/codec/cs_archive.py` — pure-Python parser (`CSArchiveParser`, `Record`, `dump_records`). Tracks the running mask, decodes the flag-word bit semantics, and optionally recurses into nested records when a value's first byte looks like a non-zero flag word.
- `crdis decrypt FILE` — runs full AES+inflate pipeline, writes plaintext to `FILE.contents.bin`.
- `crdis records FILE` — decrypts, inflates, parses, and dumps records (or histograms with `--summary`).

### Verification

Both samples parse to a complete record sequence with the parser consuming every byte:

| sample | encrypted body | inner plaintext | top-level records |
|---|---|---|---|
| 001_empty (no Text Object) | 1406 B | 5163 B | 126 |
| 002_one_label (one "HELLO") | 1633 B | 5758 B | 138 |

Both share an identical 75-record prefix (the document-wide structures: tag 0x64 root, tag 0x66 sections, tag 0x15f layout, tag 0x16d 16-slot section table, tag 0x6f, then 18× tag 0x78). They diverge at index 75 — sample 002 inserts 12 extra records that constitute the Text Object, after which both sequences re-converge.

### "HELLO" decoded end-to-end

Sample 002, top-level record #80, tag `0x00C2` (194), length 14:

```
00 00 00 06   48 45 4c 4c 4f   00 00 00 00 00
└─ length 6 ┘ H  E  L  L  O    (5 bytes padding)
```

Adjacent record #82, tag `0x0008`, length 27 — the **font binding** for the text object:

```
00 00 00 06  41 72 69 61 6c 00   10 00 01 00 0a 00 00 00 00 00 00 01 90 00 00 00 c8
└─ length 6 ┘ A  r  i  a  l \0    └─ font properties (size, weight, style, etc — TBD) ─┘
```

Both fields use the same 4-byte big-endian length prefix + null-terminated string convention, then a tail of structured properties.

The match between Designer-reported geometry (Left=100, Top=100, Width=1869, Height=221 twips) and bytes inside the Text Object's record family (e.g., 0x100=256 ≠ 100, but `00 00 00 64` = 100 BE shows up several places in the records around #75-80) is consistent but not yet aligned to specific fields — that's a Round-10 task.

### Confirmed and stable

- AES-128-CFB-128 (cslibu byte-permuted T-table variant), key `11dd1896bd4a15cdbff2543503e6760f`, IV = `body[16:32] XOR 0xff`, ciphertext at `body[34:]`.
- Inner codec: zlib with header (`78 5e ...`), default compression, 32K window.
- Inner stream is `CSRecordArchive` TLV records with running per-record XOR mask, big-endian on-disk shorts/longs, 10-bit-or-extended tags.
- `crdis decrypt` and `crdis records` work end-to-end on both sample fixtures.

### Round 10 plan

1. **Map record tags to semantic meaning** by paired-sample diffing. Author samples 003+ that differ by a single controlled change (e.g., add a Line, change Text to Bold, move a field by N twips) and diff the record sequences to identify which tag/value carries which property.
2. **Promote findings into `spec/contents.ksy`** — the 34-byte outer header is fully understood now and ready to encode in Kaitai. The inner record stream is also encodable as a generic `record` type with tag-specific subtypes added as we identify them.
3. **CRDiff cross-check.** Run `dbatesx/CRDiff` (the C# CrystalDecisions wrapper) against samples on Windows, diff its JSON output against ours.
4. **Tighten the recurse heuristic.** Current heuristic skips `flags=0` (was generating spurious zero-tag/zero-length children inside zero-padded value regions). Some legitimate nested records still get dropped if their value happens to start with all zeros; need a stronger signal (e.g. require the parsed children to span the whole value with no leftover bytes).

---

## Round 10 — element-block schemas via paired-sample diffing (2026-05-11)

### New samples and top-level record counts

| sample | description | records | delta vs baseline |
|---|---|---|---|
| 001_empty | baseline, no body elements | 126 | — |
| 002_one_label | + 1 Text Object "HELLO" | 138 | +12 |
| 003_two_labels_hello_world | + 1 Text Object "WORLD" (vs 002) | 150 | +12 |
| 004_two_labels_greetings_someone | rename both strings (vs 003) | 150 | 0 |
| 005_image_in_page_header | + 1 Image in Page Header (vs 004) | 157 | +7 |
| 006_image_in_details | same Image, moved to Details (vs 005) | 157 | 0 |
| 007_image_and_line | + 1 Line (vs 006) | 162 | +5 |
| 008_two_lines_only | 001 + 2 Lines (no text/image) | 136 | +10 = 2×5 |

The two **+12** deltas (single Text Object), **+7** delta (single Image), and the
matched **+5** and **+10 = 2×5** deltas (Line, two Lines) establish a stable
per-element record count: **TextObject = 12 records, Image = 7 records,
Line = 5 records**.

### Element block schemas (record-tag sequences, in stream order)

Status: **supported** by cross-sample agreement.

```
Text Object (12 records):
  [0xA5, 0xBE, 0xFD, 0xED, 0xC0, 0xC2, 0x101, 0x08, 0x102, 0xC3, 0xC1, 0xA6]
                   ^^^^                    ^^^^   ^^^^
                   string                  string font

Image (7 records):
  [0xAF, 0xBE, 0xFD, 0xED, 0x09, 0xBD, 0xB0]

Line (5 records):
  [0xAA, 0xBE, 0xFD, 0xED, 0xAB]
```

Common-prefix pattern: each block opens with an **element-class tag** (0xA5 /
0xAF / 0xAA), then **0xBE** carrying placement, then **0xFD** and **0xED**
(formatting blocks — identical bytes across many elements, suggesting they're
default-property templates), then type-specific records, and a closing
"end-of-element" tag (0xA6 / 0xB0 / 0xAB) with empty value.

### Confirmed field decoders

#### Tag 0xBE — element position (4 bytes)

Layout: `<u2 BE left> <u2 BE top>` (twips). Confirmed across all element classes:

| sample | element | designer (left, top) | 0xBE value bytes |
|---|---|---|---|
| 002 | "HELLO" Text Object  | (100,  100) | `00 64 00 64` |
| 003 | "WORLD" Text Object  | (2055, 100) | `08 07 00 64` |
| 005 | Image (Page Header)  | (2128, 76)  | `08 50 00 4c` |
| 006 | Image (Details)      | (4028, 76)  | `0f bc 00 4c` |
| 007 | Line                 | (1125, 675) | `04 65 02 a3` |
| 008 | Line #1              | (1050, 240) | `04 1a 00 f0` |
| 008 | Line #2              | (1710, 870) | `06 ae 03 66` |

All 8 measurements match Designer-reported twips exactly. **Confirmed.**

Width/height for Text Objects is NOT in 0xBE. For Lines, the endpoint
(right, bottom) is also not in 0xBE — it's most likely in the element-class
tag (0xAA for lines) since that's the only other record whose contents vary
between Line #1 and Line #2 within sample 008. Investigation continues.

#### Tag 0xC2 — text string (variable length)

Layout: `<u4 BE byte-length> <utf8 bytes including 1 NUL terminator> <4 pad bytes>`

The length field is the count of bytes including the trailing NUL — *not*
the character count.

| string | char count | length field | record value len | bytes after header |
|---|---|---|---|---|
| HELLO     | 5 | 6  | 14 | `48 45 4c 4c 4f 00` + 4 pad |
| WORLD     | 5 | 6  | 14 | `57 4f 52 4c 44 00` + 4 pad |
| GREETINGS | 9 | 10 | 18 | `47 52 45 45 54 49 4e 47 53 00` + 4 pad |
| SOMEONE   | 7 | 8  | 16 | `53 4f 4d 45 4f 4e 45 00` + 4 pad |

The 4 trailing zero bytes are consistent across all four observations; they
may be padding or a fixed `u4` "formatting-run count = 0" field. Tentatively
treat as 4-byte padding until contradicted.

**Confirmed** by 4 distinct strings, 2 different lengths, across 3 samples.

### Section binding is positional, not labelled

Sample 006 moves the Image from Page Header to Details. Result: the 7-record
Image block is **byte-identical** to sample 005's, only its position in the
top-level record sequence changes (idx 37 in 005, idx 99 in 006). No "section
binding" field exists inside the element block.

Implication: section assignment is recovered from the element's **index in
the global record stream**, against a section-table elsewhere in the file
(likely the 16-slot 0x16D table at record #5 or the 18× 0x78 records #7-24,
which look like per-section descriptors). Falsifying or confirming this is a
follow-up.

### Records that change in lockstep with element additions

These records' value bytes mutate every time an element is added/removed,
but stay stable for content-only edits — they look like document-wide
counters / size-or-offset tables:

- **Record #0, tag 0x0064** ("document header", len 146). Bytes at
  offsets 0x10-0x14 and 0x28-0x2c update. Offset 0x10 is a counter that
  increments by 3 every time an element is added (`f0` in 001 → `f0` in 002
  → `f3` in 003 → `f3` in 004 → `f3` in 005 → `f3` in 006 → `f3` in 007).
  Offsets 0x13-0x14 and 0x2b-0x2c are 16-bit values that change with every
  edit — likely checksums or offset-into-stream values.
- **Record #72, tag 0x0095** — value bytes at offsets ~0x0a and ~0x0f update
  with element additions. ID/counter-like.
- **Record #34, tag 0x0091** — similar pattern when image/line added in PH.

These are noise for element-decoding purposes; they need their own decode
once we understand more elements.

### "Saved Date" record (always changes — ignore in diffs)

Near the end of every stream is record tag `0x0178` (376), length 62, whose
value contains the literal string `Saved Date` followed by a `2026.05.NN
HH:MM:SS` formatted timestamp. It changes on every save. The diff helper
treats it as noise.

### Tools

`tools/diff_records.py` — aligns two parsed record streams via difflib on
`(tag, length, value)`, prints equal-context-collapsed insert / delete /
replace blocks, and for same-tag replacements emits a compact byte-offset
diff of the value bytes. This is the Round-10 workhorse.

### Open questions

- Width/height for Text Objects (1869, 221 in samples 002-004). Not in
  0xBE; not obviously in 0xC0 (`...01 00 00 00 01 00 00 01...`). Candidate:
  one of 0xA5 / 0xFD / 0xED, but those are large records with masked content.
- Line endpoint (right, bottom). Strong candidate: tag 0xAA (the line-class
  opener), since it's the only line record whose value bytes vary between
  Line#1 and Line#2 in sample 008 (apart from 0xBE).
- Line style (single vs dotted). Within sample 008, tag 0xED differs at one
  byte offset between the two lines (`ed` vs `e8` after the running mask is
  applied — masked deltas 1 vs 4). Hypothesis: 0xED contains an enum byte
  for line style; needs confirming with more styled-line samples.
- Font properties in 0x08 — record tail bytes `10 00 01 00 0a 00 00 00 00 00 00 01 90 00 00 00 c8` after "Arial\0". Hypotheses parked until we have bold / italic / size-change samples.

### Status

Sample inventory expanded from 2 → 8 reports, all parsing byte-perfect to
end. Three element classes (Text Object, Image, Line) have confirmed
record-block schemas. Two record-level field decoders confirmed
(0xBE position, 0xC2 string). Section binding shown to be positional.

### Line endpoint and style — confirmed (2026-05-11)

Within-sample diff of sample 008's two Line blocks (records 75-79 vs 80-84)
pinpointed exactly which bytes encode the variables that differ between
Line#1 (single, 1050,240→5550,240) and Line#2 (dotted, 1710,870→5700,870).

#### Line endpoint (right, bottom): tag 0xAA, nested 0xA9 sub-record

Tag 0xAA's value is a wrapped record: its first 10 bytes parse as a CSArchive
inner header `flags=0xf8, tag=0xa9, section=0x0700, length=0x54 (=84)`. The
84 nested value bytes are XOR-masked by `0xa9` (the inner mask transition).

At inner-value offsets 78..81 (i.e. outer-0xAA value offsets 88..91), as a
pair of BE `u2`:

| line | bytes after `^ 0xa9` | decoded (right, bottom) | notes.md |
|---|---|---|---|
| sample 008, line#1 | `15 ae 00 f0` | (5550, 240) | matches ground truth ✓ |
| sample 008, line#2 | `16 44 03 66` | (5700, 870) | matches ground truth ✓ |
| sample 007, line   | `15 cd 02 a3` | (5565, 675) — see note* | notes give (5325, 675); off by 240 twips on `right` |

\*Re-check: sample 007's notes say `right=5325` but the decoded byte gives
5565. Possible explanations: (a) Designer reports the bounding-box right
edge differently than the stored endpoint, (b) the notes are off by a
quarter-inch, or (c) the line is slightly different to what was recorded.
The two sample 008 lines (where notes were taken right after authoring)
agree exactly, so the **(right, bottom) at 0xAA inner offset 78..81 BE u2**
identification is solid; sample 007 is to be re-measured.

**Confirmed:** `0xBE = (left, top)` and `0xAA-inner[78..81] = (right, bottom)`
together fully encode a Line's geometry as two BE u16 pairs.

#### Line style enum: tag 0xED, nested 0xEC sub-record, inner offset 0

Tag 0xED's value also wraps a nested record: header `flags=0xf8, tag=0xec,
section=0x0700, length=0x22 (=34)`, inner mask flips by `0xec`. At inner
offset 0:

| line                       | byte (post `^ 0xec`) | CR `LineStyle` enum value |
|---|---|---|
| sample 008 line#1 (single) | `0x01`               | `crLineStyleSingle = 1` ✓ |
| sample 008 line#2 (dotted) | `0x04`               | `crLineStyleDotted = 4` ✓ |
| sample 007 line (default)  | `0x01`               | `crLineStyleSingle = 1` (default) |

Exact match against Crystal Reports' published constants
(`None=0, Single=1, Double=2, Dashed=3, Dotted=4`). **Confirmed** for values
1 and 4; the remaining three are a one-sample-each verification away
(see "Next-pass sample requests" below).

#### Possible line-thickness byte (hypothesis)

In the same nested 0xEC sub-record, byte at inner offset 19 is `0x14` (=20)
for line#1 (single) and `0x00` for line#2 (dotted) of sample 008. Twenty
twips = 1/72 inch = the default thin line weight; zero may be a "no
thickness applies" marker for dotted. This is a hypothesis — confirming
needs a paired sample where only thickness varies (e.g. 2pt single vs 1pt
single, holding style constant).

#### Per-element ID byte (parking)

At outer-0xAA value offset 41 (= inner-0xA9 value offset 31, post `^ 0xa9`),
byte reads `0xAF` for line#1 and `0xAC` for line#2 — looks like a per-element
allocation counter, not a style attribute. Noted, not promoted.

### Next-pass sample requests

To lock the remaining open questions, the next batch of Designer-authored
paired samples should isolate, one variable at a time:

1. **Line-style enum, full coverage.** One report containing one line each
   of styles None / Double / Dashed (the three not yet observed); the
   single / dotted endpoints are already confirmed.
2. **Line thickness independent of style.** Two single-style lines, one at
   1pt, one at 2pt (or any two distinct thicknesses). Confirms the offset-19
   hypothesis and gives the units (twips? half-points?).
3. **Text Object width/height.** One sample with a single Text Object at a
   distinctive width (e.g. 3000 twips wide × 500 tall) so the four bytes
   `0x0B B8 0x01 F4` are easy to spot in 0xA5 / 0xFD / 0xED candidates.
4. **Text bold/italic/size.** Three single-Text-Object samples differing
   from sample 002 by exactly one font property (bold, italic, size=14pt).
   Decodes the tail of 0x08.
5. **Cross-check sample 007's line `right` coordinate.** The current notes
   give 5325 but the file decodes to 5565 — either re-measure in Designer
   or accept the file value.

### Element block has three levels of nesting (2026-05-11, late session)

Once the parser was reworked to model wrapper records as "one nested record +
raw tail" (see `crdis.codec.cs_archive.Record.tail`), a Line block decoded to a
**three-level chain**, not two:

```
0xAA (outer, 94 B value)
  └─ 0xA9 (inner, 84 B value)        — line geometry container
       └─ 0x9E (innermost, 68 B value) — element metadata (width + name)
       └─ tail (8 B) → (right, bottom) endpoint
  └─ tail (2 B) → constant `00 01`
```

Same pattern for `0xED` (line-style container):

```
0xED (130 B value)
  └─ 0xEC (34 B value)               — line style enum + thickness
  └─ tail (88 B) → 11× `00 00 00 01 00 00 ff ff` default entries
```

And `0xFD` (formatting template):

```
0xFD (165 B value)
  └─ 0xFC (45 B value)               — default-formatting payload (not decoded)
  └─ tail (112 B) → 14× `00 00 00 01 00 00 ff ff` default entries
```

The recurring `00 00 00 01 00 00 ff ff` pattern in both 0xED and 0xFD tails
strongly suggests this is a **fixed-format default-properties table** shared
across element kinds, populated by Designer when a new element is dropped in.

### Element name lives in the innermost (0x9E) record

The 0x9E record's value contains the Designer-authored element name as a
4-byte-BE-length + UTF-8 + NUL Pascal-style string (same convention as 0xC2):

| sample 008 line | 0x9E[20:30] hex                | decoded name |
|---|---|---|
| Line#1 | `00 00 00 06 4c 69 6e 65 31 00` | "Line1\0"    |
| Line#2 | `00 00 00 06 4c 69 6e 65 32 00` | "Line2\0"    |

The leading 4 bytes of 0x9E.value are the element's bounding-box **width**
(u4 BE, twips): Line#1 = 0x00001194 = 4500 ✓, Line#2 = 0x00000f96 = 3990 ✓
— matching (right - left) for each.

### Line endpoint location, refined

Earlier I reported "0xAA value offset 88..91 = (right, bottom)". With proper
recursive parsing that's actually the **tail of the 0xA9 child**, at offsets
2..6 — i.e. after the inner 0x9E record's 78 bytes (10 B inner header + 68 B
inner value) and after a 2-byte `00 02` marker. Same bytes, cleaner structural
description.

### Updated Line element schema summary

| record | tag    | value bytes | nesting + key fields                                         |
|--------|--------|-------------|--------------------------------------------------------------|
| 0      | 0xAA   | 94          | wraps 0xA9 + 2-B tail `00 01` (constant)                     |
| 0.0    | 0xA9   | 84          | wraps 0x9E + 8-B tail = `00 02 <right u2 BE> <bottom u2 BE> 00 00` |
| 0.0.0  | 0x9E   | 68          | `[0:4]` = width (u4 BE), `[20:24]` = name length (u4 BE), then UTF-8+NUL |
| 1      | 0xBE   | 4           | `(left u2 BE, top u2 BE)` — element placement                 |
| 2      | 0xFD   | 165         | wraps 0xFC (45 B not decoded) + 112-B default-table tail     |
| 3      | 0xED   | 130         | wraps 0xEC (style + thickness) + 88-B default-table tail     |
| 3.0    | 0xEC   | 34          | byte `[2]` = LineStyle enum, `[18:22]` u4 BE = thickness (twips) |
| 4      | 0xAB   | 0           | end-of-element terminator (empty)                            |

### Tooling changes (this same session)

- `Record.tail` field added to `cs_archive.py`.
- `parse_record(recurse=True)` now parses exactly **one** nested record from
  the value and captures the remainder as `tail`. The previous "parse-as-many-
  as-fit" approach generated spurious zero-tag children inside trailing data
  and rejected legitimate single-nested records when trailing data didn't
  EOF cleanly. The new model matches every nested-record case we have observed.
- `tools/diff_records.py` auto-descends one level when both sides of a same-
  tag replacement carry a same-tag single child — inner-field deltas now
  surface in the diff output directly (no more manual XOR step).
- `spec/elements/line.ksy` encodes the full Line block — see file for full
  typed layout including the `line_style` enum.

### Round 10 (cont.) — 2026-05-12: regression test suite landed

Status: **closed** (paused work from 2026-05-11 finished). Commit `487f937`.

Three pytest modules under `tests/` now lock every Round 10 finding:

- `tests/test_golden.py` — 8 samples × {raw Contents sha256, inflated
  plaintext sha256, top-level record count, concatenated `record.value`
  sha256}. Any drift in the AES port or the CSArchive parser flips at
  least one of 32 assertions.
- `tests/test_decoders.py` — encodes the ground truth from each sample's
  `notes.md`: 001 has no element-class records; 002/003/004 0xC2 strings
  match Designer text; 007/008 Lines decode to the stated name, width,
  left/top from 0xBE, right/bottom from `0xA9.tail[2:4] / [4:6]`,
  LineStyle from `0xEC.value[2]`, thickness from `0xEC.value[18:22]`.
- `tests/test_aes_vector.py` — hardcoded `(KEY, IV, ct[:32]) -> pt[:32]`
  derived from sample 001. Guards against accidental PyCryptodome
  substitution for the cslibu byte-permuted AES.

44/44 pass in ~0.04 s. Run with `pytest -q tests/` after
`pip install -e '.[dev]'`.

**Sample 007 `right` discrepancy — resolved.** The earlier session noted
sample 007's line decoded to `right=5565` while notes said `5325`. With
the current "one nested record + tail" parser, `0xA9.tail[2:4] = 14 cd
= 5325`, exactly matching notes. The original `15 cd → 5565` reading
was a one-byte-misaligned slice of the same region. No re-measurement
needed; the previous "Re-measure sample 007" item in the next-pass list
has been dropped.
