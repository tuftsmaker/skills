#!/usr/bin/env python3
"""Generate a laser-ready, finger-jointed birdhouse from its dimensions.

    python3 birdhouse.py --width 140 --depth 120 --wall-height 110 --ridge 170
    python3 birdhouse.py -w 140 -d 120 --wall-height 110 --ridge 170 --hole 35 \
        --open          # and show the SVG in the browser

What it makes
-------------
Four jointed walls, a jointed floor, and a roof of two panels that meet at a
ridge — so it has a gable, not a flat lid. One of the two side walls (the front)
carries a round entrance hole and, below it, a small perch peg slot is optional.
Everything is finger-jointed at 3 mm (the stock the Nolop store sells).

The two roof panels are held by the gable ends: each end wall is cut with a
gable (a triangle whose top matches the roof pitch), and the roof panels have a
slot that drops over it. The gable triangle also gets the entrance hole and a
carry-over of the wall jointing.

The output is one SVG of the flat panels: **pure red `#ff0000`, unfilled,
hairline**, on a millimetre page at true size, ready for the laser at Nolop.
It packs the panels to fit the bed (300 x 600 mm) and says whether they do.
"""

from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

import box as B


def _roof_panels(width, depth, wall_height, rise, thick, finger, fit, overhang):
    """The two roof slopes.

    Each slope spans half the depth (plus overhang) in the up-slope direction and
    the full roof length (width + 2*overhang) across. The slots at the top edge
    drop over the ridge; the ends fold down as small flaps that a slot in the
    gable does not use — instead the gable's triangle is what locates them.
    """
    slope = math.hypot(depth / 2.0, rise) + overhang
    roof_len = width + 2 * overhang
    return slope, roof_len


def birdhouse_panels(width, depth, wall_height, ridge, thick, finger, fit,
                     overhang=6.0):
    """Every panel of the birdhouse in assembly coordinates.

    `ridge` is the height of the roof apex above the wall tops; the roof pitch
    follows from it and half the depth. Panels are (name, [points]) and rely on
    each tab landing in a matching slot on its neighbour.
    """
    if width <= 2 * thick or depth <= 2 * thick:
        raise ValueError("width and depth must be more than twice the thickness")
    rise = ridge - wall_height
    if rise <= finger:
        raise ValueError(
            f"the roof needs a rise of more than {finger:g} mm — raise --ridge "
            f"above the wall height plus that")

    inner_w = width - 2 * thick          # between the two side walls
    inner_d = depth - 2 * thick          # between front and back
    fx = [(thick + a, thick + b) for a, b in B.finger_intervals(inner_w, finger)]
    fd = [(thick + a, thick + b) for a, b in B.finger_intervals(inner_d, finger)]
    fh = B.finger_intervals(wall_height, finger)

    def slots(iv):
        """Widen a tab interval into a slot that clears it by `fit`."""
        return [(a - fit / 2.0, b + fit / 2.0) for a, b in iv]

    panels = []

    # Floor: tabs on all four edges, sitting inside the walls.
    floor = []
    floor += B.combed_edge((thick, thick), (width - thick, thick), (0, -1),
                           fx, thick, finger, "tab", fit)
    floor += B.combed_edge((width - thick, thick), (width - thick, depth - thick),
                           (1, 0), fd, thick, finger, "tab", fit)
    floor += B.combed_edge((width - thick, depth - thick), (thick, depth - thick),
                           (0, 1), fx, thick, finger, "tab", fit)
    floor += B.combed_edge((thick, depth - thick), (thick, thick), (-1, 0),
                           fd, thick, finger, "tab", fit)
    panels.append(("floor", B._dedupe(floor)))

    # Gable end walls: full width, gable triangle on top, slots on the bottom
    # (for the floor) and slots on both ends (the front and back walls' tabs
    # seat here). These two are identical, cut twice.
    for name in ("gable-a", "gable-b"):
        wall = []
        wall += B.combed_edge((0, 0), (width, 0), (0, -1),
                              slots(fx), thick, finger, "slot", fit)
        wall += B.combed_edge((width, 0), (width, wall_height), (1, 0),
                              slots(fh), thick, finger, "slot", fit)
        wall += [(width, wall_height), (width / 2.0, ridge), (0.0, wall_height)]
        wall += B.combed_edge((0, wall_height), (0, 0), (-1, 0),
                              slots(fh), thick, finger, "slot", fit)
        panels.append((name, B._dedupe(wall)))

    # Front and back walls: they sit between the gables, so they run from
    # `thick` to `depth - thick` and their end edges carry tabs into the gables'
    # end slots. The front also carries the entrance hole (added in `build`).
    for name in ("front", "back"):
        wall = []
        wall += B.combed_edge((thick, 0), (depth - thick, 0), (0, -1),
                              slots(fd), thick, finger, "slot", fit)
        wall += B.combed_edge((depth - thick, 0), (depth - thick, wall_height),
                              (1, 0), fh, thick, finger, "tab", fit)
        wall += [(depth - thick, wall_height), (thick, wall_height)]
        wall += B.combed_edge((thick, wall_height), (thick, 0), (-1, 0),
                              fh, thick, finger, "tab", fit)
        panels.append((name, B._dedupe(wall)))

    return panels, rise, {}


