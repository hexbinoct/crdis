# Sample 009 — five Lines, varying thickness

**Diff partner(s):**
  - 008_two_lines_only (this adds three more lines and varies thickness;
    008 had two single-style lines at default thickness)
  - For thickness decode: compare any two Line blocks within this sample —
    they differ only by endpoints and thickness, which should isolate the
    thickness field (hypothesized at inner-0xEC offset 19 per Round 10 notes).

**CRforVS / Visual Studio version used to author:** CRforVS 13.0.x (Visual Studio)

**Sections present:** Page Header / Details / Page Footer (default)

**DB bindings:** none

**Elements:**

Originally named Line1, Line2, Line4, Line6, Line8 in Designer (gaps in
numbering reflect the user's authoring history — Designer auto-assigns
names and the user did not rename). Style is single (default) for all.

| # | Type | Designer name | left | top  | right | bottom | thickness | Notes                          |
|---|------|---------------|------|------|-------|--------|-----------|--------------------------------|
| 1 | Line | Line1         | 1920 |  690 | 7530  |   690  | 1.0       | Horizontal (top==bottom). w=5610 |
| 2 | Line | Line2         | 1950 | 1800 | 6540  |  1800  | 1.5       | Horizontal. w=4590               |
| 3 | Line | Line4         | 2400 | 2790 | 7065  |  2790  | 2.0       | Horizontal. w=4665               |
| 4 | Line | Line6         | 2025 | 3555 | 6150  |  3555  | 2.5       | Horizontal. w=4125               |
| 5 | Line | Line8         | 3585 | 4245 | 7605  |  4245  | 3.0       | Horizontal. w=4020               |

**Designer-reported coordinate units:** twips (left/top/right/bottom from
the Visual Studio Properties window). Thickness as reported in the Designer
Line Style picker (points: 1, 1.5, 2, 2.5, 3).

**Anything weird or noteworthy:**

Five same-style lines at increasing thickness, all in one report. Compared
to 008 (two lines, one single + one dotted, both default thickness), this
sample holds style constant and varies thickness — the natural
within-sample diff isolates the thickness encoding. Five different values
also let us check whether the encoding is integer-twips (1pt = 20 twips, so
1.0/1.5/2.0/2.5/3.0pt → 20/30/40/50/60), half-points, or some other unit.
