"""The criterion checks.

Each check is a plain function `fn(ctx, **args) -> CheckResult`. They only look
at the submission and the task definition — never the network, never the
clock — so the same call gives the same answer on a student's laptop and on the
grader.

`ctx` carries the parsed drawing (if any), the submission, the task and the
manifest values.
"""

from __future__ import annotations

import math
import re

from geom import Profile, dist, reflex_ratio, symmetry_error
from report import failed, needs_review, passed

# The Nolop laser cutter: 60 W, 12x24 in bed, cuts up to ~3 mm.
BED_W = 300.0
BED_H = 600.0

# A 3 mm sheet cut on the Nolop laser needs roughly this much material left.
# Two adjacent cut paths closer than the kerf will not leave a usable wall.
KERF = 3.0
MIN_WEB = 3.0

MATERIAL_TOL = 0.35  # 3 mm plywood is rarely exactly 3.00 mm


class CheckError(Exception):
    """A check that cannot run (missing file, unreadable drawing)."""


# ---------------------------------------------------------------- file level


def file_present(ctx, name, required=True):
    if ctx.submission.has(name):
        return passed(f"{name} is there")
    if required:
        return failed(f"{name} is missing.", f"Add {name} to your submission folder.")
    return passed(f"{name} not required")


def dxf_parses(ctx, max_mb=5.0):
    if ctx.drawing is None:
        if ctx.dxf_path is None:
            return failed("No DXF file in the submission.", "Export your sketch as DXF (right-click the sketch → Export as DXF).")
        return failed(
            f"{ctx.dxf_path.name} could not be read as a DXF.",
            "Re-export from Onshape: right-click the committed sketch in the feature list → Export as DXF/DWG, keep the default settings, and save.",
        )
    size_mb = ctx.dxf_path.stat().st_size / 1e6 if ctx.dxf_path else 0
    n = len(ctx.drawing.entities)
    if size_mb > max_mb:
        return failed(
            f"The file is {size_mb:.1f} MB — far larger than a sketch export.",
            "A sketch DXF is well under a megabyte. You probably exported a drawing or an "
            "image instead: export the sketch itself and check the file size.",
        )
    return passed(f"{ctx.dxf_path.name} reads as a DXF: {n} entities", entities=n)


def dxf_layer_name(ctx, expected):
    """Onshape exports sketches on a known layer; a different one suggests a
    hand-made or converted file."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    layers = ctx.drawing.layers()
    if not layers:
        return failed("The DXF has no layers.")
    if expected in layers:
        return passed(f"sketch geometry is on layer {expected}", layers=list(layers))
    main = max(layers, key=layers.get)
    return needs_review(
        f"Geometry is on layer '{main}', not Onshape's usual '{expected}' ({layers}).",
        layers=list(layers),
    )


# ---------------------------------------------------------------- units


def dxf_units_detect(ctx):
    """Onshape's DXF export writes no $INSUNITS, so infer the unit from the
    file's own scale and say what was found. The drawing is checked against the
    task's stated dimensions next, which is what actually catches a unit
    mistake."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    declared = ctx.drawing.header.get("$INSUNITS")
    if declared is not None:
        mapping = {"1": "in", "2": "ft", "4": "mm", "5": "cm", "6": "m"}
        unit = mapping.get(str(int(float(declared))), f"code {declared}")
        return passed(f"File declares units: {unit}", declared=unit)
    return passed(
        "No units declared in the file (normal for Onshape) — units are checked against the stated size instead.",
        declared=None,
    )


# ---------------------------------------------------------------- geometry


def _vertex_degrees(drawing, tol=0.05):
    """How many segment-ends meet at each snapped point.

    A properly closed drawing has no vertex of degree 1: every line end meets
    another line end. This is the signal that survives every export format, so
    it is what "the paths close" means here.
    """
    import collections

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    deg = collections.Counter()
    for e in drawing.entities:
        if e.is_circle or (e.closed and len(e.points) > 2):
            continue
        if len(e.points) < 2:
            continue
        deg[key(e.points[0])] += 1
        deg[key(e.points[-1])] += 1
    return deg