def entrance_circle(width, depth, wall_height, ridge, diameter, thick):
    """The entrance hole as a circle on the front wall, and its centre.

    Placed on the wall's centreline, about two diameters up from the floor so
    there is room below it, and never so high it breaks into the gable.
    """
    r = diameter / 2.0
    cx = depth / 2.0
    cy = max(r + 2 * thick, wall_height - diameter * 1.1)
    if cy + r > wall_height - 2 * thick:
        cy = wall_height - 2 * thick - r
    return (cx, cy, r)


def circle_path(cx, cy, r, segments=64):
    pts = []
    for i in range(segments):
        t = 2 * math.pi * i / segments
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    pts.append(pts[0])
    return pts


# ---------------------------------------------------------------- engraving
#
# Engraved text is a *raster* on the laser, not a cut: UCP rasters everything
# that is not red (or blue), and the class guide shows "a black engraved image"
# loaded on the work plane. So the mark is rendered to a small black-on-white
# bitmap with Pillow and embedded in the SVG as a data-URI <image> — the exact
# thing UCP expects, using a real font instead of hand-drawn strokes.
#
# Pillow and a TrueType font are the only non-stdlib dependencies in the skill;
# SKILL.md says so. A font is optional: the code searches a short list of
# common system fonts and reports clearly if none is found.

_FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def find_font(explicit=None):
    """The first usable TrueType font, or `explicit` when given."""
    from pathlib import Path
    if explicit:
        if not Path(explicit).exists():
            raise FileNotFoundError(f"no font at {explicit}")
        return explicit
    for cand in _FONT_CANDIDATES:
        if Path(cand).exists():
            return cand
    raise FileNotFoundError(
        "no TrueType font found; pass --font /path/to/font.ttf")


def render_text_png(text, height_mm, dpi=1000, font=None, margin_mm=0.5):
    """Render `text` to a black-on-white PNG sized in millimetres.

    Returns (png_bytes, width_mm, height_mm). `dpi` sets the raster resolution:
    fine enough that the engraved edges are clean when UCP rasters the image.
    The image is a *mask*: UCP rasters the black and ignores white, so the white
    background is not engraved.

    Pillow does the rendering. Run this script with the class sandbox Python
    (`ensure-runtime.sh` prints the path), which has Pillow; if some other
    interpreter is used anyway, `env.python_with` hands the rendering to the
    sandbox and reads the PNG back. Nothing is installed into any other Python.
    """
    import io
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        # Hand the actual rendering to an interpreter that has Pillow, and read
        # back the PNG and its size. Keeps this process's own imports untouched.
        import json
        import tempfile
        import env
        python = env.python_with(["PIL"])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "text.png"
            code = (
                "import json,sys\n"
                "sys.path.insert(0, {here!r})\n"
                "import birdhouse\n"
                "png, w, h = birdhouse.render_text_png(\n"
                "    {text!r}, {height!r}, dpi={dpi!r}, font={font!r},\n"
                "    margin_mm={margin!r})\n"
                "open({out!r}, 'wb').write(png)\n"
                "print(json.dumps([w, h]))\n"
            ).format(here=str(Path(__file__).resolve().parent), text=text,
                     height=height_mm, dpi=dpi, font=font, margin=margin_mm,
                     out=str(out))
            res = subprocess.run([python, "-c", code], check=True,
                                 capture_output=True, text=True)
            w, h = json.loads(res.stdout.strip().splitlines()[-1])
            return out.read_bytes(), w, h

    px_per_mm = dpi / 25.4
    # Start with a nominal pixel size, then measure and set the final canvas so
    # the text is exactly `height_mm` tall.
    fontpath = find_font(font)
    probe = ImageFont.truetype(fontpath, 200)
    box = probe.getbbox(text)                    # (l, t, r, b) at 200 px
    glyph_h = max(1, box[3] - box[1])
    px_size = max(8, int(round(200 * (height_mm * px_per_mm) / glyph_h)))
    f = ImageFont.truetype(fontpath, px_size)

    box = f.getbbox(text)
    pad = int(round(margin_mm * px_per_mm))
    w = (box[2] - box[0]) + 2 * pad
    h = (box[3] - box[1]) + 2 * pad
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    draw.text((pad - box[0], pad - box[1]), text, font=f, fill=0)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), w / px_per_mm, h / px_per_mm


