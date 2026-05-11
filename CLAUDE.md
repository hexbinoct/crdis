# crdis — guidance for Claude Code

This project is a clean-room reverse-engineering effort to parse Crystal
Reports `.rpt` files (CRforVS 13.x generation, files made by Visual Studio
2010–2019). See `README.md` for the high-level pitch and `research/format_notes.md`
for the running RE notebook.

## TL;DR for a fresh session

If you are reading this on a new machine or after a long gap, read **in this order**:

1. The "RESUME HERE" section below (in this file). It tells you where we are
   today and what the next step is.
2. `research/format_notes.md` — every confirmed/falsified hypothesis with
   evidence, round by round (Round 9 = current bottom-of-log).
3. `research/reverse_engineering_journey.md` — narrative commentary on how
   we got here, including the cognitive errors we made and the moves that
   unlocked things. Read this if you want to *understand* the reasoning,
   not just the facts.
4. `samples/README.md` — sample naming convention.

Then ask the user where they left off if it isn't obvious from RESUME HERE.

## Hard constraints

- **No proprietary deps in the deliverable.** Never propose Crystal Reports
  runtime, COM/OLE Automation, SAP RAS SDK, `rpt-to-xml`, or any Windows-only
  component as a solution path. The point is to be free of them. Static or
  dynamic analysis of `crpe32.dll` is fine — that's clean-room interop RE; the
  output is a from-scratch parser, not a wrapper.
- **Cross-platform.** Code in `crdis/` must run on Windows, Linux, macOS.
- **Spec-first.** The canonical output of this project is the Kaitai Struct
  spec under `spec/` (currently empty — populated as findings get confirmed).
  Python code in `crdis/` is a reference parser that consumes the spec, not the
  other way around.

## Working method

1. User authors paired `.rpt` files in CRforVS Designer (Windows-only) that
   differ by one controlled change. Files + ground-truth notes go under
   `samples/NNN_*/`.
2. We binary-diff the pair, form structural hypotheses, log them in
   `research/format_notes.md` with date, sample(s), evidence, status
   (`hypothesis` / `supported` / `confirmed` / `falsified`).
3. Confirmed structure is encoded in `spec/*.ksy`.
4. Reference parser exposes findings via `crdis` CLI / library.

## RESUME HERE (2026-05-11 handoff — Round 10 in progress)

**TL;DR for the next Claude session.** The encryption is fully cracked.
Sample set has grown from 2 → 8 reports (all parse byte-perfect). Three
element classes have confirmed record-block schemas and several fields
inside them are decoded. Next pass needs a new batch of Designer-authored
samples (see "Next-pass sample requests" at the bottom of
`research/format_notes.md`). Read this section, then Round 9 + Round 10
sections of `research/format_notes.md`, then
`research/reverse_engineering_journey.md` for narrative.

### Round 10 progress so far (samples 003..008 added 2026-05-11)

- **Element block schemas (confirmed by record-count arithmetic):**
  - Text Object = 12 records, `[A5, BE, FD, ED, C0, C2, 101, 08, 102, C3, C1, A6]`
  - Image       = 7  records, `[AF, BE, FD, ED, 09, BD, B0]`
  - Line        = 5  records, `[AA, BE, FD, ED, AB]`
- **Field decoders confirmed:**
  - `0xBE` = `<u2 BE left> <u2 BE top>` (twips). 8 measurements, all match Designer.
  - `0xC2` = `<u4 BE byte-length> <utf8+NUL> <4 zero pad>`. Length counts the NUL.
  - `0xAA` inner (nested 0xA9 record, mask ^= 0xa9), offsets 78..81 = `<u2 BE right> <u2 BE bottom>` for Lines.
  - `0xED` inner (nested 0xEC record, mask ^= 0xec), offset 0 = LineStyle enum (1=single, 4=dotted confirmed).
- **Structural:** section binding is **positional** (sample 006's image
  block is byte-identical to 005's; only its index in the global record
  sequence changes). No section tag inside the element block.
- **Spec:** `spec/contents.ksy` now encodes the 34-byte outer Contents-stream
  TLV header (10-byte CSArchive header + 24-byte XOR(0xff)-masked value
  region containing 6 framing + 16 IV + 2 framing bytes). All 11 asserted
  `contents:` constants verified byte-identical across all 8 samples.
- **Tooling:** `tools/diff_records.py` aligns two parsed record streams
  with difflib on `(tag, length, value)` and prints byte-level value diffs
  for same-tag replacements. This is the Round-10 workhorse.

### What's working as of the handoff

```bash
crdis info FILE          # stream inventory + summary properties
crdis dump FILE -o DIR   # extract every stream as .bin
crdis summary-json FILE  # parsed summary as JSON
crdis decrypt FILE       # NEW: decrypt + zlib-inflate the Contents stream
crdis records FILE       # NEW: decrypt, inflate, parse the inner CSArchive records
                         #      flags: --summary, --recurse, --limit N
```