def dxf_all_paths_closed(ctx, tol=0.05, max_dangling=0):
    """Every cut line must end somewhere another line begins.

    A line that stops in mid-air reaches the laser as a cut that stops in
    mid-air. This is the check that catches both a corner that does not join
    and a line that was never meant to be cut.
    """
    if ctx.drawing is None:
        return failed("No DXF to check.")
    deg = _vertex_degrees(ctx.drawing, tol)
    dangling = [k for k, v in deg.items() if v == 1]
    if len(dangling) <= max_dangling:
        return passed(f"every line end meets another ({len(ctx.drawing.entities)} entities)")
    return failed(
        f"{len(dangling)} line end(s) stop in mid-air, with nothing to meet.",
        "Two causes, same fix. Either a corner does not quite join — zoom in on "
        "Onshape and drag the endpoints together until the dot goes yellow — or the "
        "line was only ever a guide, in which case select it and press Q to make it a "
        "construction line so it is not exported at all.",
        dangling=len(dangling),
    )


def dxf_no_construction_lines(ctx):
    """Guides are not cut. Onshape leaves construction lines out of the DXF, so
    a line in the file is real geometry — unless it is a genuine guide that got
    drawn as a line, which is a judgement call for a person."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    deg = _vertex_degrees(ctx.drawing)
    dangling = [k for k, v in deg.items() if v == 1]
    if not dangling:
        return passed("nothing in the file that is not part of a shape", free_lines=0)
    # Runs that are long and straight, spanning the drawing, read as guides.
    spans = []
    bounds = ctx.drawing.bounds()
    for points, _indexes in ctx.drawing.open_shapes():
        if len(points) < 2:
            continue
        if dist(points[0], points[-1]) < 1.0 and len(points) > 3:
            continue  # nearly closed; that is the closed check's job, not this one
        length = _polyline_length(points)
        if bounds:
            span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
            if length > 0.6 * span:
                spans.append(length)
    if spans:
        return needs_review(
            f"{len(spans)} line(s) run right across the drawing — guides, most likely.",
            free_lines=len(spans),
        )
    return passed("no guide-shaped lines in the file", free_lines=0)


def _polyline_length(points) -> float:
    return sum(dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def dxf_outer_dims(ctx, width=None, height=None, tol=0.25):
    """The overall size of the drawing, which is how a unit mistake shows up."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    bounds = ctx.drawing.bounds()
    if bounds is None:
        return failed("The DXF has no geometry.")
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    problems = []
    if width is not None and abs(w - width) > tol:
        problems.append(f"width is {w:.1f} mm, expected {width:.0f} mm")
    if height is not None and abs(h - height) > tol:
        problems.append(f"height is {h:.1f} mm, expected {height:.0f} mm")
    if not problems:
        return passed(f"drawing measures {w:.2f} × {h:.2f} mm", width=round(w, 3), height=round(h, 3))
    if width and w > width * 8:
        hint = ("That is off by a factor of about 25 — the export is probably in inches "
                "or points, not millimetres. In Onshape check the document units (top-right "
                "menu → Units → millimetre) and export again.")
    else:
        hint = "Change the dimension in the sketch (double-click the number) and export again."
    return failed("; ".join(problems) + ".", hint, width=round(w, 3), height=round(h, 3))


def dxf_bounds_mm(ctx, max_w=None, max_h=None, margin=0.0):
    if ctx.drawing is None:
        return failed("No DXF to check.")
    bounds = ctx.drawing.bounds()
    if bounds is None:
        return failed("The DXF has no geometry.")
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    max_w = max_w or BED_W
    max_h = max_h or BED_H
    fits = w <= max_w - margin and h <= max_h - margin
    rotated = h <= max_w - margin and w <= max_h - margin
    if fits:
        return passed(f"{w:.0f} × {h:.0f} mm fits the {BED_W:.0f} × {BED_H:.0f} mm bed", width=round(w, 2), height=round(h, 2))
    if rotated:
        return passed(f"{w:.0f} × {h:.0f} mm fits the bed when rotated", width=round(w, 2), height=round(h, 2))
    return failed(
        f"{w:.0f} × {h:.0f} mm is larger than the laser bed ({BED_W:.0f} × {BED_H:.0f} mm).",
        "Scale the part down or split it into pieces that each fit. A part laid out "
        "diagonally only wastes material — rotate it straight first.",
        width=round(w, 2), height=round(h, 2),
    )