def _flip_y(points, top):
    """Mirror a panel about `top`.

    The panels are generated Y-up (floor at y=0, roof above). SVG here draws
    Y-down, which renders a gable as a downward V, so each panel is reflected
    about its own top before it is written. A reflection preserves every length
    and every mating edge, so the cut parts are unchanged; only the picture reads
    the right way up.
    """
    return [(x, top - y) for x, y in points]


def build(width, depth, wall_height, ridge, thick, finger, fit, hole,
          overhang=6.0, engrave=None, font=None):
    """All panels plus the roof, laid out as (placed, page_w, page_h, notes)."""
    panels, rise, _ = birdhouse_panels(width, depth, wall_height, ridge, thick,
                                       finger, fit, overhang)

    # Roof: two identical slopes. Each spans the roof length across and the
    # up-slope distance top to bottom, with a small flap that folds over the
    # ridge so the two meet.
    slope = math.hypot(depth / 2.0, rise) + overhang
    roof_len = width + 2 * overhang
    for name in ("roof-a", "roof-b"):
        panel = [(0.0, 0.0), (roof_len, 0.0), (roof_len, slope),
                 (0.0, slope)]
        panels.append((name, B._dedupe(panel)))

    # Entrance hole and the engraved mark: both belong to the front wall, so
    # they are sub-paths/images of that panel, not separate pieces on the sheet.
    notes = []
    front_subs = []
    front_engrave = None
    if hole and hole > 0:
        cx, cy, r = entrance_circle(width, depth, wall_height, ridge, hole, thick)
        notes.append(f"entrance hole: {hole:g} mm diameter on the front wall")
        front_subs.append(circle_path(cx, cy, r))
    if engrave:
        text_h = min(12.0, max(6.0, (hole or 20) * 0.4))
        avail = depth - 2 * thick - 4
        png, tw, th = render_text_png(engrave, text_h, font=font)
        if tw > avail:                      # scale the image to fit the panel
            s = avail / tw
            tw, th = tw * s, th * s
        tx = (depth - tw) / 2.0
        ty = (cy - r - 2 * thick - th) if (hole and hole > 0) else (2 * thick)
        if ty < 1.5 * thick:
            ty = 1.5 * thick
        if tx < thick:
            tx = thick
        front_engrave = (png, tx, ty, tw, th)
        notes.append(f"engraved on the front: {engrave!r}, {th:.1f} mm tall"
                     + (" below the hole" if hole and hole > 0 else ""))
    if front_subs or front_engrave:
        panels = [
            (name, (pts, front_subs, front_engrave)) if name == "front"
            else (name, pts)
            for name, pts in panels
        ]

    # Lay out by outline, then carry each panel's sub-paths and engraving along
    # with the same translation, so the hole and the mark stay on the panel.
    placed, page_w, page_h = B.layout(
        [(n, p[0] if isinstance(p, tuple) else p) for n, p in panels])
    out = []
    for (name, shape), (_, pts) in zip(panels, placed):
        base = shape[0] if isinstance(shape, tuple) else shape
        dx = min(q[0] for q in pts) - min(q[0] for q in base)
        dy = min(q[1] for q in pts) - min(q[1] for q in base)
        if isinstance(shape, tuple):
            outline, subs, eng = shape
            moved_eng = None
            if eng:
                png, ex, ey, ew, eh = eng
                moved_eng = (png, ex + dx, ey + dy, ew, eh)
            out.append((name, (B.translate(outline, dx, dy),
                               [B.translate(s, dx, dy) for s in subs],
                               moved_eng)))
        else:
            out.append((name, pts))
    return out, page_w, page_h, notes, slope, roof_len


