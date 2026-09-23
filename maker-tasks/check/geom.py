"""Geometry helpers for the task checks.

Pure standard library on purpose: the same code runs on a student's laptop
through the `maker-tasks` skill and on the TA's machine, with no installs.

Everything is in millimetres. Tolerances are millimetres too.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------- points


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def point_close(a, b, tol: float) -> bool:
    return dist(a, b) <= tol


# ---------------------------------------------------------------- profiles


@dataclass
class Profile:
    """A closed loop of points, plus how it was built.

    `kind` is "rect" when the loop is made of four straight edges meeting at
    right angles, "circle" when it came from a single circle entity, and
    "loop" otherwise. `source` lists the entity indexes that formed it.
    """

    points: list  # [(x, y), ...] without repeating the first point
    kind: str
    source: list = field(default_factory=list)
    radius: float | None = None  # set for kind == "circle"
    centre: tuple | None = None  # set for kind == "circle"

    # -- basic measures ---------------------------------------------------

    @property
    def bbox(self):
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def width(self) -> float:
        x0, _, x1, _ = self.bbox
        return x1 - x0

    @property
    def height(self) -> float:
        _, y0, _, y1 = self.bbox
        return y1 - y0

    @property
    def area(self) -> float:
        """Shoelace area, absolute value (mm2)."""
        total = 0.0
        n = len(self.points)
        for i in range(n):
            x1, y1 = self.points[i]
            x2, y2 = self.points[(i + 1) % n]
            total += x1 * y2 - x2 * y1
        return abs(total) / 2.0

    @property
    def is_round(self) -> bool:
        return self.radius is not None

    @property
    def diameter(self) -> float | None:
        return None if self.radius is None else self.radius * 2.0

    def signed_area(self) -> float:
        total = 0.0
        n = len(self.points)
        for i in range(n):
            x1, y1 = self.points[i]
            x2, y2 = self.points[(i + 1) % n]
            total += x1 * y2 - x2 * y1
        return total / 2.0

    # -- geometry --------------------------------------------------------

    def contains_point(self, p, tol: float = 0.0) -> bool:
        """Ray casting; tolerant version nudges the point onto the polygon."""
        x, y = p
        inside = False
        pts = self.points
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < xin:
                    inside = not inside
        return inside

    def edge_clearance(self, other: "Profile") -> float:
        """Smallest distance from a point of `other` to an edge of self."""
        best = float("inf")
        pts = self.points
        n = len(pts)
        for q in other.points:
            for i in range(n):
                p1, p2 = pts[i], pts[(i + 1) % n]
                best = min(best, _point_segment(q, p1, p2))
        return best

    def centre(self) -> tuple:
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _point_segment(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return dist(p, a)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return dist(p, (ax + t * dx, ay + t * dy))


# ---------------------------------------------------------------- chaining


def chain_closed(curves, tol: float = 0.01):
    """Find closed loops among open curve segments.

    `curves` is a list of (index, start, end) for open segments, already
    tessellated to straight lines. Returns a list of (points, [indexes]) for
    every loop that closes within `tol`. Greedy and deterministic: it walks
    endpoint to endpoint, preferring the nearest unmatched continuation.
    """
    remaining = list(curves)
    loops = []

    while remaining:
        idx, start, end = remaining.pop(0)
        points = [start, end]
        used = [idx]
        closed = False

        while True:
            tail = points[-1]
            best = None
            best_d = None
            for j, (jdx, s, e) in enumerate(remaining):
                for swapped, (a, b) in ((False, (s, e)), (True, (e, s))):
                    d = dist(tail, a)
                    if d <= tol and (best_d is None or d < best_d):
                        best, best_d = (j, jdx, b), d
            if best is None:
                break
            j, jdx, nxt = best
            remaining.pop(j)
            points.append(nxt)
            used.append(jdx)
            if point_close(points[-1], points[0], tol) and len(points) >= 4:
                closed = True
                break

        if closed:
            points = points[:-1]  # drop the repeated closing point
            points = _dedupe(points, tol)
            loops.append((points, used))

    return loops


def _dedupe(points, tol):
    out = []
    for p in points:
        if not out or not point_close(out[-1], p, tol):
            out.append(p)
    while len(out) > 1 and point_close(out[0], out[-1], tol):
        out.pop()
    return out


def is_rectangle(points, tol: float = 0.01) -> bool:
    """True when a closed loop has exactly four corners and right angles."""
    pts = _dedupe(points, tol)
    if len(pts) != 4:
        return False
    for i in range(4):
        a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        if math.hypot(*v1) < tol or math.hypot(*v2) < tol:
            return False
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        scale = math.hypot(*v1) * math.hypot(*v2)
        if abs(dot) / scale > 0.02:  # not perpendicular
            return False
    return True


def reflex_ratio(points) -> float:
    """Length of the loop's own edges that is reflex (an inside corner)."""
    total = 0.0
    n = len(points)
    for i in range(n):
        a, b, c = points[i - 1], points[i], points[(i + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if cross < 0:
            total += math.hypot(*v2)
    length = 0.0
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        length += dist(a, b)
    return total / length if length else 0.0


def symmetry_error(points, axis: str, tol: float = 0.2) -> float:
    """Worst distance from a mirrored point back to the nearest original point.

    `axis` is "x" or "y": mirroring across the vertical or horizontal line
    through the shape's own centre. Because the axis is the shape's centre, a
    symmetric outline mirrors onto itself exactly; an asymmetric one does not.
    """
    pts = _dedupe(points, tol)
    if not pts:
        return float("inf")
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    worst = 0.0
    for x, y in pts:
        if axis == "x":
            m = (2 * cx - x, y)
        else:
            m = (x, 2 * cy - y)
        worst = max(worst, min(dist(m, q) for q in pts))
    return worst


# ---------------------------------------------------------------- tessellation


def tessellate_arc(cx, cy, r, a0_deg, a1_deg, max_chord: float = 0.1):
    """Approximate an arc with points, no coarser than max_chord mm per chord."""
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    sweep = (a1 - a0) % (2 * math.pi)
    if sweep == 0:
        sweep = 2 * math.pi
    if r <= 0:
        return [(cx, cy)]
    step = min(math.pi / 4, max(2 * math.asin(min(1.0, max_chord / (2 * r))), 1e-3))
    n = max(4, int(math.ceil(sweep / step)))
    return [
        (cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n))
        for i in range(n + 1)
    ]


def tessellate_circle(cx, cy, r, max_chord: float = 0.1):
    return tessellate_arc(cx, cy, r, 0.0, 360.0, max_chord)