def dxf_profiles(ctx, min_count=1, max_count=None):
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    if len(profs) < min_count:
        return failed(
            f"Found {len(profs)} closed shape(s); the task needs at least {min_count}.",
            "Check for a gap in the outline: in Onshape, look for a white (not shaded) "
            "region inside your sketch — an unclosed profile shows as an open area.",
            profiles=len(profs),
        )
    if max_count is not None and len(profs) > max_count:
        return failed(
            f"Found {len(profs)} closed shapes; the task expects {max_count}.",
            "Extra closed shapes reach the laser as extra cuts. Delete the ones you "
            "don't want, or check you did not leave a stray rectangle behind.",
            profiles=len(profs),
        )
    return passed(f"{len(profs)} closed shape(s)", profiles=len(profs))


def dxf_circle_count(ctx, count, tol=0.05):
    if ctx.drawing is None:
        return failed("No DXF to check.")
    circles = [p for p in ctx.drawing.profiles() if p.is_round]
    if len(circles) == count:
        return passed(f"{count} circular hole(s) found", circles=len(circles))
    return failed(
        f"Found {len(circles)} circle(s); the task needs {count}.",
        "Draw the hole with the Center point circle tool and make sure it is inside "
        "the outline. A circle that crosses an edge is not a hole, it is a notch.",
        circles=len(circles),
    )


def dxf_circle_diameter(ctx, diameter, tol=0.2):
    if ctx.drawing is None:
        return failed("No DXF to check.")
    circles = [p for p in ctx.drawing.profiles() if p.is_round]
    if not circles:
        return failed("No circle in the drawing.", "Draw the hole with the circle tool.")
    got = circles[0].diameter
    if abs(got - diameter) <= tol:
        return passed(f"hole diameter {got:.2f} mm", diameter=round(got, 3))
    hint = "Double-click the circle's dimension and type the value the task asks for."
    if abs(got / 25.4 - diameter) <= tol or abs(got * 25.4 - diameter) <= tol:
        hint = ("That is off by a factor of about 25 — the file is probably in inches. "
                "Set the document units to millimetre and export again.")
    return failed(f"hole diameter is {got:.2f} mm, expected {diameter:.0f} mm.", hint, diameter=round(got, 3))


