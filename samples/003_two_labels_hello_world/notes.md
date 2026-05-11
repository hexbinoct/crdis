# Sample 003 — two text labels (HELLO + WORLD)

**Diff partner(s):** 002_one_label (this adds a second Text Object "WORLD" to the right of the unchanged "HELLO")

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x (matches 001/002 toolchain)

**Sections present:** Page Header / Details / Page Footer (default)

**DB bindings:** none

**Elements:**

| # | Type        | Name  | Section | left | top | width | height | Notes                  |
|---|-------------|-------|---------|------|-----|-------|--------|------------------------|
| 1 | Text Object | Text1 | Details |  100 | 100 | 1869  | 221    | Literal text "HELLO"   |
| 2 | Text Object | Text2 | Details | 2055 | 100 | 1869  | 221    | Literal text "WORLD"   |

**Designer-reported coordinate units:** twips

**Anything weird or noteworthy:** Label #1 geometry is identical to sample 002's single "HELLO" — a clean 002→003 diff isolates exactly one added Text Object.
