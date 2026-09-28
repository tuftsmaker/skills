#!/usr/bin/env python3
"""Cut finger joints along the straight seams where two shapes touch.

A finger joint needs one number: the material thickness. Everything else
follows from it, and the rule that makes a joint work or fail is that a finger
is **never deeper than one thickness**:

    finger depth   <=  material thickness      (hard rule)
    finger width    =  material thickness      (the class's convention)

so the whole joint lives in ONE thickness-wide band. Getting that wrong is easy
and silent — an earlier version of this tool cut a 6 mm band for 3 mm material,
i.e. fingers twice as deep as the sheet, and it still looked like a joint. The
depth is therefore asserted here, and `--check` re-measures it.

What this tool is given, and what it is not
-------------------------------------------
Seams are **supplied**, not discovered. Finding them automatically would mean
deciding which closed region is which piece, and that fails on real exports: an
Onshape sketch that draws one edge twice, or shares an edge between two loops,
does not chain into the regions a person sees in it. Rather than guess, this
takes each seam as a line segment plus which side carries the fingers, and
verifies the result.

The output is one path per seam — a single zigzag the laser cuts once. Two
pieces that meet along it come apart with matching fingers and slots, so no two
cut paths ever lie on the same line (a doubled path would make the laser fire
twice and scorch the edge).

Usage
-----
    # a seam from (0,0) to (100,0), 3 mm material, fingers cut upward
    laser/finger_joints.py part.dxf -o jointed.dxf \
        --seam 0,0,100,0 --thickness 3 --side up --fingers 16

    # list the straight seams it can see in a part you drew
    laser/finger_joints.py part.dxf --list
    laser/finger_joints.py part.dxf --preview seams.svg      # numbered, to look at
    laser/finger_joints.py part.dxf -o jointed.dxf --pick 3 --thickness 3 --side up

    # report what the joints on a file already measure
    laser/finger_joints.py jointed.dxf --check --thickness 3

The `--check` mode re-derives each comb's depth and width from the geometry, so
a joint that violates the depth rule is reported rather than assumed. `--list`
and `--preview` are how a student says *where* a joint goes without typing
coordinates: the seams are numbered, they pick one, and `--pick N` uses it.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dxf_reader  # noqa: E402

LAYER = "MODELSKETCH_VISIBLE"

# A plain butt is left at each end of a seam, so the piece's corners stay
# intact. It must not be squeezed to nothing: a finger starting a fraction of a
# millimetre from a corner leaves a sliver that snaps off, and the fit near the
# corner is on the sliver rather than on the joint. Half a thickness is the
# floor — an earlier auto count left 0.5 mm for 3 mm material, which is why it
# exists.
MIN_BUTT = 1.5


# ------------------------------------------------------------------ maths

def dedupe(pts, tol=1e-9):
    out = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) > tol or abs(out[-1][1] - p[1]) > tol:
            out.append(p)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) <= tol \
            and abs(out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def comb(start, end, thickness, fingers, side, butt=None):
    """A finger comb along the seam `start` -> `end`.

    `side` is +1 for the fingers to cut to the left of the direction of travel
    (in the direction of the seam's normal) and -1 for the other way; with a
    seam along +X that is up (+Y) and down (-Y) respectively.

    Returns the polyline points. The depth never exceeds `thickness`: every
    finger is one thickness deep, and the material between fingers returns to
    the seam line. The path runs along the seam, so it starts and ends on it.

    `fingers` is the number of fingers. The comb occupies 2*n-1 thicknesses
    (n fingers and n-1 slots), and whatever is left over is split as a plain
    butt at each end, keeping the piece's corners intact.
    """
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length <= 0:
        raise ValueError("a seam needs two distinct endpoints")

    span = (2 * fingers - 1) * thickness
    auto_butt = (length - span) / 2
    if butt is None:
        butt = auto_butt
    if butt < 0 or span + 2 * butt > length + 1e-9:
        raise ValueError(
            f"{fingers} fingers of {thickness} mm need "
            f"{span + 2 * butt:.1f} mm of a {length:.1f} mm seam")
    if butt < MIN_BUTT - 1e-9:
        raise ValueError(
            f"{fingers} fingers of {thickness} mm leave only {butt:.2f} mm at "
            f"each end of a {length:.1f} mm seam — too little for the corner "
            f"to hold (minimum {MIN_BUTT} mm). Use fewer fingers.")

    # unit vectors: along the seam, and normal to it
    ux, uy = dx / length, dy / length
    nx, ny = -uy * side, ux * side      # normal, pointing to the fingers' side

    def at(along, deep):
        return (sx + ux * along + nx * deep, sy + uy * along + ny * deep)

    pts = [at(0.0, 0.0), at(butt, 0.0)]
    along = butt
    for i in range(fingers):
        pts += [at(along, thickness), at(along + thickness, thickness),
                at(along + thickness, 0.0)]      # out, across the tip, back
        along += thickness
        if i < fingers - 1:
            pts.append(at(along + thickness, 0.0))   # along the seam to the next
            along += thickness
    pts.append(at(length, 0.0))
    return dedupe(pts)


# ------------------------------------------------------------------ DXF io

def pairs(*items):
    return "".join(f"{c}\r\n{v}\r\n" for c, v in items)


def lwpolyline(pts, layer=LAYER, closed=False):
    body = [(0, "LWPOLYLINE"), (8, layer), (100, "AcDbEntity"),
            (100, "AcDbPolyline"), (90, str(len(pts))),
            (70, "1" if closed else "0")]
    for x, y in pts:
        body += [(10, f"{x:.6f}"), (20, f"{y:.6f}")]
    return pairs(*body)


def _pt_on_segment(p, a, b, tol=0.02):
    """True when `p` lies on the segment a-b, within `tol`."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 <= 0:
        return False
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
    if t < -1e-9 or t > 1 + 1e-9:
        return False
    cross = (p[0] - a[0]) * dy - (p[1] - a[1]) * dx
    return abs(cross) / math.sqrt(l2) <= tol


def _strip_collinear_lines(text, seams):
    """Drop whole LINE entities that lie along any of `seams`.

    A comb is one cut path; leaving the seam's own line in place would make the
    laser fire twice along it. Only straight LINE entities that fall entirely on
    a chosen seam are removed — anything else is left alone and reported by the
    caller's overlap check.
    """
    lines = text.splitlines(keepends=True)
    start = end = None
    i = 0
    while i + 1 < len(lines):
        code, value = lines[i].strip(), lines[i + 1].strip()
        if code == "0" and value == "SECTION" and i + 3 < len(lines) \
                and lines[i + 2].strip() == "2" and lines[i + 3].strip() == "ENTITIES":
            start = i + 4
        elif code == "0" and value == "ENDSEC" and start is not None:
            end = i
            break
        i += 1
    if start is None or end is None:
        return text, 0

    body = lines[start:end]
    blocks, current = [], []
    for line in body:
        if line.strip() == "0" and current:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)

    kept, removed = [], 0
    for block in blocks:
        pairs = [(block[j].strip(), block[j + 1].strip())
                 for j in range(0, len(block) - 1, 2)]
        etype = pairs[0][1] if pairs else ""
        if etype == "LINE":
            vals = dict(pairs)
            try:
                p = (float(vals["10"]), float(vals["20"]))
                q = (float(vals["11"]), float(vals["21"]))
            except (KeyError, ValueError):
                p = q = None
            if p and any(_pt_on_segment(p, a, b) and _pt_on_segment(q, a, b)
                         for a, b in seams):
                removed += 1
                continue
        kept.append(block)

    new_body = [line for block in kept for line in block]
    return "".join(lines[:start]) + "".join(new_body) + "".join(lines[end:]), removed


