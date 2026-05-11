# Reverse-engineering the Crystal Reports Contents stream — a narrative

This document is the *commentary track* for the work in `format_notes.md`. The
notes file logs structured findings round by round. This file logs the thinking
behind those findings: what looked promising, what turned out to be wrong and
why, what solidified the path forward, and what cognitive errors slowed us
down. Read it if you want to understand how we got from "encrypted Contents
stream, no idea what cipher" to "complete decoder, every byte accounted for."

It's also a forward-looking document — when we start on Round 10 (mapping
record tags to semantics), the same patterns of error and recovery will show
up, and remembering them will save us time.

---

## The starting picture

When we picked up the project on macOS, here's what we knew:

- The container is OLE2 (CFB) — fully public, parseable with `olefile`. Not
  the prize.
- The interesting stream is `Contents`. Its first 16 bytes are stable across
  samples (`fc 00 ff ff 07 00 00 00 00 18 ff fe fe ff ff fe`), but the rest is
  high-entropy. Single-byte XOR ruled out, repeating XOR ≤ 8 bytes ruled out.
- A previous session on Windows had captured exactly two samples and a few
  baseline tests. No prior round had identified the cipher.
- We had `crpe32_x86.dll` (the print engine, file-version `13.0.20.2399`) and
  later got `cslibu-3-0.dll` (the CSLib-300 archive layer) and `boezlib.dll`
  (the BO fork of zlib). Ghidra + GhidraMCP was set up.

The whole project hinges on this stream. Without decoding `Contents`, every
other ambition — Kaitai spec, Python parser, CLI tools — is parked.

---

## Phase 1: looking for the encryption hook

### What we did

Searched cslibu for any encryption-related function names and strings. Found
them quickly: `setEncryptionKey`, `getEncryptionKey`, `getEncryptionIV`,
`useFixedEncryptionKey`, `setUseSimpleEncryption`, plus RTTI type names
`Rijndael`, `RijndaelEncryption`, `RijndaelDecryption`, and the assertion
strings `cfbEncryption != NULL` / `cfbDecryption != NULL`.

### What this told us (and what it should have told us)

**It told us:** the cipher is Rijndael in CFB mode. That much is obvious from
the strings.

**It should have told us, but didn't until much later:** the class is named
`Rijndael`, not `AES`. In 2026, "Rijndael" and "AES" are usually
interchangeable, but the AES standard is a *specific subset* of Rijndael (only
128-bit blocks; specific byte-to-state mapping). The class name was a clue
that this might be Rijndael-the-original (which permits other block sizes and
which historically had byte-ordering ambiguities in implementations) rather
than FIPS-AES.

We didn't take this clue seriously at first. It cost us about three rounds.

### What worked

Decompiling the cipher constructor showed:

```c
*(int *)(this + 4) = 0x10;        // block size = 16
if (param_3 == 0) param_3 = 0x10; // segment size = 16 (CFB-128)
```

Two facts nailed down: 128-bit block, full-block CFB feedback. Combined with
the RTTI strings, we had a confident "AES-128-CFB-128" hypothesis. Wrong, as
it turned out, but useful as a starting point.

---

## Phase 2: finding the key

### What we did

The default `CSDoc::CSDoc()` constructor at cslibu+0x49780 has a 16-byte copy
loop from `.rdata`:

```asm
38049cc0  MOV AL, byte ptr [EDI + 0x3813a750]
          MOV byte ptr [ESI + EDI + 0x12a], AL
          ...loops 16 iterations...
```

Dumping bytes at VA 0x3813a750: `11 dd 18 96 bd 4a 15 cd bf f2 54 35 03 e6 76 0f`.

We assumed this was the AES key.

### Why decryption then failed (the trap we fell into)

For five rounds, we had:

- A correct cipher hypothesis (AES-128-CFB-128 — close enough)
- A correct key (these 16 bytes — really)
- A correct IV recipe (eventually, after Round 6 corrections)
- A correct ciphertext offset (`body[34:]`)

