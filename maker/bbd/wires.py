"""Wire routing and drawing.

Endpoint syntax in a circuit file:
    board.GPIO2   -> a pin on the ESP32 board, by its silkscreen name
    bb.2.a        -> breadboard hole at column 2, row a

Routing is automatic. Right-hand pins drop straight into the gutter between
the board and the breadboard. Left-hand pins leave left, run down the left
gutter, cross below the board in the corridor, climb the right-hand gutter and
enter the breadboard through the centre channel. Every wire gets its own lane
so runs never sit on top of each other. Override with `via:` (explicit
waypoints) if you want a specific path.
"""

from .board import find_pin
from .layout import BOT_ROWS, TOP_ROWS

COLOURS = {"red": "#e02020", "black": "#2b2b2b", "blue": "#2b6cb0",
           "green": "#2f9e44", "yellow": "#e8c22a", "orange": "#e07a1f",
           "white": "#e8e8ee", "purple": "#7a4fbf", "grey": "#9aa0a6"}

CHANNEL_OFFSETS = [0, -12, 12, -24, 24, -36, 36, -48, 48]


def parse_endpoint(L, board, text, parts=None):
    """Return ("board", (x, y)), ("bb", (col, row), (x, y)) or ("part", (x, y)).

    `parts` maps a component's `id` to its named terminals, so a wire can end
    on e.g. the driver's `driver.OUT1` screw terminal.
    """
    text = str(text).strip()
    if text.startswith("board."):
        name = text[len("board."):]
        return ("board", find_pin(L, board, name))
    if text.startswith("bb."):
        rest = text[len("bb."):]
        col, row = rest.split(".")
        col = int(col)
        L.row_y(row)  # validate
        return ("bb", (col, row), L.hole(col, row))
    if parts and "." in text:
        part_id, name = text.split(".", 1)
        if part_id in parts and name in parts[part_id]:
            return ("part", parts[part_id][name])
    raise ValueError(f"cannot parse endpoint {text!r} — use 'board.PIN', 'bb.COL.ROW' or 'part.TERMINAL'")


def _pin_side(L, parsed):
    """Which side of the board a parsed endpoint sits on."""
    px = parsed[1][0]
    return "L" if px < L.board_x + L.board_w / 2 else "R"


def assign_lanes(L, board, wires, parts=None):
    """Plan routing lanes: one per wire, plus side lanes for left-hand pins."""
    lanes = []
    gutter = left = corridor = 0
    for spec in wires:
        pin = None
        for end in (spec["from"], spec["to"]):
            parsed = parse_endpoint(L, board, end, parts)
            if parsed[0] == "part":
                pin = parsed
                break
            if parsed[0] == "board":
                pin = parsed
                break
        if pin is None:
            lanes.append({"side": "C"})
            continue
        if pin[0] == "part":
            lanes.append({"side": "P", "gutter": gutter})
            gutter += 1
            continue
        side = _pin_side(L, pin)
        if side == "L":
            lanes.append({"side": "L", "gutter": gutter, "left": left, "corridor": corridor})
            gutter += 1
            left += 1
            corridor += 1
        else:
            lanes.append({"side": "R", "gutter": gutter})
            gutter += 1
    return lanes


def wire_holes(L, board, spec, parts=None):
    """Breadboard holes this wire touches (for column highlighting)."""
    holes = []
    for end in (spec["from"], spec["to"]):
        parsed = parse_endpoint(L, board, end, parts)
        if parsed[0] == "bb":
            holes.append(parsed[1])
    return holes


def _channel_y(L, lane):
    return L.channel + CHANNEL_OFFSETS[lane.get("gutter", 0) % len(CHANNEL_OFFSETS)]


def _part_to_hole(L, term, hole, lane):
    """From a part terminal: down to the channel lane, across, then into the hole."""
    ax, ay = term
    hx, hy = hole
    cy = _channel_y(L, lane)
    return [(ax, ay), (ax, cy), (hx, cy), (hx, hy)]


def _board_to_hole(L, pin, hole, lane):
    px, py = pin
    hx, hy = hole
    gx = L.gutter_x(lane["gutter"])
    cy = _channel_y(L, lane)
    if lane["side"] == "L":
        lgx = L.left_gutter_x(lane["left"])
        ky = L.corridor_y(lane["corridor"])
        return [(px, py), (lgx, py), (lgx, ky), (gx, ky), (gx, cy), (hx, cy), (hx, hy)]
    return [(px, py), (gx, py), (gx, cy), (hx, cy), (hx, hy)]


def route(L, board, spec, lane, parts=None):
    if spec.get("via"):
        pts = []
        a = parse_endpoint(L, board, spec["from"], parts)
        b = parse_endpoint(L, board, spec["to"], parts)
        pts.append(a[2] if a[0] == "bb" else a[1])
        pts.extend([tuple(p) for p in spec["via"]])
        pts.append(b[2] if b[0] == "bb" else b[1])
        return pts

    a = parse_endpoint(L, board, spec["from"], parts)
    b = parse_endpoint(L, board, spec["to"], parts)

    if a[0] == "board" and b[0] == "bb":
        return _board_to_hole(L, a[1], b[2], lane)

    if a[0] == "bb" and b[0] == "board":
        return list(reversed(_board_to_hole(L, b[1], a[2], lane)))

    if a[0] == "part" and b[0] == "bb":
        return _part_to_hole(L, a[1], b[2], lane)

    if a[0] == "bb" and b[0] == "part":
        return list(reversed(_part_to_hole(L, b[1], a[2], lane)))

    if a[0] == "part" and b[0] == "part":
        ax, ay = a[1]
        bx2, by2 = b[1]
        cy = _channel_y(L, lane)
        return [(ax, ay), (ax, cy), (bx2, cy), (bx2, by2)]

    # breadboard to breadboard — hop through the centre channel
    hx1, hy1 = a[2]
    hx2, hy2 = b[2]
    return [(hx1, hy1), (hx1, L.channel), (hx2, L.channel), (hx2, hy2)]


def draw_wire(add, L, board, spec, lane, parts=None):
    pts = route(L, board, spec, lane, parts)
    colour = COLOURS.get(str(spec.get("color", "red")).lower(), spec.get("color", "#e02020"))
    path = " ".join(f"{x},{y}" for x, y in pts)
    add(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="7" '
        f'stroke-linejoin="round" stroke-linecap="round" opacity="0.95"/>')

    # plug marker where the wire enters a breadboard hole
    for end in (spec["from"], spec["to"]):
        parsed = parse_endpoint(L, board, end, parts)
        if parsed[0] == "bb":
            x, y = parsed[2]
            add(f'<circle cx="{x}" cy="{y}" r="6.5" fill="none" stroke="#333" '
                f'stroke-width="2.5" opacity="0.5"/>')
