# Sample 006 — image moved from Page Header to Details

**Diff partner(s):** 005_image_in_page_header (same image, but placed in Details section to the right of "SOMEONE" instead of in Page Header)

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x

**Sections present:** Page Header / Details / Page Footer

**DB bindings:** none

**Elements:**

| # | Type        | Name  | Section | left | top | width | height | Notes                       |
|---|-------------|-------|---------|------|-----|-------|--------|-----------------------------|
| 1 | Text Object | Text1 | Details |  100 | 100 | 1869  | 221    | Literal text "GREETINGS"    |
| 2 | Text Object | Text2 | Details | 2055 | 100 | 1869  | 221    | Literal text "SOMEONE"      |
| 3 | Image       | Pic1  | Details | 4028 |  76 | 2445  | 2371   | Same image as 005           |

**Designer-reported coordinate units:** twips

**Anything weird or noteworthy:** A 005→006 diff isolates section-binding (which section an element belongs to) and any geometry deltas. Image dimensions are identical; only `left` changed (2128 → 4028) and the parent section.