def dxf_circle_position(ctx, from_corner=None, from_edges=None, tol=0.3):
    """Where the hole sits: a distance from a corner, or a pair of edge
    distances, measured to the nearest outline edge."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    if not circles:
        return failed("No circle in the drawing.", "Draw the hole with the circle tool.")
    outer = _outer_profile(profs, circles)
    if outer is None:
        return failed("Could not identify the outer outline.")
    centre = circles[0].centre

    bounds = outer.bbox
    if from_corner is not None:
        x0, y0, x1, y1 = bounds
        corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
        measured = min(math.hypot(centre[0] - cx, centre[1] - cy) for cx, cy in corners)
        # A hole anchored to a corner with an equal x/y offset: check both legs.
        near = min(corners, key=lambda c: math.hypot(centre[0] - c[0], centre[1] - c[1]))
        legs = (abs(centre[0] - near[0]), abs(centre[1] - near[1]))
        if abs(measured - from_corner) <= tol:
            return passed(
                f"hole centre is {measured:.2f} mm from the nearest corner",
                distance=round(measured, 3),
            )
        return failed(
            f"hole centre is {measured:.2f} mm from the nearest corner; the task asks for "
            f"{from_corner:.0f} mm.",
            f"Anchor the hole with dimensions from both edges meeting that corner "
            f"({legs[0]:.1f} and {legs[1]:.1f} mm at the moment). Use a construction line "
            "from the corner, then dimension the circle from the two edges.",
            distance=round(measured, 3),
        )

    if from_edges is not None:
        x0, y0, x1, y1 = bounds
        dx = min(centre[0] - x0, x1 - centre[0])
        dy = min(centre[1] - y0, y1 - centre[1])
        want_x, want_y = from_edges
        if abs(dx - want_x) <= tol and abs(dy - want_y) <= tol:
            return passed(f"hole is {dx:.2f} mm from the left/right edge and {dy:.2f} mm from the near edge")
        return failed(
            f"hole sits {dx:.2f} mm from the nearest vertical edge and {dy:.2f} mm from the "
            f"nearest horizontal edge; the task asks for {want_x:.0f} and {want_y:.0f} mm.",
            "Dimension the circle's centre to both edges and type the two numbers. "
            "Snap to the edges so the dimension binds to the outline.",
        )

    # no expected position given: report where it is
    bounds_ = outer.bbox
    centre_of_outer = ((bounds_[0] + bounds_[2]) / 2, (bounds_[1] + bounds_[3]) / 2)
    return passed(
        f"hole centre is at ({centre[0]:.1f}, {centre[1]:.1f}) mm",
        centre=[round(centre[0], 3), round(centre[1], 3)],
    )


def dxf_circle_centred(ctx, tol=0.3):
    """The hole sits at the centre of the outline."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    if not circles:
        return failed("No circle in the drawing.", "Draw the hole with the circle tool.")
    outer = _outer_profile(profs, circles)
    if outer is None:
        return failed("Could not identify the outer outline.")
    x0, y0, x1, y1 = outer.bbox
    want = ((x0 + x1) / 2, (y0 + y1) / 2)
    got = circles[0].centre
    off = math.hypot(got[0] - want[0], got[1] - want[1])
    if off <= tol:
        return passed(f"hole is centred ({off:.2f} mm off centre)", offset=round(off, 3))
    return failed(
        f"hole centre is {off:.2f} mm off the centre of the outline.",
        "Find the centre with two construction lines (one from each pair of midpoints), "
        "then place the circle on the crossing point. Onshape shows a small square when "
        "you hover the midpoint — that is what you want to snap to.",
        offset=round(off, 3),
    )


def dxf_aspect(ctx, width=1.0, height=1.0, tol=0.15):
    """The outline's width:height ratio — catches a 'square' that is not one."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    outer = _outer_profile(profs, circles)
    if outer is not None:
        got_w, got_h = outer.width, outer.height
        how = f"outline is {got_w:.1f} × {got_h:.1f} mm"
    else:
        # No closed outline: report what is there and leave the diagnosis to
        # the check that owns it ("the outline is closed").
        bounds = ctx.drawing.bounds()
        if bounds is None:
            return failed("The DXF has no geometry.")
        got_w, got_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        how = f"the drawing spans {got_w:.1f} × {got_h:.1f} mm (not a closed outline yet)"
    ratio = got_w / got_h if got_h else float("inf")
    want = width / height
    if abs(ratio - want) <= tol:
        return passed(how)
    return failed(
        f"{how}; the task asks for {width:.0f} × {height:.0f}.",
        "Dimension both sides of the rectangle and check the two numbers.",
    )


def dxf_dimensions_are_driven(ctx, expect=(100.0, 60.0), tol=0.25):
    """The sketch matches the dimensions the task states. (Named for what it
    means to the student: the numbers in the file are the numbers asked for.)"""
    return dxf_outer_dims(ctx, width=expect[0], height=expect[1], tol=tol)


def dxf_min_web(ctx, minimum=MIN_WEB, kerf=KERF):
    """Material left between the hole and the outside edge.

    Measured rim-to-edge, which is what actually survives the cut: the hole's
    centre may sit 20 mm from an edge, but a 10 mm hole leaves 15 mm of wall.
    A wall thinner than the kerf falls out.
    """
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    if not circles:
        return passed("no hole to check against the outline", min_web=None)
    outer = _outer_profile(profs, circles)
    if outer is None:
        return failed("Could not identify the outer outline.")

    worst = None
    for hole in circles:
        rim_to_edge = outer.edge_clearance(hole)
        if rim_to_edge <= 0.01:
            return failed(
                "a hole touches the outside edge — that is a notch, not a hole.",
                "Move the hole inward so the whole circle is inside the outline, with "
                "at least a few millimetres of material around it.",
                min_web=round(rim_to_edge, 2),
            )
        worst = rim_to_edge if worst is None else min(worst, rim_to_edge)

    if worst >= kerf:
        return passed(f"thinnest wall around the hole is {worst:.1f} mm", min_web=round(worst, 2))
    return failed(
        f"only {worst:.1f} mm of material between the hole and the outside edge.",
        f"The laser burns about {kerf:.0f} mm wide, so a wall thinner than that falls "
        "apart. Move the hole inward or make it smaller.",
        min_web=round(worst, 2),
    )


def dxf_symmetry(ctx, axis="x", tol=0.25):
    """The outline is symmetric about its own centre — the mirror-tool task."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    outer = _outer_profile(profs, circles)
    if outer is None:
        return failed("Could not identify the outer outline.")
    err = symmetry_error(outer.points, axis, tol)
    if err <= tol:
        return passed(f"outline is symmetric across the {axis}-axis", error=round(err, 3))
    return failed(
        f"the halves are not mirror images of each other ({err:.2f} mm apart on the "
        f"{axis}-axis).",
        "Draw one half, then use the Mirror tool: pick the centre line first, then the "
        "edges to reflect. The mirrored side follows the original, so they can never "
        "drift apart.",
        error=round(err, 3),
    )