def svg(placed, page_w, page_h):
    """One SVG: red hairlines cut the panels, a black image engraves the text.

    A panel may carry sub-paths (the entrance hole) and an engraved raster (the
    class mark); the hole is a red cut loop inside the panel's outline, and the
    mark is a black PNG the laser rasters. The whole page is reflected once
    about its own height, so the gable reads as a peak; a reflection preserves
    every length and mating edge.
    """
    import base64

    def loop(pts):
        return "M " + " L ".join(f"{x:.4f},{y:.4f}" for x, y in pts) + " Z"

    def flip(pts):
        return [(x, page_h - y) for x, y in pts]

    paths = []
    for _, pts in placed:
        eng = None
        if isinstance(pts, tuple):
            outline, subs, eng = pts
            d = loop(flip(outline)) + " " + " ".join(loop(flip(s)) for s in subs)
        else:
            d = loop(flip(pts))
        paths.append(f'  <path d="{d}" style="{B.HAIRLINE}"/>')
        if eng:
            png, ex, ey, ew, eh = eng
            # The raster is already the right way up, so it is placed after the
            # page flip: SVG image y is measured from the top.
            top = page_h - (ey + eh)
            b64 = base64.b64encode(png).decode("ascii")
            paths.append(
                f'  <image x="{ex:.4f}" y="{top:.4f}" width="{ew:.4f}" '
                f'height="{eh:.4f}" preserveAspectRatio="none" '
                f'xlink:href="data:image/png;base64,{b64}" '
                f'xmlns:xlink="http://www.w3.org/1999/xlink"/>')
    body = "\n".join(paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Laser-ready cut file: pure red (#ff0000) hairlines, no fill;\n"
        "     the black image is what the laser rasters (engraves). -->\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{page_w:.3f}mm" height="{page_h:.3f}mm" '
        f'viewBox="0 0 {page_w:.3f} {page_h:.3f}">\n'
        f"{body}\n</svg>\n"
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="birdhouse",
        description="Generate a laser-ready, finger-jointed birdhouse "
                    "(jointed walls and floor, two-panel gable roof, round "
                    "entrance hole).",
    )
    p.add_argument("--width", "-w", type=float, default=130.0,
                   help="outside width across the gable, in mm (default 130)")
    p.add_argument("--depth", "-d", type=float, default=110.0,
                   help="outside depth front to back, in mm (default 110)")
    p.add_argument("--wall-height", type=float, default=110.0,
                   help="height to the top of the walls, in mm (default 110)")
    p.add_argument("--ridge", type=float, default=160.0,
                   help="height of the roof apex above the floor, in mm "
                        "(default 160)")
    p.add_argument("--thickness", "-t", type=float, default=B.NOLOP_THICKNESS,
                   help=f"material thickness in mm (default "
                        f"{B.NOLOP_THICKNESS:g}, the Nolop stock)")
    p.add_argument("--finger", type=float, default=None,
                   help="finger width in mm (default: the material thickness)")
    p.add_argument("--fit", type=float, default=0.1,
                   help="kerf clearance added to every slot, in mm (default 0.1)")
    p.add_argument("--hole", type=float, default=35.0,
                   help="entrance hole diameter in mm (0 for none; default 35)")
    p.add_argument("--engrave", nargs="?", const="ENT-164", default=None,
                   metavar="TEXT",
                   help="text to raster-engrave on the front, below the hole "
                        "(default 'ENT-164' when given without a value)")
    p.add_argument("--overhang", type=float, default=6.0,
                   help="roof overhang past the walls, in mm (default 6)")
    p.add_argument("--font", default=None, metavar="PATH",
                   help="TrueType font for the engraved text (default: a common "
                        "system font)")
    p.add_argument("-o", "--output", default="birdhouse-laser-ready.svg",
                   help="where to write the SVG")
    p.add_argument("--open", action="store_true",
                   help="open the written SVG in the browser to preview it")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    finger = args.finger if args.finger else args.thickness
    if args.thickness <= 0 or args.fit < 0:
        print("error: thickness must be positive and fit non-negative")
        return 2

    try:
        placed, page_w, page_h, notes, slope, roof_len = build(
            args.width, args.depth, args.wall_height, args.ridge,
            args.thickness, finger, args.fit, args.hole, args.overhang,
            args.engrave, args.font)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}")
        return 2

    out = Path(args.output)
    if out.parent != Path(""):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg(placed, page_w, page_h), encoding="utf-8")

    names = ", ".join(name for name, _ in placed)
    print(f"birdhouse  : {args.width:g} x {args.depth:g} x {args.ridge:g} mm "
          f"(walls {args.wall_height:g}, ridge {args.ridge:g}), "
          f"{args.thickness:g} mm material")
    print(f"roof       : pitch over {args.depth / 2:.0f} mm rise "
          f"{args.ridge - args.wall_height:.0f} mm, each slope {slope:.1f} x "
          f"{roof_len:.1f} mm")
    print(f"panels     : {len(placed)} ({names})")
    for n in notes:
        print(f"note       : {n}")
    print(f"page       : {page_w:.1f} x {page_h:.1f} mm")
    ok, msg = B.fits_bed(page_w, page_h)
    print(f"{'bed        : ' if ok else 'CHECK      : '}{msg}")
    print(f"wrote      : {out}")
    if args.open:
        import platform
        import subprocess
        url = Path(out).resolve().as_uri()
        try:
            subprocess.Popen(
                ["open", url] if platform.system() == "Darwin"
                else ["cmd", "/c", "start", "", url] if platform.system() == "Windows"
                else ["xdg-open", url])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