def add_combs(src, out, seams, thickness, layer=LAYER, replace=True):
    """Write `out`: a copy of `src` with a comb cut along each seam.

    `seams` is a list of (start, end, fingers, side). Returns the written path,
    a per-seam report, and the number of existing seam lines removed.

    With `replace` (the default) a straight LINE already drawn along a seam is
    removed first, so the comb is the only path there; otherwise the laser fires
    twice along the seam. Combs are appended to the ENTITIES section.

    That section is located by parsing group codes rather than by matching text:
    DXF group-code lines may be padded (`  0`) or bare (`0`), and the OBJECTS
    section also has an ENDSEC, so `rpartition("ENDSEC")` finds the wrong one and
    a padded `pairs()` marker matches nothing at all.
    """
    drawing = dxf_reader.read(src)
    parts = []
    report = []
    for start, end, fingers, side in seams:
        pts = comb(start, end, thickness, fingers, side)
        parts.append(lwpolyline(pts, layer=layer))
        report.append(summarise(pts, start, end, thickness, fingers))

    text = Path(src).read_text(encoding="utf-8", errors="replace")
    removed = 0
    if replace:
        text, removed = _strip_collinear_lines(
            text, [(s[0], s[1]) for s in seams])
    at = _entities_end(text)
    if at is None:
        raise dxf_reader.DxfError("no ENTITIES section found")
    text = text[:at] + "".join(parts) + text[at:]
    Path(out).write_text(text, encoding="utf-8")
    return Path(out), report, drawing, removed


