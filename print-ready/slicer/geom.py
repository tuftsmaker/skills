"""Planar geometry for slicing: contours, offsets and infill.

Clipper (via `pyclipper`) does the offsetting. That matters: a perimeter is a
mitred inward offset of the layer outline, and doing that by hand produces
self-intersections on any concave corner. Clipper is the same library the real
slicers use for this step.

Clipper works in integers, so every coordinate is multiplied by `SCALE` on the
way in and divided out on the way back. At 1e-5 mm the quantisation is four
orders of magnitude below anything a 0.4 mm nozzle can express.
"""

from __future__ import annotations

import math

import pyclipper

#: Clipper integer scale. 1e-5 mm resolution.
SCALE = 100_000

#: Points closer than this are the same point when stitching contours.
TOL = 1e-4

Point = tuple[float, float]


# --------------------------------------------------------------- contours


def signed_area(loop: list[Point]) -> float:
    """Shoelace area. Positive is counter-clockwise."""
    total = 0.0
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def _key(p: Point) -> tuple[int, int]:
    return (round(p[0] / TOL), round(p[1] / TOL))


def point_in_polygon(x: float, y: float, poly: list[Point]) -> bool:
    """Ray casting. Used only to decide which contour encloses which."""
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                inside = not inside
    return inside


def stitch(segments: list[tuple[Point, Point]]) -> list[list[Point]]:
    """Walk a layer's unordered segments into closed loops.

    A slice of a triangle mesh gives back loose segments that must be joined
    end-to-end. Segments arrive split at every triangle edge, so most loops are
    built from several of them and many are collinear - joining on rounded keys
    is what makes that work.
    """
    adjacency: dict[tuple[int, int], list[tuple[int, Point]]] = {}
    for i, (a, b) in enumerate(segments):
        adjacency.setdefault(_key(a), []).append((i, b))
        adjacency.setdefault(_key(b), []).append((i, a))

    used: set[int] = set()
    loops: list[list[Point]] = []
    for start in range(len(segments)):
        if start in used:
            continue
        a, b = segments[start]
        used.add(start)
        loop = [a, b]
        current = b
        while _key(current) != _key(loop[0]):
            nxt = next(
                ((j, other) for j, other in adjacency.get(_key(current), [])
                 if j not in used),
                None,
            )
            if nxt is None:
                break
            used.add(nxt[0])
            loop.append(nxt[1])
            current = nxt[1]
        if _key(current) == _key(loop[0]) and len(loop) >= 4:
            loops.append(loop[:-1])
    return loops


def classify(loops: list[list[Point]]) -> list[tuple[list[Point], bool]]:
    """Tag each loop as an outer boundary or a hole.

    Containment is tested with a vertex of the candidate loop, never with its
    centroid: for a ring, the outer loop's centroid falls inside the hole, so a
    centroid test marks the outer boundary as a hole as well. That mistake
    offsets both loops the same way and the hole comes out solid.
    """
    tagged: list[tuple[list[Point], bool]] = []
    for i, loop in enumerate(loops):
        px, py = loop[0]
        enclosing = sum(
            1 for j, other in enumerate(loops)
            if j != i and point_in_polygon(px, py, other)
        )
        tagged.append((loop, enclosing % 2 == 1))
    return tagged


# ---------------------------------------------------------------- clipper


def _to_clipper(paths: list[list[Point]]) -> list[list[tuple[int, int]]]:
    return [[(round(x * SCALE), round(y * SCALE)) for x, y in p] for p in paths]


def _from_clipper(paths) -> list[list[Point]]:
    return [[(x / SCALE, y / SCALE) for x, y in p] for p in paths]


def as_region(tagged: list[tuple[list[Point], bool]]) -> list[list[Point]]:
    """Orient loops so Clipper reads them as one filled region with holes.

    Clipper decides inside from winding: outers counter-clockwise, holes
    clockwise. Getting this wrong makes a hole fill in.
    """
    out: list[list[Point]] = []
    for loop, is_hole in tagged:
        area = signed_area(loop)
        if abs(area) < TOL:
            continue
        want_positive = not is_hole
        if (area > 0) != want_positive:
            loop = loop[::-1]
        out.append(loop)
    return out


def offset(paths: list[list[Point]], delta: float,
           miter_limit: float = 3.0) -> list[list[Point]]:
    """Offset every path by `delta` mm.

    Negative shrinks the region (which is what an inward perimeter is);
    positive grows it (what a hole's perimeter is, when holes are fed in with
    reversed winding). Returns Clipper's paths, which may be more or fewer than
    went in: thin regions vanish, sharp corners can split.
    """
    if not paths:
        return []
    pco = pyclipper.PyclipperOffset()
    pco.MiterLimit = miter_limit
    pco.AddPaths(_to_clipper(paths), pyclipper.JT_MITER, pyclipper.ET_CLOSEDPOLYGON)
    return _from_clipper(pco.Execute(delta * SCALE))