def dxf_text_or_annotations(ctx):
    """A drawing with title block, dimensions or notes exported by mistake."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    if ctx.drawing.skipped:
        kinds = ", ".join(sorted(ctx.drawing.skipped))
        return needs_review(
            f"The file contains {kinds}, which a sketch export normally does not.",
            skipped=dict(ctx.drawing.skipped),
        )
    return passed("no annotations or extra entity types", skipped={})


# ---------------------------------------------------------------- manifest


def manifest_field(ctx, field, pattern=None, present=True, hint=""):
    value = (ctx.manifest or {}).get(field)
    if not value:
        if present:
            return failed(
                f"manifest.md does not say '{field}'.",
                hint or f"Add a line to manifest.md: {field}: <value>",
            )
        return passed(f"'{field}' not given")
    if pattern and not re.search(pattern, value):
        return needs_review(
            f"manifest 'field' value is '{value}', which does not look right.",
            value=value,
        )
    return passed(f"{field}: {value}", value=value)


def manifest_material_thickness(ctx, expected=3.0, tol=MATERIAL_TOL):
    value = (ctx.manifest or {}).get("material_thickness")
    if not value:
        return failed(
            "manifest.md does not state the material thickness.",
            "Measure the sheet with calipers and write it in: material_thickness: 3.15",
        )
    try:
        mm = float(re.sub(r"[^0-9.]", "", value))
    except ValueError:
        return needs_review(f"could not read a thickness from '{value}'", value=value)
    if abs(mm - expected) <= tol:
        return passed(f"material thickness {mm} mm, close to the {expected} mm stock")
    return failed(
        f"manifest states {mm} mm material; the class stock is {expected} mm.",
        "Re-measure with calipers — plywood is sold as '3 mm' but varies. Then redo the "
        "finger joints at the thickness you measured.",
        thickness=mm,
    )


def manifest_source_link(ctx, field="onshape_url"):
    value = (ctx.manifest or {}).get(field)
    if not value:
        return failed(
            "manifest.md does not give the Onshape link.",
            "In Onshape, click Share, set the link to 'can view', and add one line to "
            "manifest.md: onshape_url: https://cad.onshape.com/documents/...",
        )
    if "onshape.com/documents/" not in value:
        return needs_review(
            f"'{value}' is not an Onshape document link.",
            value=value,
        )
    return needs_review(
        "link recorded — a person opens it to confirm the sketch is yours and committed.",
        value=value,
    )


# ------------------------------------------------------------ laser SVG
#
# The DXF checks above cannot see colour — a DXF has none. The file that goes
# to the laser is the SVG, and *its* checks are where colour lives: red
# hairlines cut, black (or nothing) is an etch, anything else rasters.
#
# Both producers of that file are accepted: the checker's own --svg converter
# writes inline styles on each path, and Inkscape keeps them there too, so the
# checks walk the document and resolve style through ancestors the way SVG
# does, skipping <defs> (not drawn).

_SVG_DRAW = {"path", "rect", "circle", "ellipse", "line", "polyline",
             "polygon", "text"}
_SVG_RED = {"#ff0000", "red"}
_SVG_BLACK = {"#000000", "black"}
# An unfilled element is correct, not a defect: a cut path must have no fill at
# all (the guide's "set the fill to No paint"), so `fill:none` is what every
# good cut line carries. Omitting it from the allowed set failed the checker's
# own --svg output.
_SVG_NO_FILL = {"none", "", "transparent"}


def _svg_submission(ctx):
    """(path, parsed root) for the submitted laser-ready SVG."""
    import xml.etree.ElementTree as ET

    path = ctx.submission.find("part-laser-ready.svg", "laser-ready.svg")
    if path is None:
        return None, None
    try:
        return path, ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return path, None


def _svg_local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _svg_style(el) -> dict:
    """An element's own style declarations plus presentation attributes."""
    out = {}
    for decl in (el.get("style") or "").split(";"):
        if ":" in decl:
            key, value = decl.split(":", 1)
            out[key.strip().lower()] = value.strip().lower()
    for key in ("stroke", "fill", "stroke-width", "stroke-opacity"):
        if el.get(key):
            out.setdefault(key, el.get(key).strip().lower())
    return out