def _entities_end(text):
    """Character offset just before the ENTITIES section's closing ENDSEC."""
    lines = text.splitlines(keepends=True)
    in_entities = False
    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1].strip()
        if code == "0" and value == "SECTION":
            in_entities = (i + 2 < len(lines) and lines[i + 2].strip() == "2"
                           and lines[i + 3].strip() == "ENTITIES")
        elif code == "0" and value == "ENDSEC" and in_entities:
            return sum(len(x) for x in lines[:i])
        i += 1
    return None


def summarise(pts, start, end, thickness, fingers):
    """Measured properties of a comb, for the report and for --check."""
    sx, sy = start
    ex, ey = end
    length = math.hypot(ex - sx, ey - sy)
    ux, uy = (ex - sx) / length, (ey - sy) / length
    # signed distance from the seam line, and distance along it
    deep, along = [], []
    for x, y in pts:
        t = (x - sx) * ux + (y - sy) * uy
        along.append(t)
        deep.append(abs((x - sx) * uy - (y - sy) * ux))

    # the butt is the gap between the seam's end and the nearest point that is
    # off the seam line — NOT min(along), which is where the seam starts.
    off_seam = [t for t, d in zip(along, deep) if d > 1e-9]
    butt = min(min(off_seam), length - max(off_seam)) if off_seam else \
        min(along) if along else 0.0

    runs = {round(max(abs(b[0] - a[0]), abs(b[1] - a[1])), 4)
            for a, b in zip(pts, pts[1:])}
    diagonals = [(a, b) for a, b in zip(pts, pts[1:])
                 if abs(a[0] - b[0]) > 1e-9 and abs(a[1] - b[1]) > 1e-9]
    return {
        "fingers": fingers,
        "thickness": thickness,
        "seam_length": round(length, 4),
        "depth_max": round(max(deep), 6),
        "band": round(max(deep) - min(deep), 6),
        "used": round(max(along) - min(along), 4),
        "butt": round(butt, 4),
        "runs": sorted(runs),
        "diagonals": len(diagonals),
        "ok": max(deep) <= thickness + 1e-9 and not diagonals
              and butt >= MIN_BUTT - 1e-9,
    }


# ------------------------------------------------------------------ check

def read_combs(path):
    """Every open polyline in the file, as point lists — the combs."""
    drawing = dxf_reader.read(path)
    return [e.points for e in drawing.entities
            if e.kind in ("LWPOLYLINE", "POLYLINE") and not e.closed]


def check_file(path, thickness, tol=1e-6):
    """Measure every comb in a file against the depth rule."""
    combs = read_combs(path)
    if not combs:
        print(f"{Path(path).name}: no open polylines — no combs to check")
        return 1
    bad = 0
    for i, pts in enumerate(combs, 1):
        # the seam is the line the comb's butts sit on: use the extremes of the
        # path's own bounding box along its longer axis
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        horizontal = (max(xs) - min(xs)) >= (max(ys) - min(ys))
        if horizontal:
            seam = min(ys) if ys.count(min(ys)) > ys.count(max(ys)) else max(ys)
            deep = [abs(y - seam) for y in ys]
            length = max(xs) - min(xs)
        else:
            seam = min(xs) if xs.count(min(xs)) > xs.count(max(xs)) else max(xs)
            deep = [abs(x - seam) for x in xs]
            length = max(ys) - min(ys)
        runs = {round(max(abs(b[0] - a[0]), abs(b[1] - a[1])), 4)
                for a, b in zip(pts, pts[1:])}
        diagonals = sum(1 for a, b in zip(pts, pts[1:])
                        if abs(a[0] - b[0]) > tol and abs(a[1] - b[1]) > tol)
        depth = max(deep)
        ok = depth <= thickness + tol and diagonals == 0
        bad += 0 if ok else 1
        print(f"  comb {i}: spans {length:.2f} mm, runs {sorted(runs)} mm, "
              f"depth {depth:.4f} mm"
              + (f", {diagonals} diagonal(s)" if diagonals else ""))
        print(f"          {ok and 'ok' or 'FAIL'}"
              + ("" if ok else f" — a finger deeper than {thickness} mm, or a "
                               f"diagonal (a ramp, not a mating face)"))
    print(f"\n{'all combs within one thickness' if not bad else str(bad) + ' BAD'}")
    return 1 if bad else 0


