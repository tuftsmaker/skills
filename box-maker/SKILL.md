---
name: box-maker
description: Generate the flat panels for a laser-ready, finger-jointed box — an open tray with a slip-on lid by default — or any custom part composed from the same joint primitives, such as a divider or the gabled birdhouse that ships as a worked example. Output is one SVG of pure-red hairlines on a millimetre page at true size, ready for the laser at Nolop. Use when a student asks for a box, tray, enclosure, drawer or birdhouse to cut, or wants finger joints sized to the material.
---

# Make laser-ready, finger-jointed parts

From a few dimensions, this generates the flat panels for a finger-jointed
**box** — an open tray, and by default a slip-on lid. The result is one SVG in
the colours the laser reads: pure red `#ff0000`, no fill, hairline, on a
millimetre page at true size. Cut it and the parts slot together; no glue
needed on the joints.

The box is the common case and has a command of its own. Anything else — a
divider, a custom enclosure, a birdhouse — is the same joint rules composed in
a few lines against the **box API**; `birdhouse.py` ships as the worked example
of that, and it is where the engraving lives.

## What to ask for

A student needs to give four numbers:

- **length** and **width** — the outside footprint, in mm.
- **height** — the wall height, in mm.
- **thickness** — the material, in mm. This is the finger width and the slot
  depth. **At Nolop this is 3 mm** — the store sells 3 mm plywood and acrylic
  precut to the bed — so default to `3` and only ask for a different value if the
  student is using their own material. If they measured it with calipers, use
  their number: a nominal "3 mm" sheet is often 2.8–3.2 mm, and getting it wrong
  makes the box too tight or too loose.

If the student gives a box "to hold X" rather than outside dimensions, work out
the outside size first and confirm it, then pass it here. Optional knobs: a
kerf `--fit` (default 0.1 mm), `--no-lid`, `--lid-height` and `--clearance`.

**Fits the Nolop bed?** The laser bed is **300 × 600 mm**. The generator wraps the
panels into rows across the bed's 600 mm side and then checks the result, printing
either `bed : page ... fits the Nolop bed` or a `CHECK :` line when it does not —
so a box whose panels cannot share one sheet is flagged, not silently written.

## Setup

Resolve this skill's own folder from this file's location — opencode installs
it somewhere like `~/.cache/opencode/skills/box-maker` — and do not
assume the current directory:

```bash
SKILL="<directory containing this SKILL.md>"
```

The generators run on the **class Python sandbox**: one pinned, private Python
that every class skill shares, so nothing depends on the student's own Python
and nothing is installed into it. Run this once per machine — cheap to re-run,
and re-running repairs a broken sandbox:

```bash
sh "$SKILL/ensure-runtime.sh"                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File "$SKILL\ensure-runtime.ps1"   # Windows
```

Its last line is `ENT164_PYTHON=…`: use exactly that interpreter for every
command below. On macOS and Linux it is
`"$HOME/.venvs/ent164-maker/bin/python"`, on Windows
`"$HOME\.venvs\ent164-maker\Scripts\python.exe"`. It comes with Pillow (the
engraving) and PyYAML. If the sandbox cannot download — no internet, or a
locked-down machine — say so and point at the setup guide:
<https://tuftsmaker.github.io/ENT-164/opencode-deepseek-guide/guide.html>.

## Run it — a box

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/box.py" --length 150 --width 100 --height 60
```

That uses the default 3 mm Nolop material and writes `box-laser-ready.svg`.
Choose the file, or the material, with flags:

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/box.py" -l 150 -w 100 --height 60 -o out/caddy.svg
"$PY" "$SKILL/box.py" -l 150 -w 100 --height 60 --thickness 3.15   # own stock
"$PY" "$SKILL/box.py" -l 150 -w 100 --height 60 --no-lid
"$PY" "$SKILL/box.py" -l 150 -w 100 --height 60 --fit 0.2
```

The geometry is standard library only; with the sandbox set up (see Setup),
a plain box needs nothing else. (`-h` is help; the height flag is `-H` or
`--height`.)

## Making your own part — the box API

The generator is an ordinary Python module, and a part the command does not
know is meant to be composed from its primitives, not to become another flag.
Write a small script: build the panels, then `layout` them, then `svg` them.
Run it on the sandbox interpreter too (see Setup). The useful names:

