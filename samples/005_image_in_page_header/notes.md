# Sample 005 — two labels + image in Page Header

**Diff partner(s):** 004_two_labels_greetings_someone (this adds one image element to the Page Header section)

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x

**Sections present:** Page Header / Details / Page Footer

**DB bindings:** none

**Elements:**

| # | Type        | Name  | Section     | left | top | width | height | Notes                  |
|---|-------------|-------|-------------|------|-----|-------|--------|------------------------|
| 1 | Image       | Pic1  | Page Header | 2128 |  76 | 2445  | 2371   | Embedded image         |
| 2 | Text Object | Text1 | Details     |  100 | 100 | 1869  | 221    | Literal text "GREETINGS" |
| 3 | Text Object | Text2 | Details     | 2055 | 100 | 1869  | 221    | Literal text "SOMEONE"  |

**Designer-reported coordinate units:** twips

**Anything weird or noteworthy:** Text Object records should be unchanged vs 004; diff against 004 isolates the image plumbing (image record(s), page-header section content, and likely some object-count headers).
