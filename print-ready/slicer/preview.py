"""Render the toolpaths to a PNG so a student can see what was sliced.

Top-down, one image, layers shaded from bottom to top so the vertical shape
reads as colour. Uses Pillow, which the class sandbox already pins for the
`box-and-birdhouse` skill, so this adds no dependency.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

#: Drawn size in pixels before the margin is added.
CANVAS = 900
MARGIN = 40

#: Support is drawn grey, so it reads as "not the part" at a glance.
SUPPORT_COLOUR = (150, 150, 150)


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _layer_colour(t: float) -> tuple[int, int, int]:
    """Bottom layers blue, top layers red - a readable height gradient."""
    return (_lerp(40, 200, t), _lerp(90, 60, t), _lerp(200, 40, t))


def render(path: Path, machine, layers, layer_height: float,
           infill_percent: float) -> None:
    """Write the preview PNG to `path`.

    `layers` is a list of (z, wall_paths, infill_segments, support_segments) as
    collected by the slicer. Support is drawn in grey so it is obvious at a
    glance which material is the part and which is there to be broken away.
    """
    if not layers:
        return

    xs: list[float] = []
    ys: list[float] = []
    for _, walls, infills, supports in layers:
        for wall in walls:
            xs.extend(x for x, _ in wall)
            ys.extend(y for _, y in wall)
        for group in (infills, supports):
            for start, end in group:
                xs.extend((start[0], end[0]))
                ys.extend((start[1], end[1]))
    if not xs:
        return

    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    span = max(x1 - x0, y1 - y0, 1e-6)
    scale = (CANVAS - 2 * MARGIN) / span

    width = int((x1 - x0) * scale) + 2 * MARGIN
    height = int((y1 - y0) * scale) + 2 * MARGIN
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    def to_px(x: float, y: float) -> tuple[float, float]:
        # Flip Y: the printer's Y grows away from the front, and the preview
        # should read like looking down at the bed from the front.
        return (MARGIN + (x - x0) * scale, height - MARGIN - (y - y0) * scale)

    top = max(layer[0] for layer in layers) or 1.0
    for z, walls, infills, supports in layers:
        colour = _layer_colour(z / top)
        for start, end in supports:
            draw.line([to_px(*start), to_px(*end)], fill=SUPPORT_COLOUR, width=1)
        for start, end in infills:
            draw.line([to_px(*start), to_px(*end)], fill=colour, width=1)
        for wall in walls:
            points = [to_px(*p) for p in wall]
            if len(points) > 1:
                points.append(points[0])
                draw.line(points, fill=colour, width=2)

    label = (f"{machine.name}   {layer_height} mm layers   "
             f"{infill_percent:g}% infill   {machine.nozzle} mm PLA")
    if any(layer[3] for layer in layers):
        label += "   grey = support"
    draw.text((MARGIN, 10), label, fill=(60, 60, 60))
    image.save(path)