And the decrypt produced **random output**.

When you have all four ingredients right but the output is wrong, the only
remaining variable is the cipher itself. **We did not seriously consider that
the cipher might not be FIPS-AES until Round 8.** That was the single biggest
mistake of the project.

### What we tried instead, and why each one failed

| Hypothesis | Why we believed it | Why it was wrong |
|---|---|---|
| The key is build-specific; we have an x64 cslibu, samples are x86 | DLLs come in arch-paired builds; reasonable that crypto consts vary | x86 cslibu has the *exact same* 16 bytes at the analogous address |
| `setEncryptionKey` is called from another DLL with the real key | `setEncryptionKey` is exported, must be there for someone | grep-of-mangled-symbol across all 2,236 DLLs in SAP BO 4.0: zero callers |
| The 16 bytes are a placeholder and the real key is generated at runtime | Plausible defense-in-depth pattern | The 8× replication of the same constant across `crpe32.dll`, `craxddrt.dll`, and cslibu killed it: it's clearly a product-wide canonical |
| Mask was 0xfe (Round 4 conclusion that we kept) | XOR'ing the 6 value-shorts with 0xfe gave plausible values | Round 6: actually 0xff with big-endian shorts gives the same plausible values; Round 4's "0xfe + LE" was algebraically equivalent for those 6 bytes only |
| Inner codec is raw deflate, no preset dict | Read `BO_inflateInit2_` carefully; no `inflateSetDictionary` calls | True in negative form (no preset dict), false in positive form: it's zlib *with header*, not raw deflate. We confused "no preset dict" with "raw deflate" — they are independent |

That last one is worth dwelling on. The fact that `BO_inflateInit2_` doesn't
call `inflateSetDictionary` was *real* and *correct*. We just stretched the
inference too far. The codec uses `windowBits=15` (positive = expect zlib
header). We had assumed `-15` (raw deflate, no header). The static-analysis
finding ("no preset dict") was correct; the conclusion drawn from it ("raw
deflate") was a leap.

### The lesson

When all your obvious variables are right and the output is still wrong,
consider that one of your *assumptions* about the obvious variables is wrong —
not just the variables themselves. We kept asking "is the key wrong?" and
"is the IV wrong?" instead of "is the cipher itself wrong?"

This is the hardest kind of bug because the framework you used to verify your
assumptions is the same framework that's broken. PyCryptodome isn't going to
tell you "you've used the wrong AES implementation"; it'll happily decrypt
with FIPS-AES and produce garbage, and you'll keep fiddling with key/IV
permutations.

---

## Phase 3: the framing fix-ups (Round 6)

### What we did

Re-decompiled `storeStreamHeader` and the `store(...)` overloads carefully —
not just skimming for shape, but reading byte by byte. Two fix-ups dropped:

1. `store(unsigned short)` and `store(long)` byte-swap before `storeBlock`. So
   multi-byte values are **big-endian on disk**.
2. `CSRecordArchive` ctor sets the running XOR mask to **0**, not 0xfe.
   `startRecord` updates it as `mask ^= byte(recordTag)` only when
   `useSimpleEncryption` is set. For the stream-header record (`recordTag =
   0xffff`), the mask transitions `0 → 0xff` after startRecord's own writes
   are out, before the value-byte stores begin.

Re-decoding header bytes 10..15 (`ff fe fe ff ff fe`) with mask=0xff and
big-endian gave clean `0x0001, 0x0100, 0x0001` (`isEncrypted=1,
encryptionVersion=0x0100, useFixedEncryptionKey=1`). Matches Round 4's values
but with a structurally correct framing.

### Why Round 4's wrong answer looked right

Round 4 said: mask = 0xfe, little-endian.
Round 6 said: mask = 0xff, big-endian.

Both decode the 6 value-bytes the same way:

```
byte 10: 0xff ^ 0xfe = 0x01    (Round 4 "low byte of LE 0x0001")
byte 10: 0xff ^ 0xff = 0x00    (Round 6 "high byte of BE 0x0001")
```

The byte-swap and the mask change are both single-byte transforms that, on
this particular set of 6 bytes, happen to map to the same on-disk pattern.
We got lucky — and unlucky, because confirming Round 4 made us trust it
without checking the IV bytes (which would have caught the discrepancy: the
IV is per-byte raw, not byte-swapped, so the mask matters more there).

### The lesson

Confirmation bias on coincidentally-correct decoding is real. If you have N
bytes and your decode is consistent with all N bytes, that's evidence for
the framing — but only weak evidence if N is small and your transformation
has only N*log(N) degrees of freedom. We had 6 bytes and 2 binary parameters
(mask choice, endian); 6 bytes is barely enough to constrain 2 parameters
unambiguously.

When validating a framing hypothesis, write down "what *additional* bytes
would this predict" and check those, not just the bytes you derived the
hypothesis from.

---

## Phase 4: the cipher actually being non-FIPS (Round 8 — the breakthrough)

### What unlocked it

Two things in sequence:

1. **The user's nudge to look outside.** We'd been stuck in a static-analysis
   loop for several rounds. The user said "go browse the internet, get a
   second perspective." The web search itself didn't find anything (no public
   RE of CR encryption exists), but the *act of switching context* and asking
   "what's the simplest hypothesis we haven't tested" surfaced one we'd been
   avoiding: maybe the cipher itself is wrong.

