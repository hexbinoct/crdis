# Sample 007 — labels + image in Details + one Line

**Diff partner(s):** 006_image_in_details (this adds exactly one Line element)

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x

**Sections present:** Page Header / Details / Page Footer

**DB bindings:** none

**Elements:**

| # | Type        | Name  | Section | left | top | width  | height | Notes                                  |
|---|-------------|-------|---------|------|-----|--------|--------|----------------------------------------|
| 1 | Text Object | Text1 | Details |  100 | 100 | 1869   | 221    | Literal text "GREETINGS"               |
| 2 | Text Object | Text2 | Details | 2055 | 100 | 1869   | 221    | Literal text "SOMEONE"                 |
| 3 | Image       | Pic1  | Details | 4028 |  76 | 2445   | 2371   | Same image as 005/006                  |
| 4 | Line        | Line1 | ?       | 1125 | 675 | (5325-1125)=4200 | (675-675)=0 | Endpoints: bottom=675 top=675 left=1125 right=5325 — horizontal line, style default |

**Designer-reported coordinate units:** twips

**Anything weird or noteworthy:** Per notes.txt: `bottom:675, top:675, left:1125, right:5325`. Equal top and bottom = horizontal line. A 006→007 diff isolates Line plumbing in a context that already contains text + image, useful for comparing against 008's lines-only baseline.
