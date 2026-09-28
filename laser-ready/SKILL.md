---
name: laser-ready
description: Turn a DXF exported from Onshape into the laser-ready SVG that Nolop's laser cutter reads — pure-red hairlines, no fill, millimetres at true size. Use when a student asks how to prepare a part for laser cutting, wants the red-hairline SVG the cutter takes, needs a DXF turned into a cut file, asks how to set the colours UCP reads, or has an Onshape DXF export that needs to reach the laser.
---

# Prepare a DXF for the laser

This helper turns the DXF you exported from Onshape into the SVG the laser at
Nolop actually takes: cut lines in pure red, nothing filled, hairline strokes,
and a millimetre page so the part imports at its true size.

It is a helper, not a grader — it does not score you or check you off. It makes
the file and tells you what it did. The
[laser-cutting guide](https://tuftsmaker.github.io/ENT-164/laser-cutting/)
walks through the same preparation by hand in Inkscape, if you would rather see
every step.

## The Nolop material and bed

The laser at Nolop cuts stock up to about 3 mm, and the store sells **3 mm**
plywood and acrylic precut to the bed — so unless a student says they are using
their own material, **assume 3 mm**. That is the finger width and the slot depth
for a joint. If they have measured it with calipers, use their number.

The bed is **300 × 600 mm** (about 12 × 24 inches). Both tools report the size of
the page they wrote, and a page larger than the bed will not cut in one piece:

- `laser_svg.py` prints the `page size` line.
- `finger_joints.py` warns with a `CHECK` line when the jointed drawing is bigger
  than the bed.

## Setup

Resolve this skill's own folder from this file's location — opencode installs
it somewhere like `~/.cache/opencode/skills/laser-ready` — and do not assume
the current directory:

```bash
SKILL="<directory containing this SKILL.md>"
```

The converter is standard library only, but it runs on the **class Python
sandbox**: one pinned, private Python that every class skill shares, so
nothing depends on the student's own Python and nothing is installed into it.
Run this once per machine — cheap to re-run, and re-running repairs a broken
sandbox:

```bash
sh "$SKILL/ensure-runtime.sh"                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File "$SKILL\ensure-runtime.ps1"   # Windows
```

Its last line is `ENT164_PYTHON=…`: use exactly that interpreter for every
command below. On macOS and Linux it is
`"$HOME/.venvs/ent164-maker/bin/python"`, on Windows
`"$HOME\.venvs\ent164-maker\Scripts\python.exe"`. If the sandbox cannot
download — no internet, or a locked-down machine — say so and point at the
setup guide: <https://tuftsmaker.github.io/ENT-164/opencode-deepseek-guide/guide.html>.

## Run it

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/laser/laser_svg.py" part.dxf
```

That writes `part-laser-ready.svg` beside the DXF. Also useful:

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/laser/laser_svg.py" part.dxf -o out/part.svg   # choose the output
"$PY" "$SKILL/laser/laser_svg.py" part.dxf --margin 5        # 5 mm page margin
"$PY" "$SKILL/laser/laser_svg.py" part.dxf --open            # show it in the browser
```

## Show the student what it made

Two ways, and after any joint or conversion you should do one of them:

- **`--open`** (on both `laser_svg.py` and `finger_joints.py`) hands the written
  SVG to the student's browser. On `finger_joints.py` it converts the jointed DXF
  first, so what opens is the actual cut file, not just the DXF.
- **Show it in opencode's review pane**: the SVG is a plain file the agent can
  preview directly — use the browser preview tool on the `.svg` path (it renders
  vector and can zoom). Do this when `--open` cannot (a headless or remote
  session), or when you simply want the student to see it in the conversation.

The SVG is vector and at true size, so a browser preview is what confirms the
joint landed on the right edge and the size is right.

Nothing to install beyond the sandbox: the converter is standard library only —
no Inkscape, no Python packages — and it runs on the class Python sandbox (see
Setup), so the file comes out the same on every machine. The hairline is spelled
the way Inkscape reads it, so opening it there afterwards behaves; the
`box-and-birdhouse` skill shares the same sandbox for its engraving.

## Finger joints that fit

If the part joins another sheet, `laser/finger_joints.py` cuts finger joints
along a straight seam you name. It needs the thickness you measured with
calipers — a finger is one thickness wide and never deeper than one thickness:

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/laser/finger_joints.py" part.dxf -o jointed.dxf \
    --seam 0,0,100,0 --thickness 3.15 --side up
"$PY" "$SKILL/laser/finger_joints.py" jointed.dxf --check --thickness 3.15
```

Repeat `--seam x0,y0,x1,y1` for each seam. `--fingers N` sets the count, or leave
it off for as many as fit while keeping a butt at each end; `--side up|down`
picks which side of the seam the fingers cut to. The `--check` mode re-measures
the combs already in a file and reports any whose finger is deeper than the
thickness (or that ramp with a diagonal instead of a square mating face).

## Joints on a drawing the student made

Ask the student to **attach their DXF** (drop it into the chat, or give its
path). Then find the seam they mean instead of asking for coordinates:

```bash
SKILL="<directory containing this SKILL.md>"
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/laser/finger_joints.py" part.dxf --list
"$PY" "$SKILL/laser/finger_joints.py" part.dxf --preview seams.svg
```

`--list` prints every straight seam it can find, longest first, with its length,
angle, centre and endpoints; `--preview` draws the same seams numbered and
coloured, so a student can look and say "seam 3". Ask which seam and which side,
and confirm the **measured** thickness, then:

```bash
PY="$HOME/.venvs/ent164-maker/bin/python"   # Windows: PY="$HOME\.venvs\ent164-maker\Scripts\python.exe"
"$PY" "$SKILL/laser/finger_joints.py" part.dxf -o jointed.dxf \
    --pick 3 --thickness 3.15 --side up
```

`--pick N` uses the same numbering as `--list` and `--preview`. Collinear pieces
are merged, so a wall drawn as three lines is offered once. A **straight line
already drawn along the seam is removed** and replaced by the comb, so the laser
cuts the joint once; if the seam is part of a polyline the tool cannot remove it
cleanly, and it says so — then that edge must come out in Onshape and be
exported again. Add `--open` to show the jointed file in the browser as soon as
it is written. The jointed DXF still needs the `laser_svg.py` step above to
reach the cutter.

## What "laser-ready" means

UCP decides what to do with each line by its colour:

- **pure red `#ff0000`, opacity 1** — UCP cuts red, scores blue, and rasters
  everything else. A dark red or a 90%-opaque red is not read as a cut.
- **no fill** — a filled shape is engraved, not cut.
- **hairline** — the laser follows the centre of the line it is given; a thick
  line gives it nothing useful to follow and can make it fire twice.

The converter sets all three, and pages the drawing in millimetres at true
size.

## What it reports while it works

Alongside the page and part size and the number of cut paths, it prints anything
worth a second look rather than hiding it:

- geometry it had to approximate (splines, ellipse arcs, polyline bulges);
- cut lines sitting on an unexpected layer;
- two entities drawn on the same line — the laser fires on each copy, so remove
  the duplicate in Onshape and export again.

## Looking at the result

Open the SVG in a browser or in Inkscape to check the colour and the size before
you take it to Nolop. The file path is printed when it is written.
