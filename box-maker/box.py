#!/usr/bin/env python3
"""Generate a laser-ready, finger-jointed box from its dimensions.

    python3 box.py --length 150 --width 100 --height 60 --thickness 3
    python3 box.py -l 150 -w 100 -h 60 -t 3 --lid --lid-height 15 -o box.svg

What it makes
-------------
An open tray: a base and four walls joined by finger joints (the base's edges
carry tabs that seat in slots in the walls' bottom edges; the walls interlock at
the corners). With `--lid` it also lays out a slip-on lid — a shallow inverted
tray — sized to drop over the box with a little clearance.

The output is one SVG whose cut lines are **pure red `#ff0000`, unfilled,
hairline**, on a millimetre page at true size, so it goes straight to the laser
at Nolop (the same conventions the `laser-ready` skill produces).

The fit
-------
A finger is one material thickness wide and never deeper than one thickness.
Slots are cut `--fit` millimetres wider (and deeper) than the tabs, so the parts
assemble after the laser's kerf. Measure your material and pass it as
`--thickness` — do not trust the nominal plywood size.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

HAIRLINE = (
    "fill:none;stroke:#ff0000;stroke-opacity:1;stroke-linejoin:round;"
    "stroke-linecap:round;stroke-width:1px;vector-effect:non-scaling-stroke;"
    "-inkscape-stroke:hairline"
)

EPS = 1e-9

# The laser at Nolop and the stock its store sells: 3 mm plywood or acrylic,
# precut to the bed. The bed is 300 x 600 mm (about 12 x 24 inches). These are
# the class defaults, so a student who just says "a 150 x 100 x 60 box" gets a
# file that is right for the machine without having to name the material.
NOLOP_THICKNESS = 3.0        # mm
NOLOP_BED = (300.0, 600.0)   # mm, short side x long side


def finger_intervals(length, width):
    """Where the fingers sit along an edge of `length`, local from 0.

    Returns [(start, end), ...] for each finger, leaving a butt at each end so
    the corners stay solid. One finger needs `length >= width`.
    """
    n = max(1, int(length // (2 * width)))
    while n > 1 and (2 * n - 1) * width > length + EPS:
        n -= 1
    if (2 * n - 1) * width > length + EPS:
        raise ValueError(
            f"a {width:g} mm finger does not fit a {length:g} mm edge")
    butt = (length - (2 * n - 1) * width) / 2.0
    return [(butt + i * 2 * width, butt + i * 2 * width + width)
            for i in range(n)]


def _dedupe(points):
    out = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > EPS or abs(p[1] - out[-1][1]) > EPS:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= EPS \
            and abs(out[0][1] - out[-1][1]) <= EPS:
        out.pop()
    return out


def combed_edge(p0, p1, normal, intervals, depth, width, kind, fit):
    """An axis-aligned edge from `p0` to `p1` with a comb along it.

    `intervals` are absolute coordinates on the edge's varying axis (x for a
    horizontal edge, y for a vertical one), each already widened for `fit` by
    the caller. `kind` is 'tab' (protrude by `depth`) or 'slot' (recede, cut
    `fit` wider and deeper by the caller). `normal` is the outward unit
    direction.

    The comb starts and ends on the edge line at `p0` and `p1`, so the polygon
    closes without an extra straight line along the edge.
    """
    axis = 0 if abs(p0[0] - p1[0]) > EPS else 1
    a0, a1 = p0[axis], p1[axis]
    sign = 1.0 if a1 > a0 else -1.0
    lo, hi = min(a0, a1), max(a0, a1)

    def at(coord, off):
        if axis == 0:
            return (coord + normal[0] * off, p0[1] + normal[1] * off)
        return (p0[0] + normal[0] * off, coord + normal[1] * off)

    pts = [p0]
    ordered = sorted(intervals, key=lambda iv: iv[0], reverse=(sign < 0))
    prev = None
    for (a, b) in ordered:
        d = -(depth + fit) if kind == "slot" else depth
        # The intervals are caller-supplied and must lie on the edge and not
        # overlap; a silent clamp here is what once doubled the cut line, so
        # refuse instead.
        if a < lo - 1e-6 or b > hi + 1e-6:
            raise ValueError(
                f"a comb interval {a:.3f}..{b:.3f} falls outside its "
                f"{lo:.3f}..{hi:.3f} edge")
        if prev is not None and (a < prev - 1e-6 if sign > 0 else a > prev + 1e-6):
            raise ValueError("comb intervals must not overlap or reorder")
        prev = b
        # Enter the interval from the end nearer the direction of travel, so the
        # slot/tab steps inward between its mouths rather than running along the
        # edge line (which would leave a doubled cut on the panel edge).
        near, far = (a, b) if sign > 0 else (b, a)
        pts += [at(near, 0.0), at(near, d), at(far, d), at(far, 0.0)]
    pts.append(p1)
    return pts


def tray_panels(length, width, height, thick, finger, fit):
    """The base and four walls of an open tray, as (name, [points]).

    Each panel is generated in assembly coordinates so the fingers on a tab
    panel and its matching slot panel line up exactly; the caller then
    translates them apart for the flat layout.
    """
    inner_l = length - 2 * thick
    inner_w = width - 2 * thick
    if inner_l < finger or inner_w < finger or height < finger:
        raise ValueError(
            f"too small: need length and width > 2 x thickness and height "
            f">= the finger width ({finger:g} mm)")

    fx = [(thick + a, thick + b) for a, b in finger_intervals(inner_l, finger)]
    fy = [(thick + a, thick + b) for a, b in finger_intervals(inner_w, finger)]
    fz = finger_intervals(height, finger)

    def slots(iv):
        """Widen a tab interval into a slot that clears it by `fit`."""
        return [(a - fit / 2.0, b + fit / 2.0) for a, b in iv]

    panels = []

    base = []
    base += combed_edge((thick, thick), (length - thick, thick), (0, -1),
                        fx, thick, finger, "tab", fit)
    base += combed_edge((length - thick, thick), (length - thick, width - thick),
                        (1, 0), fy, thick, finger, "tab", fit)
    base += combed_edge((length - thick, width - thick), (thick, width - thick),
                        (0, 1), fx, thick, finger, "tab", fit)
    base += combed_edge((thick, width - thick), (thick, thick), (-1, 0),
                        fy, thick, finger, "tab", fit)
    panels.append(("base", _dedupe(base)))

    # Front and back span the full length; slots on the bottom and both ends.
    for name in ("front", "back"):
        wall = []
        wall += combed_edge((0, 0), (length, 0), (0, -1),
                            slots(fx), thick, finger, "slot", fit)
        wall += combed_edge((length, 0), (length, height), (1, 0),
                            slots(fz), thick, finger, "slot", fit)
        wall += [(length, height), (0, height)]
        wall += combed_edge((0, height), (0, 0), (-1, 0),
                            slots(fz), thick, finger, "slot", fit)
        panels.append((name, _dedupe(wall)))

    # Left and right fit between the front and back; tabs on both ends.
    for name in ("left", "right"):
        wall = []
        wall += combed_edge((thick, 0), (width - thick, 0), (0, -1),
                            slots(fy), thick, finger, "slot", fit)
        wall += combed_edge((width - thick, 0), (width - thick, height), (1, 0),
                            fz, thick, finger, "tab", fit)
        wall += [(width - thick, height), (thick, height)]
        wall += combed_edge((thick, height), (thick, 0), (-1, 0),
                            fz, thick, finger, "tab", fit)
        panels.append((name, _dedupe(wall)))

    return panels


def translate(points, dx, dy):
    return [(x + dx, y + dy) for x, y in points]


def bounds(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def layout(panels, margin=8.0, spacing=6.0, row_width=None, bed=None):
    """Shelf-pack the panels, return (placed, page_w, page_h).

    `row_width` is how wide a row of panels may get; it defaults to the Nolop
    bed's long side, so the packed page is laid out to fit one sheet — the
    panels come out upright (their own Y is maintained) and wrap into rows,
    which is the sensible packing when they are mostly axis-aligned rectangles.
    """
    if row_width is None:
        row_width = (bed or NOLOP_BED)[1] - 2 * margin
    placed = []
    x = margin
    y = margin
    row_h = 0.0
    max_x = margin
    for name, pts in panels:
        _, _, w, h = bounds(pts)
        if x > margin and x + w > margin + row_width:
            x = margin
            y += row_h + spacing
            row_h = 0.0
        placed.append((name, translate(pts, x - min(p[0] for p in pts),
                                       y - min(p[1] for p in pts))))
        x += w + spacing
        row_h = max(row_h, h)
        max_x = max(max_x, x - spacing)
    return placed, max_x + margin, y + row_h + margin


def fits_bed(page_w, page_h, bed=NOLOP_BED):
    """Can the laid-out page be cut from one Nolop sheet?

    The pieces may be rotated on the bed, so the page fits if it fits the sheet
    either way round. Returns (ok, message).
    """
    short, long_ = min(bed), max(bed)
    if (page_w <= long_ + EPS and page_h <= short + EPS) or \
            (page_h <= long_ + EPS and page_w <= short + EPS):
        return True, (f"page {page_w:.0f} x {page_h:.0f} mm fits the Nolop bed "
                      f"({short:g} x {long_:g} mm)")
    return False, (f"page is {page_w:.0f} x {page_h:.0f} mm, which is larger "
                   f"than the Nolop bed ({short:g} x {long_:g} mm) — the panels "
                   f"need rearranging or the box making smaller")


def svg(placed, page_w, page_h):
    def path(pts):
        d = "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in pts) + " Z"
        return f'  <path d="{d}" style="{HAIRLINE}"/>'

    body = "\n".join(path(pts) for _, pts in placed)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Laser-ready cut file: pure red (#ff0000) hairlines, no fill. -->\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{page_w:.3f}mm" height="{page_h:.3f}mm" '
        f'viewBox="0 0 {page_w:.3f} {page_h:.3f}">\n'
        f"{body}\n</svg>\n"
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="box",
        description="Generate a laser-ready finger-jointed box (open tray and "
                    "an optional slip-on lid).",
    )
    p.add_argument("--length", "-l", type=float, required=True,
                   help="outside length in mm, along the front")
    p.add_argument("--width", "-w", type=float, required=True,
                   help="outside width in mm, front to back")
    p.add_argument("--height", "-H", type=float, required=True,
                   help="wall height in mm")
    p.add_argument("--thickness", "-t", type=float, default=NOLOP_THICKNESS,
                   help=f"the material thickness in mm (default {NOLOP_THICKNESS:g}, "
                        f"the Nolop stock; pass your own if you measured it)")
    p.add_argument("--finger", type=float, default=None,
                   help="finger width in mm (default: the material thickness)")
    p.add_argument("--fit", type=float, default=0.1,
                   help="kerf clearance added to every slot, in mm (default 0.1)")
    p.add_argument("--lid", dest="lid", action="store_true", default=True,
                   help="also lay out a slip-on lid (default)")
    p.add_argument("--no-lid", dest="lid", action="store_false",
                   help="the tray only")
    p.add_argument("--lid-height", type=float, default=15.0,
                   help="rim height of the lid, in mm (default 15)")
    p.add_argument("--clearance", type=float, default=0.4,
                   help="gap between the box and the lid, in mm (default 0.4)")
    p.add_argument("-o", "--output", default="box-laser-ready.svg",
                   help="where to write the SVG")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    finger = args.finger if args.finger else args.thickness
    if args.thickness <= 0 or args.fit < 0:
        print("error: thickness must be positive and fit non-negative",
              file=sys.stderr)
        return 2

    try:
        panels = tray_panels(args.length, args.width, args.height,
                             args.thickness, finger, args.fit)
        if args.lid:
            lid_l = args.length + args.clearance + 2 * args.thickness
            lid_w = args.width + args.clearance + 2 * args.thickness
            lid = tray_panels(lid_l, lid_w, args.lid_height,
                              args.thickness, finger, args.fit)
            panels += [(f"lid-{n}", pts) for n, pts in lid]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    placed, page_w, page_h = layout(panels)
    out = Path(args.output)
    if out.parent != Path(""):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg(placed, page_w, page_h), encoding="utf-8")

    names = ", ".join(name for name, _ in placed)
    print(f"box        : {args.length:g} x {args.width:g} x {args.height:g} mm, "
          f"{args.thickness:g} mm material (= finger width)")
    print(f"fit        : {args.fit:g} mm added to each slot"
          + (f", lid clearance {args.clearance:g} mm" if args.lid else ""))
    print(f"panels     : {len(placed)} ({names})")
    print(f"page       : {page_w:.1f} x {page_h:.1f} mm")
    ok, msg = fits_bed(page_w, page_h)
    print(f"{'bed        : ' if ok else 'CHECK      : '}{msg}")
    print(f"wrote      : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
