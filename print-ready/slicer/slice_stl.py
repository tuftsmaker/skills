#!/usr/bin/env python3
"""Slice an STL for the Prusa MK4 or Prusa CORE One at Nolop.

    python3 slice_stl.py part.stl                      # MK4, PLA, 0.2 mm
    python3 slice_stl.py part.stl --machine coreone    # the CORE One
    python3 slice_stl.py part.stl --infill 25

This writes G-code for the two machines in the makerspace. It is a helper, not
a slicer you should reach for over PrusaSlicer when a part is difficult: it has
no support generation, no bridging detection and no arc fitting. What it does
have is the printers' real start/end sequences and PLA settings, so simple
parts come out printable.

The machine settings and the start/end sequences come from PrusaSlicer's own
profiles. See `profiles.py`.

The slice runs in three passes, because the top and bottom surfaces of a part
cannot be known from one layer alone:

  1. cut every layer into contours;
  2. work out which parts of each layer are exposed to air above or below,
     looking `top_solid_layers` / `bottom_solid_layers` in each direction;
  3. emit perimeters, then solid infill where a surface is exposed and sparse
     infill everywhere else.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geom  # noqa: E402
import mesh  # noqa: E402
import profiles  # noqa: E402

#: 1.75 mm filament, the diameter both machines take.
FILAMENT_DIAMETER = 1.75
FILAMENT_AREA = math.pi * (FILAMENT_DIAMETER / 2.0) ** 2

#: Infill is widened by this fraction of a line width so it meets the innermost
#: wall instead of leaving a seam. PrusaSlicer's `infill_overlap` is 15%.
INFILL_OVERLAP = 0.15

# Support settings, all read from PrusaSlicer's own MK4IS profile so the
# numbers are not invented:
SUPPORT_LINE_WIDTH = 0.36          # support_material_extrusion_width
SUPPORT_BODY_SPACING = 2.0         # support_material_spacing (about 18%)
SUPPORT_INTERFACE_SPACING = 0.2    # support_material_interface_spacing
SUPPORT_INTERFACE_LAYERS = 3       # support_material_interface_layers
SUPPORT_CONTACT = 0.2              # support_material_contact_distance, mm
SUPPORT_XY_GAP = 0.80              # support_material_xy_spacing, of line width
SUPPORT_FEED = 7200                # support_material_speed, 120 mm/s
SUPPORT_INTERFACE_FEED = 3600      # support_material_interface_speed, 50%
#: PrusaSlicer's `support_material_threshold`: the steepest overhang, in
#: degrees from vertical, that still stands up on its own.
SUPPORT_ANGLE = 40.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="slice_stl.py",
        description="Slice an STL for the Nolop Prusa MK4 or Prusa CORE One.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("stl", type=Path, help="the STL to slice")
    parser.add_argument("-o", "--output", type=Path,
                        help="output .gcode path (default: beside the STL)")
    parser.add_argument("--machine", choices=sorted(profiles.MACHINES),
                        default="mk4",
                        help="which printer (default: mk4)")
    parser.add_argument("--layer-height", type=float, default=0.20,
                        help="layer height in mm (default: 0.20)")
    parser.add_argument("--infill", type=float, default=15.0,
                        help="infill density as a percentage (default: 15)")
    parser.add_argument("--perimeters", type=int, default=2,
                        help="number of walls (default: 2)")
    parser.add_argument("--line-width", type=float, default=0.45,
                        help="extrusion width in mm (default: 0.45)")
    parser.add_argument("--top-solid", type=int, default=5,
                        help="solid layers above an exposed top surface "
                             "(default: 5, as PrusaSlicer uses)")
    parser.add_argument("--bottom-solid", type=int, default=3,
                        help="solid layers under an exposed bottom surface "
                             "(default: 3, as PrusaSlicer uses)")
    parser.add_argument("--nozzle", type=float, default=0.4,
                        help="nozzle diameter, must match the machine "
                             "(default: 0.4)")
    parser.add_argument("--support", action="store_true",
                        help="generate support under overhangs "
                             "(off by default, as PrusaSlicer ships it)")
    parser.add_argument("--support-angle", type=float, default=SUPPORT_ANGLE,
                        help=f"steepest overhang that prints unsupported, in "
                             f"degrees from horizontal, so 90 is a vertical "
                             f"wall (default: {SUPPORT_ANGLE:g}, PrusaSlicer's "
                             f"support_material_threshold)")
    parser.add_argument("--preview", type=Path,
                        help="also write a PNG of the toolpaths")
    parser.add_argument("--open", dest="open_preview", action="store_true",
                        help="show the preview in the browser when written")
    return parser.parse_args(argv)


def emit_path(out, points, closed: bool, line_width: float,
              layer_height: float, feed: int, travel: int) -> float:
    """Write one extrusion path.

    Returns the FILAMENT consumed in mm, not the length of the track: a printed
    track 1 mm long and 0.45 x 0.2 mm in cross-section draws 0.09 mm3 of
    plastic, which is far less than 1 mm of 1.75 mm filament.
    """
    if len(points) < 2:
        return 0.0
    coords = list(points) + ([points[0]] if closed else [])
    out.write(f"G1 X{coords[0][0]:.3f} Y{coords[0][1]:.3f} F{travel}\n")
    filament = 0.0
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= geom.TOL:
            continue
        extruded = length * line_width * layer_height / FILAMENT_AREA
        filament += extruded
        out.write(f"G1 X{x1:.3f} Y{y1:.3f} E{extruded:.5f} F{feed}\n")
    return filament


def solid_area(layers, exposed_top, exposed_bottom, index: int,
               top_layers: int, bottom_layers: int) -> list:
    """The part of one layer that needs solid infill.

    A layer needs a solid surface where there is nothing above it, and for the
    `top_layers` below that. So this looks UP for exposed tops and DOWN for
    exposed bottoms, and keeps the overlap with this layer.

    Layer 0 counts as exposed underneath: there is no layer below it, so its
    whole cross-section is a bottom surface. That is what makes the first layer
    print solid, which is what gives the part something to stick with.
    """
    above = [exposed_top[index + k]
             for k in range(top_layers)
             if index + k < len(layers)]
    below = [exposed_bottom[index - k]
             for k in range(bottom_layers)
             if index - k >= 0]
    covering = geom.union_all(above + below)
    if not covering:
        return []
    return geom.drop_slivers(geom.intersection(layers[index], covering))


def support_columns(regions, layer_height: float, angle: float,
                    contact: float) -> tuple[list[list], list[list]]:
    """Work out where support goes.

    Returns (support, interface) per layer. `support` is the region to fill at
    the support's own sparse density; `interface` is the subset to fill densely
    so the overhang has something flat to land on.

    Two things make this work:

    An overhang is the part of a layer that the layer below does not hold up.
    How far a layer may lean over the one below before it needs help is
    `layer_height * tan(angle)`, so at 40 degrees a 0.2 mm layer may lean
    0.168 mm and no further.

    Support is then carried DOWN from each overhang, layer by layer, removing
    whatever the part itself occupies plus a small gap. Going down rather than
    up is what keeps a column continuous: each layer's support is the next
    layer's support plus that layer's overhang, so a column cannot start in
    mid-air.

    The gap is what makes the support removable. `contact` is held back between
    the top of the support and the overhang above it.
    """
    count = len(regions)
    overhang: list[list] = []
    for index, region in enumerate(regions):
        if index == 0 or not region:
            overhang.append([])
            continue
        below = regions[index - 1]
        if not below:
            overhang.append(region)          # nothing at all underneath
            continue
        # PrusaSlicer measures this threshold from the HORIZONTAL, where a
        # vertical wall is 90 degrees. A surface at angle `a` rises one layer
        # height while running out `h / tan(a)`, so that is how far the layer
        # below reaches. Check it against the familiar rule: at 45 degrees the
        # run is exactly one layer height, which is why a 45 degree overhang
        # stands up on its own.
        lean = layer_height / math.tan(math.radians(angle))
        overhang.append(geom.difference(region, geom.offset(below, lean)))

    # The topmost support layer sits this far below the overhang it holds up.
    delay = 1 + int(math.ceil(contact / layer_height - 1e-9))
    gap = SUPPORT_XY_GAP * SUPPORT_LINE_WIDTH

    support: list[list] = [None] * count       # type: ignore[list-item]
    interface: list[list] = [None] * count     # type: ignore[list-item]
    carry: list = []
    for index in range(count - 1, -1, -1):
        source = index + delay
        if source < count and overhang[source]:
            carry = geom.union(carry, overhang[source])

        if not carry:
            support[index] = []
            interface[index] = []
            continue
        clipped = geom.drop_slivers(
            geom.difference(carry, geom.offset(regions[index], gap))
        )
        support[index] = clipped
        # The contact patch is the top of the column: the part of this layer's
        # support standing under an overhang from `delay` to
        # `delay + interface_layers - 1` layers above. Selecting it by layer
        # distance is what keeps it to a few layers. Tracking "recently added
        # overhangs" instead never ages out, so every layer all the way down
        # the column counts as contact and the support prints solid.
        window = [overhang[j] for j in
                  range(index + delay, index + delay + SUPPORT_INTERFACE_LAYERS)
                  if j < count]
        interface[index] = (geom.intersection(clipped, geom.union_all(window))
                            if any(window) else [])
    return support, interface


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    machine = profiles.MACHINES[args.machine]

    if not args.stl.is_file():
        print(f"error: no such file: {args.stl}", file=sys.stderr)
        return 2

    triangles = mesh.read_stl(args.stl)
    low, high = mesh.bounds(triangles)
    size = high - low
    print(f"model      : {args.stl.name}")
    print(f"triangles  : {len(triangles):,}")
    print(f"size       : {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm")

    for note in mesh.report_mesh(triangles):
        print(f"note       : {note}")

    # Centre the part on the bed, sitting on z=0.
    triangles = triangles + (
        (machine.bed_x - size[0]) / 2.0 - low[0],
        (machine.bed_y - size[1]) / 2.0 - low[1],
        -low[2],
    )

    if size[0] > machine.bed_x or size[1] > machine.bed_y or size[2] > machine.bed_z:
        print(f"WARNING    : the part is larger than the {machine.name} build "
              f"volume ({machine.bed_x:.0f} x {machine.bed_y:.0f} x "
              f"{machine.bed_z:.0f} mm)")

    layer_height = args.layer_height
    height = float(size[2])
    total_layers = mesh.layer_count(0.0, height, layer_height)
    line_width = args.line_width

    # ---------------------------------------------------------------- pass 1
    regions: list[list] = []
    for index in range(total_layers):
        z = (index + 1) * layer_height
        if z > height + 1e-6:
            break
        loops = geom.stitch(mesh.layer_segments(triangles, z))
        regions.append(geom.as_region(geom.classify(loops)) if loops else [])

    if not any(regions):
        print("error: nothing to print - no layer produced any geometry",
              file=sys.stderr)
        return 1

    first = next(i for i, r in enumerate(regions) if r)
    first_layer_bounds = geom.bounding_box(regions[first])

    # ---------------------------------------------------------------- pass 2
    # exposed_top[i] is the part of layer i with nothing directly above it.
    # The empty layer past the end of the part makes the topmost layer fully
    # exposed, and likewise below layer 0.
    exposed_top, exposed_bottom = [], []
    for index, region in enumerate(regions):
        if not region:
            exposed_top.append([])
            exposed_bottom.append([])
            continue
        above = regions[index + 1] if index + 1 < len(regions) else []
        below = regions[index - 1] if index - 1 >= 0 else []
        exposed_top.append(geom.difference(region, above))
        exposed_bottom.append(geom.difference(region, below))

    solid_flags = [
        bool(solid_area(regions, exposed_top, exposed_bottom, i,
                        args.top_solid, args.bottom_solid))
        for i in range(len(regions))
    ]

    # ---------------------------------------------------------------- pass 2b
    if args.support:
        support, interface = support_columns(
            regions, layer_height, args.support_angle, SUPPORT_CONTACT)
    else:
        support = interface = [[] for _ in regions]

    # Infill reaches to the inner face of the innermost wall, plus a little
    # overlap, instead of stopping short of it.
    infill_inset = args.perimeters * line_width - INFILL_OVERLAP * line_width
    spacing = line_width / (args.infill / 100.0) if args.infill > 0 else 0.0
    top = next((i for i in range(len(regions) - 1, -1, -1) if regions[i]),
               len(regions) - 1) * layer_height + layer_height

    # ---------------------------------------------------------------- pass 3
    out_path = args.output or args.stl.with_name(f"{args.stl.stem}-{machine.key}.gcode")
    filament_mm = 0.0
    support_mm = 0.0
    layers_with_geometry = 0
    layers_with_support = 0
    preview_layers: list[list] = []
    wants_preview = args.preview is not None or args.open_preview
    preview_stride = max(1, len(regions) // 40)

    with out_path.open("w") as out:
        out.write("; sliced by the print-ready class skill\n")
        out.write(f"; machine = {machine.name}\n")
        out.write(f"; layer_height = {layer_height} mm\n")
        out.write(f"; infill = {args.infill}%\n")
        out.write(f"; perimeters = {args.perimeters}\n")
        out.write(f"; line_width = {line_width} mm\n")
        out.write(f"; top_solid_layers = {args.top_solid}\n")
        out.write(f"; bottom_solid_layers = {args.bottom_solid}\n")
        out.write(f"; filament_diameter = {FILAMENT_DIAMETER} mm\n")
        out.write(profiles.start_gcode(machine, first_layer_bounds))

        for index, region in enumerate(regions):
            layer_support = support[index] if args.support else []
            # A support column often passes through layers where the part is
            # absent, so the test is "part OR support", not just part.
            if not region and not layer_support:
                continue
            layers_with_geometry += 1
            if layer_support:
                layers_with_support += 1
            # The marker is written here rather than before the loop so layers
            # come out in order even when support starts below the part.
            out.write(f";LAYER:{index}\nG1 Z{(index + 1) * layer_height:.3f} F720\n")
            feed = 900 if index == 0 else 1800

            # Perimeters: the whole region shrunk by half a line width, then by
            # one more line width per extra wall. Clipper moves hole boundaries
            # outward as it does this, which is what sizes holes correctly.
            wall_paths = []
            for wall in range(args.perimeters):
                delta = -(line_width / 2.0 + wall * line_width)
                for path in geom.offset(region, delta):
                    wall_paths.append(path)
                    filament_mm += emit_path(out, path, True, line_width,
                                             layer_height, feed, 9000)

            # Infill: solid where a surface is exposed, sparse everywhere else.
            infill_region = geom.offset(region, -infill_inset) if region else []
            angle = 45.0 if index % 2 == 0 else 135.0

            drawn = []
            if infill_region:
                solid = solid_area(regions, exposed_top, exposed_bottom, index,
                                   args.top_solid, args.bottom_solid)
                solid = geom.intersection(solid, infill_region) if solid else []
                sparse = (geom.difference(infill_region, solid) if solid
                          else infill_region)
                for part, part_spacing in ((solid, line_width), (sparse, spacing)):
                    if not part or part_spacing <= 0:
                        continue
                    for start, end in geom.scanline_infill(part, part_spacing,
                                                           angle):
                        drawn.append((start, end))
                        filament_mm += emit_path(out, [start, end], False,
                                                 line_width, layer_height,
                                                 feed, 9000)

            # Support: a dense contact patch under the overhang, sparse below
            # it. Both use the narrower support extrusion width.
            support_drawn = []
            if layer_support:
                contact = interface[index]
                body = (geom.difference(layer_support, contact) if contact
                        else layer_support)
                for part, part_spacing, part_feed in (
                    (contact, SUPPORT_INTERFACE_SPACING, SUPPORT_INTERFACE_FEED),
                    (body, SUPPORT_BODY_SPACING, SUPPORT_FEED),
                ):
                    if not part or part_spacing <= 0:
                        continue
                    for start, end in geom.scanline_infill(part, part_spacing,
                                                           angle):
                        support_drawn.append((start, end))
                        used = emit_path(out, [start, end], False,
                                         SUPPORT_LINE_WIDTH, layer_height,
                                         part_feed, 9000)
                        filament_mm += used
                        support_mm += used

            if wants_preview and index % preview_stride == 0:
                preview_layers.append(
                    (index * layer_height, wall_paths, drawn, support_drawn))

        out.write(profiles.end_gcode(machine, height))

    grams = filament_mm * FILAMENT_AREA * 1.24 / 1000.0
    solid_count = sum(1 for i, r in enumerate(regions) if r and solid_flags[i])
    print(f"machine    : {machine.name} ({args.nozzle} mm nozzle, PLA)")
    print(f"layers     : {layers_with_geometry} with geometry, "
          f"{solid_count} with a solid surface")
    if args.support:
        print(f"support    : {layers_with_support} layers, "
              f"{support_mm / 1000.0:.2f} m "
              f"(~{support_mm * FILAMENT_AREA * 1.24 / 1000.0:.1f} g)")
    print(f"filament   : {filament_mm / 1000.0:.2f} m  (~{grams:.1f} g)")
    print(f"wrote      : {out_path}")

    if wants_preview:
        target = args.preview or out_path.with_suffix(".png")
        try:
            import preview as preview_module
        except ImportError:
            print("note       : no preview written - Pillow is not available",
                  file=sys.stderr)
        else:
            preview_module.render(target, machine, preview_layers,
                                  layer_height, args.infill)
            print(f"preview    : {target}")
            if args.open_preview:
                import webbrowser
                webbrowser.open(target.resolve().as_uri())

    if args.infill <= 0:
        print("note       : infill was 0%, so parts are hollow shells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