def svg_parses(ctx):
    path, root = _svg_submission(ctx)
    if path is None:
        return failed(
            "No part-laser-ready.svg in the submission.",
            "The laser reads SVG, not DXF. In Inkscape: File → Save As… → Inkscape SVG.",
        )
    if root is None:
        return failed(
            f"{path.name} is not valid SVG/XML.",
            "Open it in Inkscape and save it again (File → Save As… → Inkscape SVG).",
        )
    local = _svg_local(root.tag)
    if local != "svg":
        return failed(f"{path.name} is not an SVG (the root element is <{local}>).")
    width, height = root.get("width", ""), root.get("height", "")
    if not (width.endswith("mm") and height.endswith("mm")):
        return failed(
            f"The page is not in millimetres (width={width!r}, height={height!r}).",
            "The laser imports millimetres; a px page comes out the wrong size. "
            "In Inkscape, check File → Document Properties, set the display units to mm, "
            "and save again. (The checker's --svg output is already in mm.)",
        )
    return passed(f"{path.name} reads as SVG, {width} × {height}")


def svg_laser_ready(ctx):
    """Every cut is a red hairline and nothing is filled but black.

    Fills may be black (an etch — UCP rasters black) or absent; anything else
    would raster too. Strokes may be absent, or #ff0000 and hairline. Opacity
    must be a full 1: a semi-transparent line is a different colour to the laser.
    """
    path, root = _svg_submission(ctx)
    if path is None:
        return failed("No part-laser-ready.svg in the submission.")
    if root is None:
        return failed(f"{path.name} is not valid SVG/XML.")

    problems, cuts = [], 0

    def walk(el, stroke, fill, hairline, opacity, in_defs):
        nonlocal cuts
        tag = _svg_local(el.tag)
        if not tag:
            return
        if tag == "defs":
            in_defs = True
        style = _svg_style(el)
        stroke = style.get("stroke", stroke)
        fill = style.get("fill", fill)
        opacity = style.get("stroke-opacity", opacity)
        if style.get("-inkscape-stroke") == "hairline":
            hairline = True
        if tag in _SVG_DRAW and not in_defs:
            name = el.get("id") or tag
            if stroke and stroke != "none":
                if stroke not in _SVG_RED:
                    problems.append(f"{name} is stroked {stroke}, not #ff0000")
                else:
                    cuts += 1
                    if not hairline:
                        problems.append(
                            f"{name} is not hairline (stroke-width "
                            f"{style.get('stroke-width', 'unset')})")
                    if opacity and opacity not in ("1", "1.0", "100%"):
                        problems.append(f"{name} is {opacity} opaque")
            if fill and fill not in _SVG_BLACK and fill not in _SVG_NO_FILL:
                problems.append(
                    f"{name} is filled {fill}; fills must be none or black")
        for child in el:
            walk(child, stroke, fill, hairline, opacity, in_defs)

    walk(root, "none", "", False, "", False)

    if problems:
        sample = "; ".join(problems[:4])
        more = f" (+{len(problems) - 4} more)" if len(problems) > 4 else ""
        return failed(
            f"{len(problems)} element(s) are not laser-ready: {sample}{more}.",
            "Cuts: pure red #ff0000, width Hairline (Inkscape: Fill and Stroke → "
            "Stroke style). Etches: black fill, no stroke. "
            "The checker's --svg run does both for you.",
        )
    if cuts == 0:
        return failed(
            "Nothing in the file is a red cut line.",
            "The laser only cuts red. Set your outline's stroke to #ff0000, or let "
            "the checker write the file for you (add --svg to the check command).",
        )
    return passed(f"{cuts} red hairline cut path(s); nothing filled that is not black")