| function | what it gives you |
| --- | --- |
| `box.finger_intervals(length, width)` | where the fingers sit along an edge, with a butt at each end |
| `box.combed_edge(p0, p1, normal, intervals, depth, width, kind, fit)` | one edge with a comb on it (`kind` is `"tab"` or `"slot"`) |
| `box.tray_panels(length, width, height, thick, finger, fit)` | the tray's base and four walls, in assembly coordinates |
| `box.layout(panels, margin=8, spacing=6)` | shelf-pack the panels into rows → `(placed, page_w, page_h)` |
| `box.fits_bed(page_w, page_h)` | does that page fit the Nolop bed → `(ok, message)` |
| `box.svg(placed, page_w, page_h)` | the finished SVG text |
| `birdhouse.birdhouse_panels(...)` | the worked example's panels |
| `birdhouse.render_text_png(text, height_mm)` | the engraved mark as a PNG (Pillow) |

Import them by adding this skill's folder to `sys.path`. Keep to these pieces:
they carry the joint rules (a finger is one thickness wide and never deeper,
tabs and slots match, no doubled cuts), which is the part that is easy to get
wrong by hand. `birdhouse.py` is the worked example of the whole pattern: its
`birdhouse_panels()` and `build()` show a custom part end to end, roof slopes
and entrance hole included.

## Worked example — the birdhouse

`birdhouse.py` makes a jointed birdhouse: four walls, a floor, a **gable roof**
of two slopes, and a **round entrance hole** in the front. Same material
default (3 mm) and the same bed check as the box. It is an example, not a
second product — copy its pattern for a part of your own.

Ask for **width**, **depth**, **wall height** and the **ridge** (apex height
above the floor — the gable rise is `ridge − wall height`). The entrance
`--hole` defaults to 35 mm (`0` for none); a bluebird box wants ~32 mm, a house
sparrow ~35 mm, and too large lets starlings in.

```bash
SKILL="<directory containing this SKILL.md>"
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/birdhouse.py" --width 130 --depth 110 --wall-height 110 --ridge 160
```

That writes `birdhouse-laser-ready.svg` (534 × 292 mm — fits the Nolop bed),
with a 35 mm hole. Variations:

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/birdhouse.py" -w 130 -d 110 --wall-height 110 --ridge 160 -o out/box.svg
"$PY" "$SKILL/birdhouse.py" -w 130 -d 110 --wall-height 110 --ridge 160 --hole 32
"$PY" "$SKILL/birdhouse.py" -w 130 -d 110 --wall-height 110 --ridge 160 --engrave
"$PY" "$SKILL/birdhouse.py" ... --open           # show it in the browser
```

`--engrave` (with no value) puts **ENT-164** on the front, below the entrance
hole; `--engrave "TEXT"` engraves something else. The text is rendered with a
real system font in **pure black**, which the laser *rasters* (engraves) —
against the **pure red** hairlines it cuts — and is sized to fit the front panel,
shrinking if needed. White stays unengraved, so only the letterforms are marked.
Engraving is the only part that needs a package — **Pillow** — and the class
sandbox already has it (see Setup), so there is nothing to install; the
geometry is standard library only.

How it fits: the **floor** tabs into slots in all four walls; the two **gable
ends** are full width with a peak to the ridge, and the **front and back** sit
between them, tabbing into the gable slots; the **roof** is two plain slopes that
rest on the gable peaks (glue or screw them — the jointed shell holds it
together). The entrance hole is cut as a loop inside the front panel, not as a
separate piece on the sheet. Hang it with the hole high on the front, no perch
below it, facing away from the prevailing weather. If a birdhouse does not fit
the bed, reduce the size or the ridge — the script prints the same
`bed :`/`CHECK :` line as the box.

## What you get, and how it fits

- The base's edges carry **tabs** that seat in **slots** in the walls' bottom
  edges, and the side walls interlock with the front and back at the corners.
- Slots are cut `--fit` millimetres wider and deeper than the tabs, so the parts
  assemble after the laser's kerf. Too tight → raise `--fit` (0.15–0.2 mm is
  common); too loose → lower it.
- A finger is one thickness wide and **never deeper than one thickness**.
- The lid is a shallow inverted tray, sized to drop over the finished box with
  `--clearance` (default 0.4 mm).
- The panels come out laid flat on the page, at true size, in millimetres.

## Checking it and cutting it

Open the SVG in a browser or in Inkscape to see the panels and confirm the size.
If you drew the part yourself instead, the `laser-ready` skill turns an Onshape
DXF export into the same red-hairline format; and the
[laser-cutting guide](https://tuftsmaker.github.io/ENT-164/laser-cutting/) walks
through the Inkscape → UCP → laser steps.