def simplify(paths: list[list[Point]]) -> list[list[Point]]:
    """Drop collinear points and repair self-intersections."""
    if not paths:
        return []
    out = pyclipper.SimplifyPolygons(_to_clipper(paths), pyclipper.PFT_NONZERO)
    return _from_clipper(out)


def _clip(a: list[list[Point]], b: list[list[Point]], op) -> list[list[Point]]:
    # The empty-region cases have to be handled here rather than passed to
    # Clipper: an empty region is not "no region", it is the empty set, and
    # each operation has its own identity for it. Getting difference(a, empty)
    # wrong empties every region that is not covered from one side.
    if op == pyclipper.CT_UNION:
        if not a:
            return list(b)
        if not b:
            return list(a)
    elif op == pyclipper.CT_DIFFERENCE:
        if not a:
            return []
        if not b:
            return list(a)
    elif op == pyclipper.CT_INTERSECTION:
        if not a or not b:
            return []
    clipper = pyclipper.Pyclipper()
    clipper.AddPaths(_to_clipper(a), pyclipper.PT_SUBJECT, True)
    clipper.AddPaths(_to_clipper(b), pyclipper.PT_CLIP, True)
    return _from_clipper(
        clipper.Execute(op, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    )


def union(a: list[list[Point]], b: list[list[Point]]) -> list[list[Point]]:
    return _clip(a, b, pyclipper.CT_UNION)


def difference(a: list[list[Point]], b: list[list[Point]]) -> list[list[Point]]:
    return _clip(a, b, pyclipper.CT_DIFFERENCE)


def intersection(a: list[list[Point]], b: list[list[Point]]) -> list[list[Point]]:
    return _clip(a, b, pyclipper.CT_INTERSECTION)


def union_all(regions: list[list[list[Point]]]) -> list[list[Point]]:
    out: list[list[Point]] = []
    for region in regions:
        if region:
            out = union(out, region)
    return out


#: Areas below this, in mm^2, are Clipper slivers rather than real regions. A
#: 0.4 mm nozzle cannot express anything this small.
MIN_AREA = 1e-4


def area(paths: list[list[Point]]) -> float:
    """Net area enclosed by a set of paths, in mm^2.

    Sums SIGNED areas, so a hole (which is wound the other way) subtracts.
    Summing absolute values adds the holes in instead, which reported a
    "solid area" larger than the layer region it was clipped from.
    """
    return abs(sum(signed_area(p) for p in paths))


def drop_slivers(paths: list[list[Point]],
                 min_area: float = MIN_AREA) -> list[list[Point]]:
    """Keep only the paths that enclose real area.

    Clipper returns zero-area paths wherever two boundaries touch, and a
    non-empty list of those reads as "there is a region here" when there is
    not. Testing area instead of list emptiness is what makes a solid-surface
    test mean anything: `bool(solid_area(...))` was True on every layer of a
    part with only eight solid layers.
    """
    return [p for p in paths if abs(signed_area(p)) >= min_area]


def bounding_box(paths: list[list[Point]]) -> tuple[float, float, float, float]:
    xs = [x for path in paths for x, _ in path]
    ys = [y for path in paths for _, y in path]
    return min(xs), min(ys), max(xs), max(ys)


# ----------------------------------------------------------------- infill


def scanline_infill(paths: list[list[Point]], spacing: float,
                    angle: float) -> list[tuple[Point, Point]]:
    """Even-odd scanline fill across every path at once.

    Running one pass over all the paths together is what makes holes fall out
    for free: a scan line crossing an outer boundary and its hole has four
    crossings, and even-odd keeps only the span between crossings two and
    three. Clipping each polygon separately would fill the holes in.
    """
    if spacing <= 0 or not paths:
        return []
    radians = math.radians(angle)
    cos_a, sin_a = math.cos(radians), math.sin(radians)

    rotated = [
        [(x * cos_a + y * sin_a, -x * sin_a + y * cos_a) for x, y in path]
        for path in paths
    ]
    ys = [y for path in rotated for _, y in path]
    y_min, y_max = min(ys), max(ys)

    segments: list[tuple[Point, Point]] = []
    y = y_min + spacing / 2.0
    while y < y_max:
        crossings: list[float] = []
        for path in rotated:
            n = len(path)
            for i in range(n):
                x0, y0 = path[i]
                x1, y1 = path[(i + 1) % n]
                if (y0 > y) != (y1 > y):
                    crossings.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        crossings.sort()
        for i in range(0, len(crossings) - 1, 2):
            x0, x1 = crossings[i], crossings[i + 1]
            if x1 - x0 <= TOL:
                continue
            segments.append((
                (x0 * cos_a - y * sin_a, x0 * sin_a + y * cos_a),
                (x1 * cos_a - y * sin_a, x1 * sin_a + y * cos_a),
            ))
        y += spacing
    return segments


def path_length(points: list[Point]) -> float:
    return sum(
        math.dist(points[i], points[(i + 1) % len(points)])
        for i in range(len(points))
    )