# ---------------------------------------------------------------- human


def dxf_has_curve(ctx, min_curves=1):
    """The outline contains a real curve, not only straight lines.

    Onshape exports a sketch arc as an ARC entity, so this reads the entity
    kinds of the outer profile rather than guessing from the tessellation.
    """
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    outer = _outer_profile(profs, circles)
    if outer is None:
        return failed("Could not identify the outer outline.")
    kinds = {}
    for idx in outer.source:
        if 0 <= idx < len(ctx.drawing.entities):
            kind = ctx.drawing.entities[idx].kind
            kinds[kind] = kinds.get(kind, 0) + 1
    curves = sum(n for k, n in kinds.items() if k in ("ARC", "SPLINE", "ELLIPSE"))
    if curves >= min_curves:
        return passed(f"the outline contains {curves} curve(s)", kinds=kinds)
    return failed(
        "the outline is made of straight lines only — there is no curve in it.",
        "The arc has to be part of the outline, not floating beside it. Draw it "
        "corner to corner and then trim away the straight edge it replaces.",
        kinds=kinds,
    )


def dxf_joints_match_thickness(ctx, tol=0.2, min_joints=1):
    """Finger joints are sized from the material thickness, measured not guessed.

    A finger or slot is an edge of the outline that lies between two inside
    (reflex) corners; its length is the joint width. Everything about the joint
    comes down to that number, so it is compared with the thickness the student
    wrote in the manifest — which is what they measured with calipers.
    """
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    circles = [p for p in profs if p.is_round]
    outer = _outer_profile(profs, circles)
    if outer is None:
        return failed("Could not identify the outer outline.")

    joints = _reflex_pairs(outer.points)
    if len(joints) < min_joints:
        return failed(
            "the outline has no slots or fingers in it — it is a plain shape.",
            "Cut notches out of one edge and add matching tabs to the other so the "
            "two pieces press together. In Onshape, dimension the notch width and "
            "leave the rest of the shape as it is.",
            joints=len(joints),
        )

    stated = (ctx.manifest or {}).get("material_thickness")
    if not stated:
        return failed(
            "manifest.md does not say what thickness you measured.",
            "Measure the sheet with calipers and write it down: material_thickness: 3.15",
        )
    try:
        import re as _re

        thickness = float(_re.sub(r"[^0-9.]", "", stated))
    except ValueError:
        return needs_review(f"could not read a thickness from '{stated}'", value=stated)

    widths = [round(w, 2) for w, _i in joints]
    closest = min(widths, key=lambda w: abs(w - thickness))
    if abs(closest - thickness) <= tol:
        return passed(
            f"joint width {closest:.2f} mm matches the {thickness:.2f} mm you measured",
            joints=widths,
            thickness=thickness,
        )
    return failed(
        f"the joints are {closest:.2f} mm wide, but you measured {thickness:.2f} mm "
        f"material.",
        f"Type the joint width as {thickness:.2f} — the number you measured, not the "
        "label on the sheet. If the pieces rattle, take a tenth of a millimetre off "
        "and cut a test again.",
        joints=widths,
        thickness=thickness,
    )


