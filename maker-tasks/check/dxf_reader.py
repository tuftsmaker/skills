"""Minimal, forgiving DXF reader for sketch exports.

Reads what Onshape / Inkscape / Illustrator actually emit: LINE, LWPOLYLINE,
POLYLINE, CIRCLE, ARC, SPLINE and ELLIPSE in the ENTITIES section, with the
handful of header variables we care about. ASCII DXF only — that is what every
tool in this class exports.

Deliberately NOT a full DXF implementation. It knows the group codes that
matter for 2D profiles and ignores everything else, so a file with entities we
do not understand still yields usable geometry instead of an error.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from geom import (
    Profile,
    chain_closed,
    tessellate_arc,
    tessellate_circle,
)

SUPPORTED = {"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "SPLINE", "ELLIPSE"}


class DxfError(Exception):
    pass


@dataclass
class Entity:
    kind: str
    index: int
    layer: str = "0"
    closed: bool = False
    points: list = field(default_factory=list)  # tessellated, open
    radius: float | None = None
    centre: tuple | None = None
    is_circle: bool = False
    handle: str | None = None
    # Arcs keep their parameters as well as their tessellation: the checks work
    # from the points, but writing a real SVG arc (rather than a many-point
    # polyline) needs the centre, radius and angles. None on every other kind.
    a0: float | None = None  # start angle, degrees, CCW from +X
    a1: float | None = None  # end angle, degrees
    # A polyline vertex can carry a "bulge" (code 42), meaning the segment to the
    # next vertex is an arc, not a straight line. Onshape never emits it; set
    # here so callers can warn instead of silently drawing a straight chord.
    bulges: bool = False


@dataclass
class Drawing:
    path: Path
    header: dict
    entities: list
    skipped: dict = field(default_factory=dict)  # kind -> count

    # -- convenient views -------------------------------------------------

    @property
    def supported(self) -> list:
        return self.entities

    def open_shapes(self, tol: float = 0.01):
        """Segments that do not form a closed loop. Returns a list of
        (points, [index]) — one entry per open run, so a rectangle drawn as
        four lines is reported as nothing, and a gap is reported once."""
        curves = []
        for e in self.entities:
            if e.is_circle:
                continue  # a circle is closed by definition
            if e.closed and len(e.points) > 2:
                continue  # closed entity is not an open shape
            for i in range(len(e.points) - 1):
                curves.append((e.index, e.points[i], e.points[i + 1]))

        unclosed = []
        while curves:
            idx, start, end = curves.pop(0)
            pts = [start, end]
            used = {idx}
            closed = False
            while True:
                tail = pts[-1]
                hit = None
                for j, (jdx, s, e) in enumerate(curves):
                    if _near(tail, s, tol):
                        hit = (j, jdx, e)
                        break
                    if _near(tail, e, tol):
                        hit = (j, jdx, s)
                        break
                if hit is None:
                    break
                j, jdx, nxt = hit
                curves.pop(j)
                pts.append(nxt)
                used.add(jdx)
                if _near(pts[-1], pts[0], tol) and len(pts) >= 3:
                    closed = True
                    break
            if not closed:
                unclosed.append((pts, sorted(used)))
        return unclosed

    def profiles(self, tol: float = 0.01) -> list:
        """Every closed region: circles, closed polylines, and loops chained
        from separate line/arc entities."""
        out = []
        for e in self.entities:
            if e.is_circle:
                out.append(
                    Profile(
                        points=tessellate_circle(e.centre[0], e.centre[1], e.radius),
                        kind="circle",
                        source=[e.index],
                        radius=e.radius,
                        centre=e.centre,
                    )
                )
            elif e.closed and len(e.points) > 2:
                kind = "rect" if _looks_rectangular(e.points) else "loop"
                out.append(Profile(points=e.points[:-1] if _near(e.points[0], e.points[-1], tol) else e.points, kind=kind, source=[e.index]))

        curves = []
        for e in self.entities:
            if e.is_circle or (e.closed and len(e.points) > 2):
                continue
            for i in range(len(e.points) - 1):
                curves.append((e.index, e.points[i], e.points[i + 1]))
        for points, used in chain_closed(curves, tol):
            kind = "rect" if _looks_rectangular(points) else "loop"
            out.append(Profile(points=points, kind=kind, source=sorted(set(used))))
        return out

    def bounds(self):
        xs, ys = [], []
        for e in self.entities:
            for x, y in e.points:
                xs.append(x)
                ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def layers(self) -> dict:
        counts = {}
        for e in self.entities:
            counts[e.layer] = counts.get(e.layer, 0) + 1
        return counts


def _near(a, b, tol):
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _looks_rectangular(points) -> bool:
    pts = points
    if len(pts) > 1 and _near(pts[0], pts[-1], 0.01):
        pts = pts[:-1]
    if len(pts) != 4:
        return False
    for i in range(4):
        a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        if math.hypot(*v1) < 0.01 or math.hypot(*v2) < 0.01:
            return False
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        if abs(dot) / (math.hypot(*v1) * math.hypot(*v2)) > 0.02:
            return False
    return True


# ---------------------------------------------------------------- parsing


def read(path) -> Drawing:
    path = Path(path)
    raw = path.read_bytes()
    text = _decode(raw)
    pairs = _pairs(text)
    if not pairs:
        raise DxfError("no DXF group codes found — is this really a DXF?")

    header, entities_raw = _split_sections(pairs)
    entities, skipped = _parse_entities(entities_raw)
    if not entities:
        detail = ", ".join(f"{k} x{v}" for k, v in skipped.items()) or "nothing"
        raise DxfError(f"no 2D geometry found ({detail})")

    return Drawing(path=path, header=header, entities=entities, skipped=skipped)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def _pairs(text: str):
    lines = re.split(r"\r\n|\n|\r", text)
    out = []
    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1].strip()
        if code:
            out.append((code, value))
        i += 2
    return out


def _split_sections(pairs):
    header = {}
    ent_lines = []
    section = None
    i = 0
    while i < len(pairs):
        code, value = pairs[i]
        if code == "0" and value == "SECTION":
            section = pairs[i + 1][1] if i + 1 < len(pairs) else None
            i += 2
            continue
        if code == "0" and value == "ENDSEC":
            section = None
            i += 1
            continue
        if section == "HEADER":
            if code == "9" and value.startswith("$"):
                nxt = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
                header[value] = nxt[1]
                i += 2
                continue
        elif section == "ENTITIES":
            ent_lines.append((code, value))
        i += 1
    return header, ent_lines


def _parse_entities(lines):
    entities = []
    skipped = {}
    i = 0
    while i < len(lines):
        code, value = lines[i]
        if code == "0" and value in SUPPORTED:
            start = i
            j = i + 1
            while j < len(lines) and lines[j][0] != "0":
                j += 1
            entities.append(_build_entity(value, lines[start:j], len(entities)))
            i = j
            continue
        if code == "0" and value not in ("", "EOF"):
            skipped[value] = skipped.get(value, 0) + 1
        i += 1
    return entities, skipped


def _codes(body):
    """Group the entity body into {code: [values]} in file order."""
    out = {}
    for code, value in body:
        out.setdefault(code, []).append(value)
    return out


def _floats(values):
    vals = []
    for v in values:
        try:
            vals.append(float(v))
        except ValueError:
            continue
    return vals


def _has_bulge(codes) -> bool:
    """True when any polyline vertex carries a non-zero bulge (code 42).

    A bulge turns the segment to the next vertex into an arc; the reader
    tessellates vertices only, so this is what lets a caller say "drawn as
    straight lines" instead of quietly changing the shape. Onshape's own exports
    have none, so this normally stays False.
    """
    for raw in codes.get("42", []):
        try:
            if abs(float(raw)) > 1e-9:
                return True
        except ValueError:
            continue
    return False


def _build_entity(kind, body, index):
    c = _codes(body)
    layer = (c.get("8") or ["0"])[0]
    handle = (c.get("5") or [None])[0]

    if kind == "LINE":
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        xe, ye = _floats(c.get("11", [])), _floats(c.get("21", []))
        pts = [(xs[0], ys[0]), (xe[0], ye[0])] if xs and ys and xe and ye else []
        return Entity("LINE", index, layer, False, pts, handle=handle)

    if kind == "LWPOLYLINE":
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        flags = int((c.get("70") or ["0"])[0])
        closed = bool(flags & 1)
        pts = list(zip(xs, ys))
        return Entity("LWPOLYLINE", index, layer, closed, pts, handle=handle,
                      bulges=_has_bulge(c))

    if kind == "POLYLINE":
        flags = int((c.get("70") or ["0"])[0])
        closed = bool(flags & 1)
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        pts = list(zip(xs, ys))
        return Entity("POLYLINE", index, layer, closed, pts, handle=handle,
                      bulges=_has_bulge(c))

    if kind == "CIRCLE":
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        rs = _floats(c.get("40", []))
        if not (xs and ys and rs):
            return Entity(kind, index, layer, True, [], handle=handle)
        return Entity(
            "CIRCLE",
            index,
            layer,
            True,
            tessellate_circle(xs[0], ys[0], rs[0]),
            radius=rs[0],
            centre=(xs[0], ys[0]),
            is_circle=True,
            handle=handle,
        )

    if kind == "ARC":
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        rs = _floats(c.get("40", []))
        a0, a1 = _floats(c.get("50", [])), _floats(c.get("51", []))
        if not (xs and ys and rs and a0 and a1):
            return Entity(kind, index, layer, False, [], handle=handle)
        return Entity(
            "ARC",
            index,
            layer,
            False,
            tessellate_arc(xs[0], ys[0], rs[0], a0[0], a1[0]),
            radius=rs[0],
            centre=(xs[0], ys[0]),
            handle=handle,
            a0=a0[0],
            a1=a1[0],
        )

    if kind == "SPLINE":
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        pts = list(zip(xs, ys))
        closed = False
        if len(pts) > 2 and _near(pts[0], pts[-1], 0.01):
            closed = True
        return Entity("SPLINE", index, layer, closed, pts, handle=handle)

    if kind == "ELLIPSE":
        xs, ys = _floats(c.get("10", [])), _floats(c.get("20", []))
        major = _floats(c.get("11", [])) or [1.0]
        ratio = _floats(c.get("40", [])) or [1.0]
        if not (xs and ys and major):
            return Entity(kind, index, layer, True, [], handle=handle)
        a = math.hypot(major[0], _floats(c.get("21", []))[0] if c.get("21") else 0.0)
        b = a * ratio[0]
        # Tessellate as an ellipse (chords coarse to 0.1 mm).
        r = max(a, b)
        pts = tessellate_circle(xs[0], ys[0], r)
        pts = [(xs[0] + (px - xs[0]) * (a / r), ys[0] + (py - ys[0]) * (b / r)) for px, py in pts]
        return Entity("ELLIPSE", index, layer, True, pts, handle=handle)

    return Entity(kind, index, layer, False, [], handle=handle)
