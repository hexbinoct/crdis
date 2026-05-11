# crdis — Crystal Reports Disassembler

A clean-room, cross-platform parser for Crystal Reports `.rpt` files.

## Goal

Given a `.rpt` file, extract everything in it without depending on the proprietary Crystal Reports runtime, COM/OLE Automation, or any Windows-only component:

- All text content (field names, labels, formulas, embedded SQL, parameter definitions)
- Embedded images (extracted as standalone PNG/JPEG/BMP files)
- Element geometry — for every visible element, its bounding box (`x`, `y`, `width`, `height`) and section
- Eventually: full structural dump matching what the Designer view shows

## Why

Crystal Reports `.rpt` is a closed, undocumented binary format. Existing OSS tooling (e.g. `rpt-to-xml`) wraps the proprietary engine and runs only on Windows with the runtime installed — which defeats the point of breaking free of the legacy stack. This project builds the parser from scratch.

## Target

- **Format generation:** Crystal Reports for Visual Studio (CRforVS), version 13.x — files produced by Visual Studio 2010 through 2019. One format family, mostly stable across that range.
- **Other versions:** out of scope for now; revisit once 13.x is solid.

## Methodology

We do not have a spec, so we make one. The loop:

1. **Controlled-pair sampling.** In the CRforVS Designer, build a minimal `.rpt` file (e.g. empty report). Then build a second one differing by exactly one known change (e.g. one extra label at known coordinates). Save both with ground-truth notes (screenshots, property-panel values, DB bindings).
2. **Binary diff.** The bytes that changed between the pair encode that one change. Read them.
3. **Hypothesise.** Form a structural hypothesis: "bytes at offset X are the element's x-coordinate in twips," etc.
4. **Encode the hypothesis** as a [Kaitai Struct](https://kaitai.io) spec (`.ksy`) under `spec/`. Kaitai compiles to parsers in Python, JS, C, C#, Java, Go, Rust — the spec is the deliverable, the parsers are downstream.
5. **Verify** against more samples. Refine. Commit. Repeat.

## Layout

```
crdis/
  spec/          Kaitai Struct (.ksy) specification — the canonical output of this project
  crdis/         Python reference parser + CLI (uses spec/ via kaitaistruct runtime)
  samples/       Paired .rpt files + ground-truth screenshots/notes (see samples/README.md)
  research/      Running RE notebook — diff logs, hypotheses, dead ends
  tests/         Verifies parser against samples
```

## Status

Phase 0 — project setup. Awaiting first controlled sample pair (`samples/001_empty_vs_one_label/`).

## Phases

- **Phase 1:** Carve text + images, locate elements with bounding boxes (x/y/w/h).
- **Phase 2:** Section tree, element type discrimination (Text vs Field vs Line vs Box vs Image), font/style attributes.
- **Phase 3:** Formulas, parameters, sub-reports, group/sort definitions, DB binding metadata.
- **Phase 4:** Round-trip — emit a structural JSON that fully reproduces what Designer shows.

## Non-goals

- Rendering reports.
- Modifying or writing `.rpt` files (read-only parser).
- Supporting non-CRforVS versions until 13.x is solid.