Both samples parse to byte-perfect completion:

| sample | encrypted body | inflated plaintext | top-level records |
|---|---|---|---|
| `samples/001_empty/report.rpt` | 1406 B | 5163 B | 126 |
| `samples/002_one_label/report.rpt` | 1633 B | 5758 B | 138 |

The 12-record delta between the samples is the records that encode the
"HELLO" Text Object in sample 002. Sample 002's record #80 (tag 0xC2)
contains the literal `00 00 00 06 H E L L O 00 00 00 00 00`; record #82
(tag 0x08) contains the font binding (`00 00 00 06 A r i a l 00 ...`).

### The decode pipeline (everything below is confirmed)

```
.rpt (CFB) → "Contents" stream
            → 34-byte TSLV header (mask=0xff, big-endian shorts/longs,
                                   16-byte IV at body[16:32] XOR 0xff)
            → AES-128-CFB-128, **non-FIPS variant** (cslibu byte-permuted
                                                     T-table impl;
                                                     PyCryptodome will NOT match)
              key = 11dd1896bd4a15cdbff2543503e6760f  (CR-13 product-wide)
            → zlib WITH header (78 5e ...; default compression, 32K window)
            → CSArchive TLV record stream (running per-record XOR mask,
                                           10-bit-or-extended tags, BE shorts/longs)
```

Implementation: `crdis/codec/cslibu_aes.py` (AES port) + `crdis/codec/cs_archive.py` (record parser).

### Critical pitfalls (don't re-fall into these)

- **AES is non-FIPS.** Tables and key schedule look standard, but the
  byte-position picks in the round function differ from FIPS-AES. Standard
  `Crypto.Cipher.AES` will not match cslibu's cipher. Use
  `crdis.codec.cslibu_aes` — never re-derive from PyCryptodome.
- **Inner codec is zlib WITH header**, not raw deflate.
  `zlib.decompressobj(15)` (positive wbits) — not `-15`. An earlier round
  concluded "raw deflate" because `BO_inflateInit2_` doesn't call
  `inflateSetDictionary`. That negative finding is true but the
  "raw deflate" inference from it is wrong.
- **Header values are big-endian.** `store(unsigned short)` and `store(long)`
  byte-swap before `storeBlock`. `store(uchar)` does not.
- **Running XOR mask is 0xff, not 0xfe.** Earlier (Round 4) "mask=0xfe with
  little-endian" decoded the 6 value-shorts identically and survived for
  rounds; it was algebraically equivalent to "mask=0xff, big-endian" on
  those 6 bytes only.
- **`useFixedEncryptionKey=1` does not gate the key choice in any code
  path.** The key in `CSDoc + 0x12a` is set only by the default ctor (from
  `cslibu-3-0.dll` `.rdata` at VA `0x3813a750`) and never overridden — we
  searched all 2,236 DLLs in the SAP BO 4.0 install tree for callers of
  `setEncryptionKey` and found zero. The key is replicated 8× in
  `crpe32.dll` and 8× in `craxddrt.dll`, confirming it as a CR-13
  product-wide canonical.

### Round 10 plan — next pass

1. **Author the requested next-pass samples** (in CR Designer on Windows).
   Full list with rationale in the "Next-pass sample requests" section at
   the bottom of `research/format_notes.md`. In priority order:
   - One line each of style None / Double / Dashed (locks the remaining
     three LineStyle enum values).
   - Two single-style lines at different thicknesses (confirms the
     thickness hypothesis at inner-0xEC offset 19, and gives units).
   - One Text Object at a distinctive non-default width × height (decodes
     Text-Object geometry — currently unknown which of 0xA5/0xFD/0xED holds it).
   - Three single-Text-Object samples differing by bold / italic / size=14pt
     (decodes the property tail of font record 0x08).
   - Re-measure sample 007's line `right` coordinate (file says 5565, notes
     say 5325 — one of them is wrong).
2. **Drop new samples into `samples/NNN_*/`** with `notes.md` per template.
3. **Diff with `tools/diff_records.py`** against the closest existing
   sibling, append findings to `research/format_notes.md` as
   "Round 10 (cont.) — <date>".
4. **Promote any newly confirmed field decoders** into `spec/contents.ksy`
   (currently only the outer 34-byte header is encoded; element-block
   types are next).