def _reflex_pairs(points):
    """Edges whose two endpoints are both inside corners, with their lengths.

    On a finger-jointed outline every slot floor and every tab face is exactly
    that: an edge between two reflex corners. Its length is the joint width.
    """
    pts = _dedupe_ring(points)
    n = len(pts)
    if n < 4:
        return []
    area = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    ccw = area > 0

    def reflex(i):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cross) < 1e-9:
            return False  # collinear: not a corner at all
        return (cross < 0) if ccw else (cross > 0)

    out = []
    for i in range(n):
        j = (i + 1) % n
        if reflex(i) and reflex(j):
            out.append((dist(pts[i], pts[j]), (i, j)))
    return out


def _dedupe_ring(points):
    out = []
    for p in points:
        if not out or dist(out[-1], p) > 1e-6:
            out.append(p)
    while len(out) > 1 and dist(out[0], out[-1]) <= 1e-6:
        out.pop()
    return out


def dxf_single_profile(ctx):
    """Exactly one closed shape, with nothing left over.

    Two closed shapes means the trim did not finish. So does one shape plus
    leftover geometry: an arc whose ends land on the corners leaves vertices
    where three segments meet, and the laser would cut along it.
    """
    if ctx.drawing is None:
        return failed("No DXF to check.")
    profs = ctx.drawing.profiles()
    if not profs:
        return failed(
            "there is no closed shape in the drawing.",
            "Close the outline: every corner has to be joined. In Onshape look for "
            "a shaded region — an open profile shows as white.",
        )
    if len(profs) > 1:
        return failed(
            f"there are {len(profs)} closed shapes; the drawing should be one.",
            "The shapes are still separate, so the laser would cut the edge you meant "
            "to remove and the piece would fall in two. Use the Trim tool on the "
            "straight edge the arc replaced.",
            profiles=len(profs),
        )

    # One profile — but is everything else part of it?
    used = set(profs[0].source)
    leftovers = [e for e in ctx.drawing.entities if e.index not in used]
    if leftovers:
        kinds = ", ".join(sorted({e.kind for e in leftovers}))
        return failed(
            f"the drawing has one closed shape, plus {len(leftovers)} leftover "
            f"line(s) or curve(s) ({kinds}) that are not part of it.",
            "That extra geometry is what the Trim tool is for: the laser cuts every "
            "line it is given. Click the leftover line with the Trim tool (the "
            "scissors) to remove it.",
            profiles=1,
            leftovers=len(leftovers),
        )
    return passed("the drawing is one closed shape, and nothing else")


def dxf_width_between(ctx, min_width=None, max_width=None, height=None, tol=0.3):
    """The overall width, bounded — enough to tell a bulge out from a bulge in."""
    if ctx.drawing is None:
        return failed("No DXF to check.")
    bounds = ctx.drawing.bounds()
    if bounds is None:
        return failed("The DXF has no geometry.")
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    problems = []
    if min_width is not None and w < min_width - tol:
        problems.append(f"width is {w:.1f} mm, expected at least {min_width:.0f}")
    if max_width is not None and w > max_width + tol:
        problems.append(f"width is {w:.1f} mm, expected at most {max_width:.0f}")
    if height is not None and abs(h - height) > tol:
        problems.append(f"height is {h:.1f} mm, expected {height:.0f}")
    if not problems:
        return passed(f"drawing measures {w:.2f} × {h:.2f} mm", width=round(w, 3), height=round(h, 3))
    return failed(
        "; ".join(problems) + ".",
        "The curve bulges outward from the straight edge it replaced — check the "
        "dimensions you set and which way the arc was pulled.",
        width=round(w, 3),
        height=round(h, 3),
    )


def human_photo(ctx, what):
    if not ctx.submission.has("photo.jpg") and not any(
        n.endswith((".jpg", ".jpeg", ".png", ".heic", ".webp")) for n in ctx.submission.files
    ):
        return failed(
            "No photo in the submission.",
            f"Add a clear photo of {what}. Natural light, whole object in frame, no thumb over the interesting part.",
        )
    return needs_review(
        f"photo present — a person checks it shows {what}",
    )


def human_only(ctx, what):
    return needs_review(what)


# ---------------------------------------------------------------- helpers


def _outer_profile(profs, circles):
    """The largest non-circular profile, or the largest profile overall."""
    candidates = [p for p in profs if not p.is_round] or profs
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.area)
