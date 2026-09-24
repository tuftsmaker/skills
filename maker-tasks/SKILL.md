---
name: maker-tasks
description: Self-check a maker task submission before handing it in for signoff, and turn a DXF into a laser-ready SVG. Use when a student asks whether their DXF is laser-ready, wants to check a task file against the task's criteria, needs to build the submission folder (DXF + manifest.md) for a CAD/laser task, asks what is left to fix in a sketch they exported from Onshape, or wants the red-hairline SVG the laser cutter reads.
---

# Maker skill tasks — check your own work first

ENT-164 turns maker skills into **tasks**: each one is a short video, something
you make, and a file you hand in. A TA signs the task off against written
criteria — and the same criteria are checked here, on your own machine, before
you submit. Nothing is sent anywhere when you run this.

The tasks live at <https://tuftsmaker.github.io/ENT-164/tasks/>, which opens with
a map of the whole qualification, and the five tracks the course is building
out. One track is open now; the others are written down but not yet available.

## Run the check

The checker is part of this skill, so there is nothing to install. Resolve the
skill's own folder from this file's location (opencode puts it somewhere like
`~/.cache/opencode/skills/maker-tasks`) — do not assume the current directory:

```bash
SKILL="<directory containing this SKILL.md>"
python3 "$SKILL/check/cli.py" --task cad-03-cut-a-hole part.dxf
```

The report tells you one of three things for each criterion:

- `[ok]` — it passes
- `[FIX]` — it does not; the line under it says what to change in Onshape
- `[?]` — a person will judge this one (a photo, your Onshape link)

Fix everything marked `[FIX]`, then hand in. A submission with a `[?]` is fine —
that is the part a TA looks at.

## Take it to the laser: the red hairline SVG

The checker says the file is *ready*. To hand something to the laser you also
need the file with the **colours it reads**: add `--svg` and the same run writes
one.

```bash
SKILL="<directory containing this SKILL.md>"
python3 "$SKILL/check/cli.py" --task cad-01-first-sketch part.dxf --svg
```

You get `part-laser-ready.svg` beside your DXF. Its cut lines are:

- **pure red `#ff0000`** — UCP cuts red, scores blue, rasters everything else
  (RGB 255, 0, 0 exactly, not dark red and not 90% opaque)
- **no fill** — a filled shape would be engraved instead of cut
- **hairline** — the laser follows the centre of a line; a thick one gives it
  nothing useful to follow and can make it fire twice

```bash
python3 "$SKILL/check/cli.py" --task cad-01-first-sketch part.dxf --svg out/part.svg
python3 "$SKILL/check/cli.py" --task cad-01-first-sketch part.dxf --svg --svg-margin 5
python3 "$SKILL/check/laser_svg.py" part.dxf     # the converter alone
```

Sizes are millimetres and the page is the part plus any margin, so the drawing
imports at its true size. This needs nothing installed: no Inkscape, no Python
packages. It writes the SVG whether or not every criterion passed — but if
anything is marked `[FIX]`, fix it in Onshape, re-export, and run it again, so
the SVG is not made from a file you are about to change.

You can still do exactly this by hand in Inkscape — that is what
[the laser-cutting guide](https://tuftsmaker.github.io/ENT-164/laser-cutting/)
walks through — and opening the SVG there is the way to check it, adjust it, or
add etched text. This just gets the colours and the hairline right for you.

## What you hand in

Each task expects a small folder. Two files, every time:

```
part.dxf        your sketch, exported from Onshape
manifest.md     one or two lines — opencode writes them for you
```

The laser-ready SVG is what you *take to Nolop*; it is not one of the two files
the submission is checked against, so keep it beside them rather than in the
folder if you like.

**Do not make the student hand-write `manifest.md`.** Ask for what the task
reads, then write the file. For every task that is the Onshape share link
(Share → set to "can view" → copy); two tasks add one more line:

- `cad-08-laser-joints` — also the thickness they measured with calipers:
  `material_thickness: 3.15`
- `cad-09-laser-ready` — instead of the link, which DXF it came from:
  `source_dxf: part.dxf`

Never invent a link or copy one from somewhere else; if the student has not
given one, ask. Missing lines come back as `[FIX]` with the line to add.

For most tasks the whole file is one line:

```
onshape_url: https://cad.onshape.com/documents/.../w/.../e/...
```

Build the folder, check it, and zip it in one go:

```bash
python3 "$SKILL/check/check_submission.py" --task cad-01-first-sketch ~/ent164/cad-01
```

If `manifest.md` is missing, that command writes a starter with just the lines
this task reads. It checks the folder, writes the report into it as
`check-report.txt`, and tells you the zip to upload in Canvas.

## The tasks

| id | what it is | your file |
|----|-----------|-----------|
| `cad-01-first-sketch` | draw a 100 × 60 mm rectangle and export the DXF | `part.dxf` |
| `cad-02-update-dimension` | change the width to 80 mm by editing the dimension | `part.dxf` |
| `cad-03-cut-a-hole` | add a 10 mm hole 20 mm in from two edges | `part.dxf` |
| `cad-04-center-a-hole` | find the centre with construction lines, hole there | `part.dxf` |
| `cad-05-corner-hole` | anchor the hole 20 mm from a corner | `part.dxf` |
| `cad-06-mirror` | draw half, mirror it, keep both halves identical | `part.dxf` |
| `cad-07-trim-tool` | combine an arc with a rectangle using the trim tool | `part.dxf` |
| `cad-08-laser-joints` | cut fingers and slots sized from measured material | `part.dxf` |
| `cad-09-laser-ready` | prepare a part for the laser: red hairlines, mm page | `part-laser-ready.svg` |

The nine together are the **Laser-Ready File** track (a qualification). The last step is a
supervised cut at Nolop: a TA watches you cut one of your own files.

## Reading the report

The checkers look at what actually reaches the laser:

- **closed** — every line end meets another. A corner that looks joined but
  isn't becomes a cut that stops in mid-air.
- **mm** — Onshape's DXF carries no unit label, so the size is checked against
  the task's stated dimensions. If the numbers are out by ~25× the export is in
  inches.
- **a rectangle** — four straight sides at right angles, measured, not assumed.
- **the hole** — size, position, and that the wall left around it is thicker
  than the laser beam (~3 mm kerf).
- **guides** — construction lines are not exported by Onshape. A stray line in
  the file is real geometry and would be cut, so it is flagged.

## Two things the checker cannot do

1. **It cannot tell that the file is yours.** It checks the DXF. The manifest's
   Onshape link is what lets a TA confirm the sketch and the dimension are
   really in your document, so keep it accurate.
2. **It cannot sign you off.** A pass here means "the file meets the criteria",
   not "task complete". A TA signs the task, and the laser checkout at Nolop is
   separate again — that one is about you, not the file.

## Where things are

- This skill's own folder: wherever opencode installed it — `$SKILL` above
- Task list and videos: `tasks/` on the class site
- The criteria for each task: `tasks/cad-NN-*.yml` inside this skill
- The checks and the SVG converter: `check/` inside this skill
- The videos: the **Onshape tips** page, `onshape-tips/index.html`