5. **Optional but high-leverage:** wire up `dbatesx/CRDiff` (Windows-only
   C# `CrystalDecisions` wrapper) as an external JSON oracle for
   regression diffs once any single element class is fully decoded.

### Files to know about

```
crdis/codec/cslibu_aes.py     # The byte-permuted AES port — re-extracts T-tables
                                 from research/runtime_dlls/cslibu-3-0.dll at module
                                 load. Don't replace with PyCryptodome.
crdis/codec/cs_archive.py     # Inner record parser. Tracks running XOR mask,
                                 decodes the 10-bit-or-extended tag scheme,
                                 BE shorts/longs, four length-width encodings.
crdis/cli.py                  # All five subcommands: info / dump / summary-json
                                 / decrypt / records.
research/format_notes.md      # Structured RE log — find facts/evidence here.
research/reverse_engineering_journey.md   # Narrative — find "why we did X" here.
research/runtime_dlls/        # All CR DLLs (x86 + x64) including the full SAP
                                 BO 4.0 win32_x86 install tree (2236 DLLs).
                                 Identity: cslibu-3-0.dll and crpe32_x86.dll
                                 in the top dir are byte-identical to the SAP BO
                                 copies (sha256 verified).
```

### Tooling state

- Ghidra + GhidraMCP (LaurieWired) is operational. HTTP server on
  `localhost:8080`. The plugin is bound to whichever CodeBrowser has it
  enabled — to switch which DLL is loaded, the user has to close one and
  open another. There's no programmatic open in Lauri's MCP. Workable; the
  switch costs ~30 seconds.
- For Round 10 work, we'll mostly be in `cs_archive.py` and Designer-side
  sample authoring; Ghidra is only needed when a record's value layout is
  ambiguous and we need the writer-side `storeXxx` decompile to see what
  fields are written in what order.

### Recovered constants (do not lose these)

- **AES-128 key:** `11dd1896bd4a15cdbff2543503e6760f`
  At `cslibu-3-0.dll` x86 `.rdata` VA `0x3813a750`, also replicated 8× each
  in `crpe32.dll` and `craxddrt.dll`. CR-13 product-wide canonical.
- **Header running-XOR mask:** `0xff` (NOT 0xfe — see "Critical pitfalls").
  Initial archive mask = 0; `startRecord` does `mask ^= byte(recordTag)` if
  `useSimpleEncryption` is set in the flag word.
- **Header byte at offset 9:** `0x18` = 24 = number of value bytes in the
  outer Contents-stream record. Used as the length-field of a 4-byte-length
  TLV record.
- **Codec chunk constant:** `0xfc00` = 63 KiB = `CSZFileBufferCompressor`
  buffer size.
- **Cipher:** non-FIPS byte-permuted AES-128 (cslibu T-table impl).
  Re-extract tables with `crdis.codec.cslibu_aes._load_tables_from_dll`.

---

## Container facts (still valid — public format)

- **Container is OLE Compound File Binary (CFB / `MS-CFB`).** Magic
  `D0 CF 11 E0 A1 B1 1A E1`. We use `olefile`.
- **5 streams:** `\x05SummaryInformation`, `Contents`, `CrystalReportDesignerStream`,
  `QESession`, `ReportInfo`.
- **`Contents`** holds the report definition; layout decoded above.
- **`SummaryInformation`** is a standard MS Office property set; already parsed
  by `crdis info` / `crdis summary-json`.
- **`QESession`** is per-save random session GUID/salt. Ignored.
- **`CrystalReportDesignerStream`** (114 B) and **`ReportInfo`** (58 B) are
  byte-identical across our two-sample pair — small static metadata, no
  decode yet (and probably not interesting until the report-body parser is
  done).

Sample 002 has a Text Object "HELLO" in Details at Designer-reported geometry
Left=100, Top=100, Width=1869, Height=221 (twips). Sample 001 is empty (no
fields). Used as canonical paired fixture.

### Cross-platform parity check

`tools/verify_baseline.py` compares stream sha256 hashes and the parsed
summary-property JSON of both sample files against a baseline captured on
Windows on 2026-05-08 (CRforVS 13.0.20.2399). Run this if a new environment
might have changed the toolchain; exit 0 + "PASS" = move on, exit 1 + "FAIL"
= investigate before continuing.

```
research/windows_baseline_001_empty.txt
research/windows_baseline_001_summary.json
research/windows_baseline_002_one_label.txt
research/windows_baseline_002_summary.json
```

## When making changes

- New finding? Append to `research/format_notes.md` with date, sample(s),
  hypothesis, evidence, status.
- Promoting a hypothesis to "confirmed"? It belongs in `spec/*.ksy`, not
  hand-rolled in Python.
- Don't add sample fixtures without a corresponding `notes.md` ground-truth
  file — a sample without ground truth is useless for verification.
- Avoid Windows-specific paths in code. Use `pathlib.Path` everywhere.

## Memory (Windows-only — does not travel)

The Windows session has memory entries under
`C:\Users\ab\.claude\projects\F--ru-myprojects-may-crdis\memory\` covering:
project goal, no-proprietary-deps rule, Contents-stream-encrypted finding.
Those won't be visible on macOS — this `CLAUDE.md` is the canonical
hand-off. If you're on macOS and want to seed equivalent memories on this
machine, the source material is in `research/format_notes.md`.
