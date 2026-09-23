---
name: maker-tasks
description: Self-check a maker task submission before handing it in for signoff. Use when a student asks whether their DXF is laser-ready, wants to check a task file against the task's criteria, needs to build the submission folder (DXF + manifest.md) for a CAD/laser task, or asks what is left to fix in a sketch they exported from Onshape.
---

# Maker skill tasks — check your own work first

ENT-164 turns maker skills into **tasks**: each one is a short video, something
you make, and a file you hand in. A TA signs the task off against written
criteria — and the same criteria are checked here, on your own machine, before
you submit. Nothing is sent anywhere when you run this.

The tasks live at <https://tuftsmaker.github.io/ENT-164/tasks/>, which opens with
a map of the whole qualification — six tasks and the order they unlock in.

## Run the check

```bash
python3 tools/skill-tasks/check/cli.py --task cad-03-cut-a-hole part.dxf
```

The report tells you one of three things for each criterion:

- `[ok]` — it passes
- `[FIX]` — it does not; the line under it says what to change in Onshape
- `[?]` — a person will judge this one (a photo, your Onshape link)

Fix everything marked `[FIX]`, then hand in. A submission with a `[?]` is fine —
that is the part a TA looks at.

## What you hand in

Each task expects a small folder. Two files, every time:

```
part.dxf        your sketch, exported from Onshape
manifest.md     a few plain lines about the file
```

`manifest.md` looks like this — copy the field names exactly:

```
student: Your Name
onshape_url: https://cad.onshape.com/documents/.../w/.../e/...
material_thickness: 3.15
width_before: 100
self_check: ready to submit
```

Build the folder, check it, and zip it in one go:

```bash
# from the repo, with your file next to the manifest
python3 tools/skill-tasks/check/check_submission.py --task cad-01-first-sketch ~/ent164/cad-01
```

That checks the folder, writes the report into it as `check-report.txt`, and
tells you the zip to upload in Canvas.

## The tasks

| id | what it is | your file |
|----|-----------|-----------|
| `cad-01-first-sketch` | draw a 100 × 60 mm rectangle and export the DXF | `part.dxf` |
| `cad-02-update-dimension` | change the width to 80 mm by editing the dimension | `part.dxf` |
| `cad-03-cut-a-hole` | add a 10 mm hole 20 mm in from two edges | `part.dxf` |
| `cad-04-center-a-hole` | find the centre with construction lines, hole there | `part.dxf` |
| `cad-05-corner-hole` | anchor the hole 20 mm from a corner | `part.dxf` |
| `cad-06-mirror` | draw half, mirror it, keep both halves identical | `part.dxf` |

The six together are the **Laser-Ready File** qualification. The last step is a
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

- Task list and videos: `tasks/` on the class site, or `tools/skill-tasks/tasks/*.yml` in the repo
- The criteria themselves: `<repo>/tools/skill-tasks/tasks/cad-NN-*.yml`
- The checks: `<repo>/tools/skill-tasks/check/`
- The videos: the **Onshape tips** page, `onshape-tips/index.html`
