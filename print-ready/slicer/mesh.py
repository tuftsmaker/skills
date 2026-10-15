"""Reading an STL and cutting it into per-layer contours.

The plane/triangle intersection is vectorised with numpy: a layer of a detailed
model is tens of thousands of triangles and a Python loop over them is the
difference between two seconds and two minutes.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


def read_stl(path: Path) -> np.ndarray:
    """Read a binary or ASCII STL into an (N, 3, 3) array of triangles."""
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"{path} is empty")

    if raw[:5].lower() == b"solid" and b"facet" in raw[:2048].lower():
        vertices = []
        for line in raw.decode("ascii", "ignore").splitlines():
            parts = line.split()
            if parts[:1] == ["vertex"]:
                vertices.append([float(v) for v in parts[1:4]])
        if not vertices:
            raise ValueError(f"{path}: ASCII STL with no vertices")
        return np.asarray(vertices, dtype=np.float64).reshape(-1, 3, 3)

    if len(raw) < 84:
        raise ValueError(f"{path} is too short to be a binary STL")
    count = struct.unpack("<I", raw[80:84])[0]
    expected = 84 + count * 50
    if len(raw) < expected:
        raise ValueError(
            f"{path}: header says {count} triangles ({expected} bytes) "
            f"but the file is {len(raw)} bytes"
        )
    block = np.frombuffer(raw[84:expected], dtype=np.uint8).reshape(count, 50)
    # 12 bytes of normal, then 3 vertices of 3 float32, then a 2-byte attribute.
    return block[:, 12:48].copy().view("<f4").reshape(count, 3, 3).astype(np.float64)


def bounds(triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned bounding box as (min_xyz, max_xyz)."""
    return triangles.reshape(-1, 3).min(axis=0), triangles.reshape(-1, 3).max(axis=0)


def layer_segments(triangles: np.ndarray, z: float) -> list[tuple[tuple[float, float],
                                                                 tuple[float, float]]]:
    """Intersect every triangle with the plane at `z`.

    Returns the raw cut segments, unordered and unsplit - `geom.stitch` turns
    them into closed loops.
    """
    zs = triangles[:, :, 2]
    crossing = (zs.min(axis=1) <= z) & (zs.max(axis=1) >= z)
    hits = triangles[crossing]
    if not len(hits):
        return []

    # For each of the three edges, where it crosses z (or NaN where it doesn't).
    points = np.full((len(hits), 3, 2), np.nan, dtype=np.float64)
    for i in range(3):
        a = hits[:, i, :]
        b = hits[:, (i + 1) % 3, :]
        az, bz = a[:, 2], b[:, 2]
        spans = (az - z) * (bz - z) < 0
        denominator = np.where(bz - az == 0, 1.0, bz - az)
        fraction = np.where(spans, (z - az) / denominator, 0.0)
        point = a[:, :2] + fraction[:, None] * (b[:, :2] - a[:, :2])
        points[spans, i] = point[spans]

    present = ~np.isnan(points[:, :, 0])
    usable = present.sum(axis=1) == 2
    if not usable.any():
        return []

    # Move the two real points to the front of each triangle's triple.
    order = np.argsort(~present, axis=1)
    ordered = points[np.arange(len(points))[:, None], order]
    first, second = ordered[usable, 0], ordered[usable, 1]

    segments = []
    for (x0, y0), (x1, y1) in zip(first, second):
        if x0 != x1 or y0 != y1:
            segments.append(((float(x0), float(y0)), (float(x1), float(y1))))
    return segments


def layer_count(z_min: float, z_max: float, layer_height: float) -> int:
    return max(1, int(round((z_max - z_min) / layer_height)))


def report_mesh(triangles: np.ndarray) -> list[str]:
    """Things worth telling the student before they print.

    Deliberately shallow: this is a report, not a repair. A mesh that fails
    these is usually still sliceable, and saying so is more useful than
    refusing.
    """
    notes: list[str] = []
    low, high = bounds(triangles)
    size = high - low
    if min(size) <= 0:
        notes.append(
            f"the model is flat in one axis ({size[0]:.3f} x {size[1]:.3f} x "
            f"{size[2]:.3f} mm) - check it was exported in 3D"
        )
    # Duplicate edges are the usual sign of a mesh that is not watertight.
    edges: dict[tuple, int] = {}
    quantised = np.round(triangles.reshape(-1, 3) * 1000).astype(np.int64)
    for tri in quantised.reshape(-1, 3, 3):
        for i in range(3):
            a, b = tuple(tri[i]), tuple(tri[(i + 1) % 3])
            key = (a, b) if a <= b else (b, a)
            edges[key] = edges.get(key, 0) + 1
    duplicated = sum(1 for count in edges.values() if count > 2)
    open_edges = sum(1 for count in edges.values() if count == 1)
    if duplicated:
        notes.append(
            f"{duplicated} duplicated edge(s): the mesh is not watertight, and "
            "slicers differ in how they cope"
        )
    if open_edges:
        notes.append(f"{open_edges} edge(s) bound only one triangle (open surface)")
    return notes