2. **Decompiling `Rijndael::ProcessBlock` and just *reading* it.** Until that
   point, we'd looked at the cipher constructor, the CFB wrapper, and the key
   schedule — but not the actual block encryption. When we did, it was a
   T-table AES variant, but with non-FIPS byte-position picks:

   ```c
   // cslibu first-round word 0:
   new_word_0 = T2[byte1(s2)] ^ T1[byte2(s1)] ^ T0[byte3(s0)] ^ T3[byte0(s3)] ^ rk[4]

   // standard FIPS-AES first-round word 0:
   new_word_0 = T0[byte0(s0)] ^ T1[byte1(s1)] ^ T2[byte2(s2)] ^ T3[byte3(s3)] ^ rk[4]
   ```

   The byte indices and the T-table assignments are both rotated. This is
   *not* AES.

### The smoking gun

Once we had the cipher logic in front of us, the test was trivial: emulate
cslibu's `ProcessBlock` in Python from the extracted T-tables and call it on
`(key, IV)`. Compare with PyCryptodome's `AES.new(key).encrypt(IV)`. They
produced different output. Same key, same IV, different ciphers.

Then run a single-block CFB decrypt with the cslibu impl on the real
ciphertext. The first plaintext byte was **`0x78`** — the zlib magic byte.
Second byte `0x5e` — zlib FLG with default compression. The whole project
unblocked in about 90 seconds once that emulator was working.

### The lesson

Reading the cipher's actual block function is mandatory when the obvious
recipe doesn't work. The constructor and the wrapping mode (CFB) tell you
*structure* but not *correctness*. Two ciphers can share a constructor, an
IV size, a CFB feedback pattern, and a key length while still producing
different output for the same input — because the difference is in the
internal byte-to-state mapping that lives only in the per-block function.

The other lesson: when you *port* an algorithm rather than *use* an existing
library implementation of it, the port is hostage to your understanding. We
got lucky that we had GhidraMCP and could just transliterate the decompile
into Python. If the impl had been in obfuscated assembly, the same approach
would still work but cost much more time.

---

## Phase 5: parsing the inner stream (Round 9)

### Why this was easy compared to everything before it

Once the AES + zlib layers came off, the inner stream is **the same
`CSRecordArchive` format** as the outer Contents header. We already had:

- The full byte-level decompile of `loadTSLVHeader`, `loadNextRecordHeader`,
  `endRecord`, and the bit-mask constants at `0x381d7000..7`
- A working understanding of the running XOR mask, big-endian shorts/longs,
  10-bit-or-extended tags, and the four length-width encodings

Writing the parser took an hour. It walked both samples to byte-perfect
completion on the first try (138 records in 002, 126 in 001). Sample 002's
record #80 contained the literal "HELLO" string, which is the document's
ground truth.

### The compounding effect

This is a pattern worth noting. Each round of work on the *cipher layer*
felt like grinding because the validator was unforgiving — either the
plaintext inflated or it didn't. There was no partial credit. But the
*record-stream layer* was relatively quick to parse because each tag could
be decoded independently and the parser could checkpoint progress
("consumed 2138/5163 bytes, 47 records so far"). Different parts of an RE
project have different feedback loops. It's worth recognizing which kind
you're in, because the feedback loop dictates what kind of debugging works.

For the cipher: tiny tests, lots of permutations, frequent emulator
comparisons, hypothesis-driven A/B.

For the record stream: write parser once, run it on the whole thing, look
at the output, fix the heuristic, run it again.

---

## Tools and techniques that paid off

- **Ghidra + GhidraMCP** for decompilation. The biggest single productivity
  multiplier. Being able to ask "decompile FUN_38078550" and get readable C
  in 200ms changed the cadence of everything.
- **Manual PE-section parsing** in Python, for reading raw `.rdata` bytes at
  a known VA without leaving the terminal. ~20 lines of code; reused
  throughout.
- **Cross-binary symbol grep** for narrowing where to look. The killer
  finding that nothing in the SAP BO tree calls `setEncryptionKey` came from
  a single `grep -rl` across 2,236 DLLs. Total time: about 30 seconds.
- **Constant-pattern grep across binaries.** Once we had the 16-byte key, a
  literal byte-search across the install tree showed the constant in 3
  binaries (with 8 copies in two of them) — strong evidence it's a
  product-wide canonical. Same technique would work for any other suspected
  constant.
- **Empirical comparison of two implementations.** When you have two impls
  that *should* compute the same function, run them both on the same input
  and compare. The "PyCryptodome AES vs cslibu Rijndael::ProcessBlock"
  comparison in Round 8 was the moment of clarity.

## Tools and techniques that didn't pay off

- **Web search for prior reverse engineering of CR encryption.** Zero useful
  hits. `dbatesx/CRDiff` is a thin wrapper around the proprietary
  `CrystalDecisions.CrystalReports.Engine` SDK — useful as a future oracle
  for our parser, but contributes nothing to the cipher hunt.
- **Brute-force scanning .rdata for "any 16-byte blob that decrypts the
  sample"** with a "validity = inflates ≥ N bytes" predicate. The predicate
  was too weak; we got 20+ false positives that all turned out to be
  degenerate streams emitting one repeating byte (deflate's "RLE filler"
  patterns). A stronger predicate (inflated size ≥ 1KB AND output entropy
  in a sane range AND contains some plausible non-random structure) would
  have been a better instrument, but by the time we'd built it, the
  Round-8 emulator path had already worked.

---

## Cognitive errors made — and how to avoid them next time

### Confirmation bias on weak evidence

Round 4's "mask=0xfe, little-endian" decoded the 6 value-shorts correctly,
so we trusted it for the rest of the file. It was wrong; we just got lucky
on those 6 bytes. **Counter-strategy:** when validating a hypothesis, list
*additional* observations it would predict and check those before relying
on the hypothesis.

### Anchoring on the obvious-wrong-thing

For five rounds we kept asking "is the key wrong?" because the key is the
most-suspectable variable in a crypto mystery. We didn't ask "is the cipher
wrong?" because cipher impls are usually standard. **Counter-strategy:**
when an obvious variable seems wrong but every plausible variant of it
fails, expand the search to non-obvious variables. Make a "what could
possibly be wrong" list and don't omit the unlikely-feeling items.

