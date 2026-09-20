"""Wire routing and drawing.

Endpoint syntax in a circuit file:
    board.GPIO2   -> a pin on the ESP32 board, by its silkscreen name
    bb.2.a        -> breadboard hole at column 2, row a

Routing is automatic: a wire leaves a board pin sideways into a vertical
"gutter" between the board and the breadboard, then runs to its hole. Wires
that cross the board/breadboard gap are given their own lane so they never
overlap. Override with `via:` (explicit waypoints) if you want a specific path.
"""

from .board import find_pin
from .layout import BOT_ROWS, TOP_ROWS

COLOURS = {"red": "#e02020", "black": "#2b2b2b", "blue": "#2b6cb0",
           "green": "#2f9e44", "yellow": "#e8c22a", "orange": "#e07a1f",
           "white": "#e8e8ee", "purple": "#7a4fbf", "grey": "#9aa0a6"}


def parse_endpoint(L, board, text):
    """Return ("board", (x, y)) or ("bb", (col, row), (x, y))."""
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
    raise ValueError(f"cannot parse endpoint {text!r} — use 'board.PIN' or 'bb.COL.ROW'")


def wire_holes(L, board, spec):
    """Breadboard holes this wire touches (for column highlighting)."""
    holes = []
    for end in (spec["from"], spec["to"]):
        parsed = parse_endpoint(L, board, end)
        if parsed[0] == "bb":
            holes.append(parsed[1])
    return holes


def route(L, board, spec, lane):
    if spec.get("via"):
        pts = []
        a = parse_endpoint(L, board, spec["from"])
        b = parse_endpoint(L, board, spec["to"])
        pts.append(a[2] if a[0] == "bb" else a[1])
        pts.extend([tuple(p) for p in spec["via"]])
        pts.append(b[2] if b[0] == "bb" else b[1])
        return pts

    a = parse_endpoint(L, board, spec["from"])
    b = parse_endpoint(L, board, spec["to"])

    if a[0] == "board" and b[0] == "bb":
        px, py = a[1]
        hx, hy = b[2]
        gx = L.gutter_x(lane) if px > L.board_x + L.board_w / 2 else -L.gutter_x(lane)
        return [(px, py), (gx, py), (gx, hy), (hx, hy)]

    if a[0] == "bb" and b[0] == "board":
        hx, hy = a[2]
        px, py = b[1]
        gx = L.gutter_x(lane) if px > L.board_x + L.board_w / 2 else -L.gutter_x(lane)
        return [(hx, hy), (hx, L.channel), (gx, L.channel), (gx, py), (px, py)]

    # breadboard to breadboard — hop through the centre channel
    hx1, hy1 = a[2]
    hx2, hy2 = b[2]
    return [(hx1, hy1), (hx1, L.channel), (hx2, L.channel), (hx2, hy2)]


def draw_wire(add, L, board, spec, lane):
    pts = route(L, board, spec, lane)
    colour = COLOURS.get(str(spec.get("color", "red")).lower(), spec.get("color", "#e02020"))
    path = " ".join(f"{x},{y}" for x, y in pts)
    add(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="7" '
        f'stroke-linejoin="round" stroke-linecap="round" opacity="0.95"/>')

    # plug marker where the wire enters a breadboard hole
    for end in (spec["from"], spec["to"]):
        parsed = parse_endpoint(L, board, end)
        if parsed[0] == "bb":
            x, y = parsed[2]
            add(f'<circle cx="{x}" cy="{y}" r="6.5" fill="none" stroke="#333" '
                f'stroke-width="2.5" opacity="0.5"/>')
