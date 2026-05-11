# Sample 004 — two text labels with different strings (GREETINGS + SOMEONE)

**Diff partner(s):** 003_two_labels_hello_world (identical geometry; only the literal strings differ)

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x

**Sections present:** Page Header / Details / Page Footer

**DB bindings:** none

**Elements:**

| # | Type        | Name  | Section | left | top | width | height | Notes                       |
|---|-------------|-------|---------|------|-----|-------|--------|-----------------------------|
| 1 | Text Object | Text1 | Details |  100 | 100 | 1869  | 221    | Literal text "GREETINGS"    |
| 2 | Text Object | Text2 | Details | 2055 | 100 | 1869  | 221    | Literal text "SOMEONE"      |

**Designer-reported coordinate units:** twips

**Anything weird or noteworthy:** Geometry exactly matches sample 003. A 003→004 diff should change only the string-bearing records (candidates: tag 0xC2 plus any string-carrying side records); records that hold geometry, font, or section binding should be byte-identical.
