# Sample 008 — two Lines only (no labels, no image)

**Diff partner(s):**
  - 001_empty (this adds two Line elements to an otherwise-empty report)
  - 007_image_and_line (cross-check: Line1's payload should look like 007's Line1 with style swapped)

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x

**Sections present:** Page Header / Details / Page Footer (default)

**DB bindings:** none

**Elements:**

| # | Type | Name  | Section | left | top | right | bottom | Notes                                                  |
|---|------|-------|---------|------|-----|-------|--------|--------------------------------------------------------|
| 1 | Line | Line1 | ?       | 1050 | 240 | 5550  | 240    | Style: single. Horizontal (top==bottom). w=4500, h=0.   |
| 2 | Line | Line2 | ?       | 1710 | 870 | 5700  | 870    | Style: dotted. Horizontal (top==bottom). w=3990, h=0.   |

**Designer-reported coordinate units:** twips

**Anything weird or noteworthy:** Designer reports lines as four edges (left/top/right/bottom) rather than left/top/width/height — that's the natural endpoint representation for a line. Diff against 001 should be much cleaner than 006→007 because there's no text-object/image noise. Two lines also let us spot the per-element repeat pattern. Crucially, Line2 differs from Line1 only by style (single vs dotted) and endpoints — a within-sample comparison of the two Line record blocks should reveal the style byte/bit.

`source_notes.txt` in this directory is the original combined-notes file the user supplied for samples 003–008; preserved for provenance.