### Negative evidence as positive evidence

"`BO_inflateInit2_` doesn't call `inflateSetDictionary`" was a correct
negative finding. We extended it into "therefore, raw deflate" without
verifying the positive form. **Counter-strategy:** every negative finding
("X is not happening") needs a separate positive verification ("here's what
*is* happening") before it informs downstream choices.

### Premature giving up on a path that turned out to be right

We *did* try the .rdata key in Round 5 and ruled it out. It came back as the
correct answer in Round 8. The mistake wasn't trying it; the mistake was
ruling it out without considering "maybe everything *else* in the recipe is
wrong." **Counter-strategy:** when ruling out a candidate, write down the
specific reason it failed. If later evidence undermines that reason, revisit.

### Ignoring the user's outside-perspective nudge for too long

The user suggested web research and broader thinking *before* Round 8. We
did the web research, didn't find anything, and concluded "no leverage
there" — but the bigger value of the nudge was the *context switch*, not the
search results. After the unsuccessful web search we should have taken the
extra step the user implicitly suggested: re-examine the cipher itself.
**Counter-strategy:** when someone collaborating with you says "step back,"
the value is partly in the search and partly in the act of stepping back.
Allocate time for both.

---

## Forward look: what to expect in Round 10+

The next phase is mapping record tags to semantics. Some rough expectations:

- **Easy parts.** Strings (length-prefix BE 4-byte + null-terminated bytes)
  are clearly identifiable. Layout fields (twips) are big-endian shorts/longs
  in fixed positions inside specific tags. Single-binding fields (font name,
  field name, formula text) will pop out from paired-sample diffs quickly.
- **Hard parts.** Fields whose meaning depends on context (a record's value
  layout depends on which "section" or "object class" it lives in). Records
  whose value bytes are *themselves* nested records (parser recurse heuristic
  needs work). Records that hold compressed/expanded references to other
  parts of the file (e.g. a "field reference" that names another record by
  ID, where the ID is itself encoded in some scheme).
- **Where we'll get stuck.** Most likely: a record class whose value layout
  changes based on a flag bit somewhere else in the file. The kind of
  conditional layout that's annoying in any binary format. The recipe will
  be paired-sample diffing plus reading the relevant `loadXxx` function in
  cslibu/crpe32 (yes, we'll switch Ghidra back and forth — the friction
  cost is real but the cognitive cost of *guessing* is much higher).
- **Where prior-art could help.** `dbatesx/CRDiff` running on Windows
  produces a JSON with the SDK's view of a report. We can use that as a
  ground-truth oracle: parse our way to a JSON, diff against CRDiff's JSON
  for the same sample, fix discrepancies. Worth doing as soon as we have
  any record class fully decoded — the test harness pays for itself
  immediately.

---

## Closing note on velocity

From "encrypted with unknown cipher" to "complete decoder, every byte
accounted for" took about 9 rounds spread across two sessions. Rounds 1-7
were essentially debugging the framing and chasing the wrong key; Round 8
was the unlock; Round 9 was a victory lap.

If we ran the project again knowing what we know now, the rough path would
be: (1) extract the .rdata key, (2) decompile `Rijndael::ProcessBlock`, (3)
notice the byte-position picks don't match FIPS-AES, (4) port the impl to
Python, (5) fix the framing, (6) parse the records. About one-third of the
elapsed time. Most of that compression comes from skipping the "is the
key wrong?" diversion and going straight to the cipher impl.

The project's biggest risk going into Round 10 is making the symmetric
mistake at the record-semantics layer: getting attached to a guess about
what tag X means and not noticing it's wrong because the values it
produces *look plausible*. Same counter-strategy: when a hypothesis is
consistent with the data, write down what *more* it would predict, and
check that.