# ------------------------------------------------------------- find seams

def _seg_len(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def straight_segments_typed(drawing):
    """Every straight segment as (start, end, kind): LINEs and unbulged polylines."""
    segs = []
    for e in drawing.entities:
        if e.kind == "LINE" and len(e.points) == 2:
            segs.append((e.points[0], e.points[1], "LINE"))
        elif e.kind in ("LWPOLYLINE", "POLYLINE") and not e.bulges \
                and len(e.points) >= 2:
            pts = list(e.points) + ([e.points[0]] if e.closed else [])
            segs += [(a, b, e.kind) for a, b in zip(pts, pts[1:])]
    return [(a, b, k) for a, b, k in segs if _seg_len(a, b) > 1e-6]


def straight_segments(drawing):
    return [(a, b) for a, b, _ in straight_segments_typed(drawing)]


def candidate_seams(drawing, ang_step=0.005, off_step=0.02, gap=0.01):
    """The drawing's maximal straight runs, longest first.

    Collinear segments that touch are merged, so a wall drawn as three LINEs is
    offered as one seam, not three. Returns a list of (start, end) pairs. This
    is how a student points at a joint: the runs are numbered by their order
    here, and `--pick N` re-derives the same list.
    """
    groups = {}
    for a, b in straight_segments(drawing):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        if ux < -1e-12 or (abs(ux) <= 1e-12 and uy < 0):
            ux, uy = -ux, -uy
        off = (-uy) * a[0] + ux * a[1]
        key = (round(math.atan2(uy, ux) / ang_step), round(off / off_step))
        groups.setdefault(key, []).append((ux, uy, off, a, b))

    seams = []
    for items in groups.values():
        ux, uy, off = items[0][0], items[0][1], items[0][2]
        spans = []
        for _, _, _, a, b in items:
            ta = a[0] * ux + a[1] * uy
            tb = b[0] * ux + b[1] * uy
            spans.append((min(ta, tb), max(ta, tb)))
        spans.sort()
        merged = []
        for lo, hi in spans:
            if merged and lo <= merged[-1][1] + gap:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            if hi - lo > 1e-6:
                seams.append(((ux * lo - uy * off, uy * lo + ux * off),
                              (ux * hi - uy * off, uy * hi + ux * off)))
    seams.sort(key=lambda s: (-_seg_len(*s), round(s[0][1], 3), round(s[0][0], 3)))
    return seams


def seam_overlap(start, end, segments, line_tol=0.05):
    """How much of the seam already lies along drawn geometry, in mm.

    A comb cut along a line that is *also* in the sketch makes the laser fire
    twice, so this is worth reporting before the student cuts.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    spans = []
    for a, b in segments:
        if abs((-uy) * (a[0] - start[0]) + ux * (a[1] - start[1])) > line_tol:
            continue
        if abs((-uy) * (b[0] - start[0]) + ux * (b[1] - start[1])) > line_tol:
            continue
        ta = (a[0] - start[0]) * ux + (a[1] - start[1]) * uy
        tb = (b[0] - start[0]) * ux + (b[1] - start[1]) * uy
        lo, hi = max(0.0, min(ta, tb)), min(length, max(ta, tb))
        if hi - lo > 1e-6:
            spans.append((lo, hi))
    spans.sort()
    merged = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return sum(hi - lo for lo, hi in merged)


PALETTE = ["#1f6fd0", "#d03f1f", "#1f9d3f", "#a02fd0",
           "#c9971f", "#0f9d9d", "#d01f7a", "#5a5ad0"]


def preview_svg(drawing, seams, title="Seams"):
    """A plain-coloured, numbered picture of the drawing's straight seams.

    This is for the eye, not the laser: the part is drawn faint grey and each
    seam in its own colour with its number at its midpoint, so a student can
    say "seam 3". Y is flipped to match Onshape (DXF is Y-up, SVG is Y-down).
    """
    pts = [p for e in drawing.entities for p in e.points]
    if not pts:
        raise dxf_reader.DxfError("no geometry to preview")
    minx = min(p[0] for p in pts)
    maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    maxy = max(p[1] for p in pts)
    m = 10.0
    pw = (maxx - minx) + 2 * m
    ph = (maxy - miny) + 2 * m

    def tx(p):
        return (p[0] - minx + m, (maxy - p[1]) + m)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{pw:.2f}mm" height="{ph:.2f}mm" '
        f'viewBox="0 0 {pw:.2f} {ph:.2f}">',
        f'<rect x="0" y="0" width="{pw:.2f}" height="{ph:.2f}" fill="#ffffff"/>',
    ]
    # faint context: every entity, tessellated
    for e in drawing.entities:
        if len(e.points) < 2:
            continue
        d = "M " + " L ".join(f"{x:.3f},{y:.3f}" for x, y in map(tx, e.points))
        if e.closed:
            d += " Z"
        out.append(f'<path d="{d}" fill="none" stroke="#c8ced8" '
                   f'stroke-width="0.5"/>')
    for i, (a, b) in enumerate(seams, 1):
        col = PALETTE[(i - 1) % len(PALETTE)]
        (x0, y0), (x1, y1) = tx(a), tx(b)
        out.append(f'<path d="M {x0:.3f},{y0:.3f} L {x1:.3f},{y1:.3f}" '
                   f'fill="none" stroke="{col}" stroke-width="1.2"/>')
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        out.append(f'<text x="{mx:.3f}" y="{my:.3f}" font-family="sans-serif" '
                   f'font-size="5" font-weight="700" fill="{col}" '
                   f'text-anchor="middle">{i}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ CLI

def open_in_browser(path):
    """Try to show `path` (an SVG) in the student's browser.

    Best effort and silent on failure: a headless or remote machine simply gets
    no window, and the caller still mentions the file path. The agent can also
    show the file in opencode's own review pane instead.
    """
    import platform
    import subprocess
    url = Path(path).resolve().as_uri()
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", url])
        elif system == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
        else:
            subprocess.Popen(["xdg-open", url])
        return True
    except Exception:
        return False


def parse_seam(text):
    parts = [p for p in text.replace(" ", "").split(",") if p]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "a seam is x0,y0,x1,y1 — for example 0,0,100,0")
    try:
        x0, y0, x1, y1 = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' has a non-number in it")
    return (x0, y0), (x1, y1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="finger-joints",
        description="Cut finger joints along the straight seams where two "
                    "shapes touch.",
    )
    ap.add_argument("dxf", help="the DXF to add joints to (or --check)")
    ap.add_argument("-o", "--output", help="where to write the jointed DXF")
    ap.add_argument("--seam", action="append", type=parse_seam, default=[],
                    metavar="x0,y0,x1,y1",
                    help="a seam to joint; repeat for more than one")
    ap.add_argument("--thickness", type=float, default=None,
                    help="the material thickness you measured, in mm — this is "
                         "the finger depth AND width")
    ap.add_argument("--fingers", type=int, default=0,
                    help="fingers per seam (default: as many as fit)")
    ap.add_argument("--side", choices=("up", "down"), default="up",
                    help="which side of the seam the fingers cut to (default up)")
    ap.add_argument("--check", action="store_true",
                    help="measure the combs already in the file instead")
    ap.add_argument("--list", action="store_true",
                    help="list the straight seams found in the drawing")
    ap.add_argument("--preview", metavar="PATH",
                    help="write a numbered picture of the seams to PATH")
    ap.add_argument("--pick", action="append", type=int, default=[], metavar="N",
                    help="joint the Nth seam from --list/--preview; repeatable")
    ap.add_argument("--keep-seam", action="store_true",
                    help="leave any line already drawn along the seam (default: "
                         "remove it, so the comb is the only cut there)")
    ap.add_argument("--open", action="store_true",
                    help="open the written file in the browser to preview it")
    args = ap.parse_args(argv)

    if args.check:
        if args.thickness is None:
            ap.error("--check needs --thickness")
        return check_file(args.dxf, args.thickness)

    if args.list or args.preview:
        try:
            drawing = dxf_reader.read(args.dxf)
        except (dxf_reader.DxfError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        found = candidate_seams(drawing)
        if not found:
            print(f"{Path(args.dxf).name}: no straight seams found")
            return 1
        if args.list:
            print(f"{len(found)} straight seam(s) in {Path(args.dxf).name}, "
                  f"longest first:")
            print(f"  {'#':>3}  {'length':>9}  {'angle':>6}  "
                  f"{'centre':>17}   from -> to")
            for i, (a, b) in enumerate(found, 1):
                ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0
                cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                print(f"  {i:>3}  {_seg_len(a, b):>8.2f}  {ang:>5.1f}°  "
                      f"({cx:>7.2f},{cy:>7.2f})   "
                      f"{a[0]:.2f},{a[1]:.2f} -> {b[0]:.2f},{b[1]:.2f}")
        if args.preview:
            try:
                Path(args.preview).write_text(
                    preview_svg(drawing, found), encoding="utf-8")
            except (dxf_reader.DxfError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"wrote a picture of {len(found)} seam(s): {args.preview}")
            if args.open:
                open_in_browser(args.preview)
        return 0

    if args.thickness is None:
        ap.error("give --thickness (the measured material)")
    if not args.output:
        ap.error("give -o/--output to write the jointed file")

    chosen = []
    if args.pick:
        try:
            drawing = dxf_reader.read(args.dxf)
            found = candidate_seams(drawing)
        except (dxf_reader.DxfError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if found:
            most = len(found)
        for n in args.pick:
            if not 1 <= n <= most:
                print(f"error: --pick {n} is out of range (1..{most})",
                      file=sys.stderr)
                return 2
            chosen.append(found[n - 1])
    chosen += list(args.seam)
    if not chosen:
        ap.error("give a seam: --pick N, --seam x0,y0,x1,y1, or --list to see them")

    seams = []
    for start, end in chosen:
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if args.thickness > length:
            print(f"error: a {args.thickness} mm finger does not fit a "
                  f"{length:.1f} mm seam", file=sys.stderr)
            return 2
        if args.fingers:
            # An explicit count is honoured or refused, never silently reduced:
            # quietly changing it would hide that the request does not fit.
            n = args.fingers
            if (2 * n - 1) * args.thickness + 2 * MIN_BUTT > length + 1e-9:
                most = max(1, int((length - 2 * MIN_BUTT + args.thickness)
                                  // (2 * args.thickness)))
                print(f"error: {n} fingers of {args.thickness} mm leave less "
                      f"than {MIN_BUTT} mm at each end of a {length:.1f} mm "
                      f"seam. At most {most} fit — use --fingers {most}.",
                      file=sys.stderr)
                return 2
        else:
            # as many as fit while leaving a real butt at each end
            n = max(1, int((length - 2 * MIN_BUTT + args.thickness)
                           // (2 * args.thickness)))
        side = 1.0 if args.side == "up" else -1.0
        seams.append((start, end, n, side))

    try:
        out, report, _, removed = add_combs(args.dxf, args.output, seams,
                                            args.thickness,
                                            replace=not args.keep_seam)
        # Warn only about geometry the joint cannot be cut cleanly through: the
        # original straight LINEs were removed, so anything still on the seam is
        # a polyline (or the original when --keep-seam). Checked on the input,
        # because the written file's comb also runs along the seam.
        typed = straight_segments_typed(dxf_reader.read(args.dxf))
        for (start, end, _, _) in seams:
            segs = [(a, b) for a, b, k in typed
                    if args.keep_seam or k != "LINE"]
            over = seam_overlap(start, end, segs)
            if over > 0.5:
                print(f"note: {over:.1f} mm of the seam {start[0]:g},{start[1]:g} "
                      f"-> {end[0]:g},{end[1]:g} still lies along drawn geometry "
                      f"— remove that in your sketch, or the laser cuts it twice.",
                      file=sys.stderr)
    except (dxf_reader.DxfError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"material thickness : {args.thickness} mm")
    if removed:
        print(f"removed            : {removed} existing seam line(s), so the "
              f"comb is cut once")
    for i, r in enumerate(report, 1):
        print(f"seam {i}: {r['seam_length']:.1f} mm, {r['fingers']} fingers of "
              f"{r['thickness']} mm, butt {r['butt']:.2f} mm each end")
        print(f"        depth max {r['depth_max']:.4f} mm, band {r['band']:.4f} mm"
              + ("  (one thickness, ok)" if r["ok"] else "  <-- VIOLATES THE DEPTH RULE"))
    print(f"wrote              : {args.output}")
    if args.open:
        # The jointed DXF's own laser-ready SVG, so what is shown is the actual
        # cut file; fall back to the DXF, then the seam picture, if conversion
        # is not possible.
        preview = None
        try:
            import laser_svg
            preview, _, _ = laser_svg.convert(args.output,
                                              Path(args.output).with_suffix(".svg"))
        except Exception:
            preview = args.output if Path(args.output).exists() else None
        if preview:
            open_in_browser(preview)
    return 0 if all(r["ok"] for r in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
