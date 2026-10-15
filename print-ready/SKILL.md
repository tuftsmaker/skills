---
name: print-ready
description: Turn an STL into G-code for the two Prusa printers at Nolop, the MK4 and the CORE One. Use when a student asks to slice a part, prepare an STL for 3D printing, check whether a part fits the build volume, needs G-code for the MK4 or the CORE One, or wants to see a preview of the toolpaths before printing.
---

# Slice an STL for the Nolop printers

This helper turns an STL file into G-code for the two printers in the
makerspace: the **Prusa MK4** and the **Prusa CORE One**. It writes each
printer's own start and end sequence, so the machine homes, levels the bed and
purges its nozzle the way its firmware expects.

It is a helper, not a replacement for PrusaSlicer. Read
[What this will not do](#what-this-will-not-do) before you print a part with
overhangs.

## The two printers

Both printers take **PLA** and a **0.4 mm nozzle**. That is all the class has
set up, so those are the only settings this tool writes.

| Printer | Build volume | Enclosure |
| --- | --- | --- |
| Prusa MK4 | 250 x 210 x 220 mm | open frame |
| Prusa CORE One | 250 x 220 x 270 mm | closed, held at 20 C for PLA |

The tool checks your part against the build volume and warns you when it does
not fit. It also centres the part on the bed for you.

## Setup

Resolve this skill's own folder from this file's location. opencode installs it
somewhere like `~/.cache/opencode/skills/print-ready`, so do not assume the
current directory:

```bash
SKILL="<directory containing this SKILL.md>"
```

The slicer runs on the **class Python sandbox**. That is one pinned, private
Python shared by every class skill, so nothing depends on your own Python and
nothing is installed into it. Run this once per machine. Re-running is cheap
and repairs a broken sandbox:

```bash
sh "$SKILL/ensure-runtime.sh"                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File "$SKILL\ensure-runtime.ps1"   # Windows
```

Its last line is `ENT164_PYTHON=...`. Use exactly that interpreter for every
command below. On macOS and Linux it is
`"$HOME/.venvs/ent164-maker/bin/python"`, on Windows
`"$HOME\.venvs\ent164-maker\Scripts\python.exe"`. If the sandbox cannot
download, because there is no internet or the machine is locked down, say so
and point at the setup guide:
<https://tuftsmaker.github.io/ENT-164/opencode-deepseek-guide/guide.html>.

## Run it

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/slicer/slice_stl.py" part.stl
```

That writes `part-mk4.gcode` beside the STL. To slice for the other printer,
or to change the print settings:

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/slicer/slice_stl.py" part.stl --machine coreone
"$PY" "$SKILL/slicer/slice_stl.py" part.stl --infill 25 --perimeters 3
"$PY" "$SKILL/slicer/slice_stl.py" part.stl -o out/part.gcode
"$PY" "$SKILL/slicer/slice_stl.py" part.stl --preview part.png
"$PY" "$SKILL/slicer/slice_stl.py" part.stl --preview part.png --open
```

`--layer-height` defaults to 0.20 mm and `--infill` to 15 percent. A 0.4 mm
nozzle prints layers from about 0.08 mm to 0.28 mm. Thinner layers look better
and take longer.

## Show the student what it made

G-code is a list of coordinates, so a student cannot tell from the file whether
the part sliced the way they meant. The preview shows the toolpaths:

- **`--preview part.png`** writes a top-down picture of the layers, shaded from
  blue at the bottom to red at the top. Walls are drawn thicker than infill.
- **`--open`** also opens that picture in the browser.

Look at the preview with the student. A hole that should be empty but is
crossed by infill, or a wall that runs off the edge of the part, shows up here
and not in a text report. You can also show the PNG in opencode's review pane
by previewing the file path.

## What it reports while it works

The tool prints what it found and what it wrote:

- the model's triangle count and its size in millimetres;
- the number of layers sliced and how many of them have geometry;
- the filament used, in metres and grams;
- a **note** line for anything worth a second look.

The note lines matter. A mesh that is not watertight is the usual reason a
slicer produces a strange result, and this tool says so instead of stopping:

```
note       : 86 duplicated edge(s): the mesh is not watertight, and slicers differ in how they cope
```

A model exported in the wrong units, or from a 2D sketch, comes back flat in
one axis. That is reported too.

## Supports

Overhangs need something under them. Turn supports on with `--support`. They
are off by default, which is how PrusaSlicer ships them.

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/slicer/slice_stl.py" part.stl --support
"$PY" "$SKILL/slicer/slice_stl.py" part.stl --support --support-angle 50
```

An overhang is the part of a layer that the layer below does not hold up. The
printer can lean a little past the layer below before it needs help, and how
far is `layer height / tan(angle)`. At the default 40 degrees that is 0.24 mm
per layer.

`--support-angle` is measured from the horizontal, so a vertical wall is 90
degrees. The default of 40 means an overhang flatter than 40 degrees gets
support. Raise it to support less, lower it to support more. A 45 degree
overhang stands up on its own at any setting, which is the usual rule of
thumb.

Support is built to come off:

- a gap of one layer height, 0.2 mm, above it, so the part does not fuse to it;
- a gap of 0.29 mm around it, so it does not fuse to the walls;
- the top three layers are dense, so the overhang lands on something flat;
- the rest is sparse, about 18 percent.

The preview draws support in grey, so you can see where it went.

## What this will not do

**Its supports do not widen as they go down.** PrusaSlicer thickens a support
column with depth so a tall column stays stable. This one keeps the width of
the overhang it holds, so a tall narrow column may wobble. Watch the first few
layers of a tall support.

**It does not detect bridges**, so a bridge prints as a normal line over open
air. It has no arc fitting, so the G-code file is larger than PrusaSlicer's for
the same part. It has no variable layer height.

**It does not estimate print time**, because that needs acceleration and flow
limits from the firmware, not only the length of the path.

For anything difficult, or anything you intend to print more than once, use
PrusaSlicer. Use this tool when PrusaSlicer is not installed, when you want to
slice from a script, or when the part is a simple solid.

## If something goes wrong

**"error: no such file"**. The path to the STL is wrong. Give the full path, or
run the command from the folder that holds the file.

**"nothing to print - no layer produced any geometry"**. The model has no
volume. This happens when a sketch is exported as an STL instead of a solid.
Export again from Onshape as a part, not a sketch.

**The part is larger than the build volume**. The tool prints a WARNING line
and still writes the G-code, because you may only want to measure it. Scale the
part in Onshape, or print it in pieces.

**"no preview written - Pillow is not available"**. The sandbox is incomplete.
Run `ensure-runtime.sh` again.

**The print starts too high or too low**. The start sequence sets the nozzle
height with the printer's own mesh bed levelling. If the first layer is wrong,
the printer needs its first layer calibrated. Use the printer's own calibration
menu, not this tool.

## Next

If you are cutting flat parts instead of printing them, the `laser-ready` skill
turns an Onshape DXF into the file the laser cutter reads.
