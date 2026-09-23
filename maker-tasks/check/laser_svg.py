#!/usr/bin/env python3
"""Convert an Onshape sketch DXF into a laser-ready SVG of pure-red hairlines.

    python3 check/laser_svg.py part.dxf
    python3 check/laser_svg.py part.dxf -o part-laser-ready.svg
    python3 check/laser_svg.py part.dxf --margin 5

Why this exists
---------------
The checker tells you the DXF is *ready*. This turns it into the file the laser
actually takes: an SVG whose cut lines are pure red, unfilled and hairline — the
three things UCP reads (see `laser-cutting/guide.html`, "Set the colours the
laser reads").

The rules, and where they come from
-----------------------------------
* **Pure red `#ff0000`, opacity 1.** UCP decides by colour: red cuts through,
  blue scores, anything else rasters. A dark red or a 90%-opaque red is not
  read as a cut, so the stroke is exactly `#ff0000` at `stroke-opacity:1`.
* **No fill.** A filled shape is an engraving, not a cut: `fill:none`.
* **Hairline.** The laser follows the centre of the line it is given; a thick
  line gives it nothing useful to follow and can make it fire twice.

About hairline, specifically
----------------------------
The obvious spelling is wrong. `stroke-width="hairline"` is *not* understood as
Inkscape's Hairline: Inkscape falls back to a 1 mm line, which is exactly the
thick line the warning above is about. Inkscape's own serialisation of the UI's
Hairline is three declarations together:

    stroke-width:1px; vector-effect:non-scaling-stroke; -inkscape-stroke:hairline

The first two keep the line visible and thin in renderers that do not know the
property; the last is what makes Inkscape itself draw and print a true hairline.
Measured, this renders at ~0.04 mm against ~1.02 mm for the naive form. It is a
plain attribute in the file, so nothing needs Inkscape installed for the output
to be correct — only to edit it.

No dependencies
---------------
Standard library only, importing the reader beside it, so the same file runs on
a student's laptop through the skill and in CI. Nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dxf_reader  # noqa: E402
from dxf_reader import _near  # noqa: E402  (shared point tolerance)

# $INSUNITS codes -> millimetres. Onshape writes none at all (normal, and why
# the checker infers the unit from the stated size); a missing value is mm.
INSUNITS_TO_MM = {
    "1": 25.4,    # inches
    "2": 304.8,   # feet
    "4": 1.0,     # millimetres
    "5": 10.0,    # centimetres
    "6": 1000.0,  # metres
}

# These three declarations together are Inkscape's Hairline. See the module
# docstring: `stroke-width="hairline"` alone is not it, and renders at 1 mm.
HAIRLINE = ("stroke-width:1px;vector-effect:non-scaling-stroke;"
            "-inkscape-stroke:hairline")

CUT_STYLE = ("fill:none;stroke:#ff0000;stroke-opacity:1;"
             "stroke-linejoin:round;stroke-linecap:round;" + HAIRLINE)

# Layers whose geometry a student means to cut. Onshape puts sketch geometry on
# MODELSKETCH_VISIBLE; the others turn up in files from other tools. Geometry on
# any other layer is still emitted — never silently dropped — but reported.
CUT_LAYERS = {"MODELSKETCH_VISIBLE", "SKETCHED_GEOMETRY", "VISIBLE", "0"}


# ------------------------------------------------------------------ geometry

def shape_points(entity):
    """Points that define an entity's extent, for the page box.

    For an arc this is the endpoints plus whichever axis crossings (0/90/180/
    270 degrees) the sweep passes through. The whole circle's box would pad the
    page around geometry that is not there.
    """
    if entity.is_circle or entity.kind == "CIRCLE":
        (cx, cy), r = entity.centre, entity.radius
        return [(cx - r, cy - r), (cx + r, cy + r), (cx + r, cy - r), (cx - r, cy + r)]

    if entity.kind == "ARC" and entity.a0 is not None:
        pts = [arc_endpoint(entity, a) for a in (entity.a0, entity.a1)]
        sweep = (entity.a1 - entity.a0) % 360 or 360.0
        for axis in (0.0, 90.0, 180.0, 270.0):
            if 0 < (axis - entity.a0) % 360 < sweep:
                pts.append(arc_endpoint(entity, axis))
        return pts

    return entity.points


def arc_endpoint(entity, deg):
    cx, cy, r = entity.centre[0], entity.centre[1], entity.radius
    rad = math.radians(deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def drawable(drawing):
    """(entities, notes) — the entities worth drawing, and anything to flag.

    Every supported entity is kept. The notes cover the two approximations a
    student should know about before cutting: splines and ellipses arrive as
    fitted point lists (a polyline), and a polyline's bulge-coded vertices are
    straight lines here.
    """
    notes, keep = [], []
    for e in drawing.entities:
        if e.kind in ("SPLINE", "ELLIPSE"):
            notes.append(f"{e.kind} drawn as a {len(e.points)}-point polyline — "
                         "check the curve before cutting")
        elif e.bulges:
            # Onshape does not emit bulge codes; a file that has them came from
            # elsewhere, and drawing the segment straight would change the shape.
            notes.append("a polyline has arc-segment (bulge) vertices — those "
                         "segments are drawn as straight lines, so check them")
        if not e.is_circle and len(e.points) < 2:
            continue
        keep.append(e)
    return keep, notes


# ------------------------------------------------------------------ duplicates

def _geom_signature(entity):
    """A value that is equal for two entities cutting the same line.

    Direction is ignored — a line drawn end-to-start is the same cut — and a
    closed loop is rotated to a canonical start, so the same loop traced from a
    different vertex still matches.
    """
    if entity.is_circle or entity.kind == "CIRCLE":
        cx, cy = entity.centre
        return ("circle", round(cx, 6), round(cy, 6), round(entity.radius, 6))

    if entity.kind == "ARC" and entity.a0 is not None:
        cx, cy = entity.centre
        return ("arc", round(cx, 6), round(cy, 6), round(entity.radius, 6),
                round(entity.a0, 6), round(entity.a1, 6))

    pts = [(round(x, 6), round(y, 6)) for x, y in entity.points]
    if len(pts) > 2 and (entity.closed or _near(pts[0], pts[-1], 0.001)):
        if _near(pts[0], pts[-1], 0.001):
            pts = pts[:-1]
        i = min(range(len(pts)), key=lambda k: pts[k])
        pts = pts[i:] + pts[:i]
        return ("loop", tuple(pts))
    if len(pts) == 2:
        return ("line",) + tuple(sorted(pts))
    return ("path", tuple(pts))


def _where(entity):
    """A short human description of where an entity is."""
    if entity.is_circle or entity.kind == "CIRCLE":
        cx, cy = entity.centre
        return f"circle at ({cx:.3f}, {cy:.3f}) r{entity.radius:.3f}"
    pts = entity.points
    return (f"({pts[0][0]:.3f}, {pts[0][1]:.3f}) to "
            f"({pts[-1][0]:.3f}, {pts[-1][1]:.3f})")


def coincident_paths(entities):
    """Groups of entities that cut exactly the same line.

    Reported, never removed: a laser follows every path it is given, so two
    identical paths mean it fires twice on one line — which scorches the edge.
    Silently dropping one would instead be a tool editing the student's design,
    so the fix belongs in Onshape (delete the duplicate) and this only says so.
    """
    seen = {}
    for e in entities:
        seen.setdefault(_geom_signature(e), []).append(e)

    out = []
    for group in seen.values():
        if len(group) > 1:
            out.append({"count": len(group), "layer": group[0].layer,
                        "where": _where(group[0])})
    return sorted(out, key=lambda g: -g["count"])



# ------------------------------------------------------------------ SVG

def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def units_of(header):
    """(scale_to_mm, human wording) from $INSUNITS, defaulting to millimetres."""
    raw = str((header or {}).get("$INSUNITS") or "").strip()
    if raw:
        try:
            key = str(int(float(raw)))
        except ValueError:
            key = ""
        scale = INSUNITS_TO_MM.get(key)
        if scale is not None:
            if scale == 1.0:
                return scale, "millimetres"
            name = {25.4: "inches", 304.8: "feet", 10.0: "centimetres",
                    1000.0: "metres"}.get(scale, f"units code {key}")
            return scale, f"{name} (converted to mm)"
    return 1.0, "millimetres (none declared — Onshape exports mm)"


def build_svg(entities, header, margin, source_name):
    """Render entities into an SVG string, plus a short report dict.

    CAD is Y-up and SVG is Y-down, so Y is flipped; the part keeps its size.
    """
    scale, units = units_of(header)

    pts = [p for e in entities for p in shape_points(e)]
    xmin = min(p[0] for p in pts) * scale
    ymin = min(p[1] for p in pts) * scale
    xmax = max(p[0] for p in pts) * scale
    ymax = max(p[1] for p in pts) * scale

    page_w = (xmax - xmin) + 2 * margin
    page_h = (ymax - ymin) + 2 * margin

    def T(p):
        return (p[0] * scale - xmin + margin, ymax - p[1] * scale + margin)

    def red_circle(i, centre, r):
        cx, cy = T(centre)
        return (f'  <circle id="cut-{i}" cx="{fmt(cx)}" cy="{fmt(cy)}" '
                f'r="{fmt(r * scale)}" style="{CUT_STYLE}"/>')

    body = []
    for i, e in enumerate(entities, 1):
        if e.is_circle or e.kind == "CIRCLE":
            body.append(red_circle(i, e.centre, e.radius))
            continue

        if e.kind == "ARC" and e.a0 is not None:
            sweep = (e.a1 - e.a0) % 360
            if sweep == 0:  # a full turn is a circle
                body.append(red_circle(i, e.centre, e.radius))
                continue
            sx, sy = T(arc_endpoint(e, e.a0))
            ex, ey = T(arc_endpoint(e, e.a1))
            large = 1 if sweep > 180 else 0
            # CAD angles run CCW with Y up. The Y-flip mirrors the drawing, so a
            # CCW CAD arc is still CCW on screen — which is SVG sweep-flag 0.
            d = (f"M {fmt(sx)},{fmt(sy)} A {fmt(e.radius * scale)},"
                 f"{fmt(e.radius * scale)} 0 {large} 0 {fmt(ex)},{fmt(ey)}")
            body.append(f'  <path id="cut-{i}" d="{d}" style="{CUT_STYLE}"/>')
            continue

        pts_ = [T(p) for p in e.points]
        d = "M " + " L ".join(f"{fmt(x)},{fmt(y)}" for x, y in pts_)
        if e.closed:
            d += " Z"
        body.append(f'  <path id="cut-{i}" d="{d}" style="{CUT_STYLE}"/>')

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!-- Laser-ready cut file: pure red (#ff0000) hairlines, no fill.\n'
        f'     Source: {source_name}\n'
        f'     Units: {units}; part and page sizes in millimetres.\n'
        '     Red cuts, blue scores, black engraves — keep these red. -->\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n'
        f'     width="{fmt(page_w)}mm" height="{fmt(page_h)}mm"\n'
        f'     viewBox="0 0 {fmt(page_w)} {fmt(page_h)}">\n'
        + "\n".join(body) + "\n</svg>\n"
    )

    layers = {}
    for e in entities:
        layers[e.layer] = layers.get(e.layer, 0) + 1

    report = {
        "units": units,
        "part_w": xmax - xmin,
        "part_h": ymax - ymin,
        "page_w": page_w,
        "page_h": page_h,
        "shapes": len(entities),
        "layers": layers,
        "off_layer": {l: n for l, n in layers.items() if l not in CUT_LAYERS},
    }
    return svg, report


def convert(dxf_path, out_path=None, margin=0.0):
    """DXF -> laser-ready SVG. Returns (out_path, report, notes).

    Raises dxf_reader.DxfError when the file has no usable geometry, with the
    same wording the checker uses so a student sees one story.
    """
    dxf_path = Path(dxf_path)
    drawing = dxf_reader.read(dxf_path)
    entities, notes = drawable(drawing)
    if not entities:
        raise dxf_reader.DxfError("no 2D geometry found in the ENTITIES section")

    svg, report = build_svg(entities, drawing.header, margin, dxf_path.name)
    out = Path(out_path) if out_path else dxf_path.with_name(
        f"{dxf_path.stem}-laser-ready.svg")
    if out.parent != Path(""):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg)
    report["skipped"] = dict(drawing.skipped)
    report["coincident"] = coincident_paths(entities)
    return out, report, notes


# ------------------------------------------------------------------ CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="laser-svg",
        description="Convert an Onshape sketch DXF into a laser-ready SVG "
                    "(pure-red hairlines, no fill).",
    )
    ap.add_argument("dxf", help="the sketch DXF to convert")
    ap.add_argument("-o", "--output", help="where to write the SVG "
                    "(default: <name>-laser-ready.svg beside the DXF)")
    ap.add_argument("--margin", type=float, default=0.0,
                    help="margin around the part, in mm (default 0)")
    args = ap.parse_args(argv)

    try:
        out, rep, notes = convert(args.dxf, args.output, args.margin)
    except dxf_reader.DxfError as exc:
        print(f"error: {Path(args.dxf).name}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"source      : {Path(args.dxf).name}")
    print(f"units       : {rep['units']}")
    print(f"shapes      : {rep['shapes']} cut path(s)")
    print("layers      : " + ", ".join(f"{k} x{v}" for k, v in
                                       sorted(rep["layers"].items())))
    print(f"part size   : {rep['part_w']:.3f} x {rep['part_h']:.3f} mm")
    print(f"page size   : {rep['page_w']:.3f} x {rep['page_h']:.3f} mm"
          f"  (margin {args.margin:g} mm)")
    print("style       : #ff0000, no fill, hairline, opacity 1")
    for n in notes:
        print(f"note        : {n}")
    if rep["skipped"]:
        print(f"note        : skipped {rep['skipped']}")
    for c in rep["coincident"]:
        print(f"CHECK       : {c['count']} entities cut the same line "
              f"({c['where']}) — the laser fires on each, so remove the "
              f"duplicate in Onshape")
    if rep["off_layer"]:
        print(f"CHECK       : geometry on unexpected layers: {rep['off_layer']}")
    print(f"wrote       : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
