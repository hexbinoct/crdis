# samples/

Paired `.rpt` files plus ground-truth notes. Each sample directory captures one
*controlled* report — designed so its binary diff against another sample
isolates one specific aspect of the format.

## Naming convention

`NNN_short_description/` — three-digit zero-padded ID, snake_case description.

The ID is allocation order. Diffs are usually meaningful between *adjacent*
samples (`001` vs `002`), but any pair is fair game — note the relevant pair in
each sample's `notes.md`.

## Required files per sample

```
NNN_short_description/
  report.rpt         # the actual Crystal Report file
  designer.png       # screenshot of the report open in CRforVS Designer
  runtime.png        # (optional) screenshot when the report renders / previews
  notes.md           # ground truth — see template below
```

## notes.md template

```markdown
# Sample NNN — short description

**Diff partner(s):** NNN_other (what differs vs this sample)

**CRforVS / Visual Studio version used to author:** e.g. VS 2017, CRforVS 13.0.x

**Sections present:** Page Header / Details / Page Footer / Report Header / Report Footer / etc.

**DB bindings:** none / connection details (sanitised) / dataset name

**Elements (in z-order or as Designer lists them):**

| # | Type        | Name        | Section     | x   | y   | width | height | Notes (font, value, formula, etc.) |
|---|-------------|-------------|-------------|-----|-----|-------|--------|------------------------------------|
| 1 | Text Object | Text1       | Details     | 100 | 100 | 200   | 30     | Literal text "HELLO", Arial 10pt   |

**Designer-reported coordinate units:** twips / pixels / inches / cm — whatever the property panel shows.

**Anything weird or noteworthy:** ...
```

## Diff hygiene

To make diffs informative:

- Author both samples in the **same** Visual Studio + CRforVS install.
- Save them in the same session if possible — some headers contain timestamps.
- Change *one thing at a time* between paired samples.
- Don't let the Designer "auto-tidy" or reflow elements between saves.
