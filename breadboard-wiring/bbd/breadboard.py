"""Draw the breadboard: body, power rails, tie-point rows, net highlights."""

BODY = "#f4f1ea"
EDGE = "#cfc9bb"
HOLE = "#b9b3a6"
RAIL_RED = "#d94a4a"
RAIL_BLUE = "#4a7fd9"
NET = "#ffe9a8"
NET_LINE = "#e0b64a"

from .layout import BOT_ROWS, TOP_ROWS


def draw_breadboard(add, L, spec):
    bb = (spec.get("breadboard") or {})
    holes = bb.get("highlight_holes") or []
    labels = bb.get("labels") or {}

    add(f'<rect x="{L.bb_x}" y="{L.bb_y}" width="{L.bb_w}" height="{L.bb_h}" rx="14" '
        f'fill="{BODY}" stroke="{EDGE}" stroke-width="3" filter="url(#sh)"/>')
    add(f'<text x="{L.bb_x+22}" y="{L.bb_y+26}" font-size="13" font-weight="700" '
        f'fill="#a49c8a">BREADBOARD</text>')

    # centre channel
    add(f'<line x1="{L.bb_x+18}" y1="{L.channel}" x2="{L.bb_x+L.bb_w-18}" '
        f'y2="{L.channel}" stroke="#e2dccd" stroke-width="10"/>')

    # power rails
    for y, colour, sign in ((L.rail_top[0], RAIL_RED, "+"), (L.rail_top[1], RAIL_BLUE, "\u2212"),
                            (L.rail_bot[0], RAIL_RED, "+"), (L.rail_bot[1], RAIL_BLUE, "\u2212")):
        add(f'<line x1="{L.col_x(0)-20}" y1="{y}" x2="{L.col_x(L.ncol-1)+20}" y2="{y}" '
            f'stroke="{colour}" stroke-width="2.5" opacity="0.5"/>')
        add(f'<text x="{L.col_x(0)-34}" y="{y+5}" font-size="14" font-weight="700" '
            f'fill="{colour}" text-anchor="end">{sign}</text>')
        for i in range(L.ncol):
            add(f'<circle cx="{L.col_x(i)}" cy="{y}" r="3.4" fill="{HOLE}"/>')

    # tie-point rows
    for y in L.row_top + L.row_bot:
        for i in range(L.ncol):
            add(f'<circle cx="{L.col_x(i)}" cy="{y}" r="3.4" fill="{HOLE}"/>')

    # highlight each tie-point group that forms a single net
    groups = set()
    for col, row in holes:
        groups.add((int(col), str(row).lower() in BOT_ROWS))
    for col, bottom in sorted(groups):
        rows = L.row_bot if bottom else L.row_top
        y0, y1 = rows[0] - 16, rows[-1] + 16
        add(f'<rect x="{L.col_x(col)-16}" y="{y0}" width="32" height="{y1-y0}" rx="16" '
            f'fill="{NET}" opacity="0.75"/>')
        for y in rows:
            add(f'<circle cx="{L.col_x(col)}" cy="{y}" r="3.4" fill="{HOLE}"/>')
        add(f'<line x1="{L.col_x(col)}" y1="{rows[0]}" x2="{L.col_x(col)}" '
            f'y2="{rows[-1]}" stroke="{NET_LINE}" stroke-width="2" opacity="0.85"/>')

    # free-form labels: [{text: "one net", at: [col, row], offset: [dx, dy]}]
    for item in labels:
        item = item or {}
        text = item.get("text", "")
        col, row = item.get("at", [0, "a"])
        dx, dy = item.get("offset", [0, -30])
        add(f'<text x="{L.col_x(col)+dx}" y="{L.row_y(row)+dy}" font-size="12.5" '
            f'font-weight="700" fill="#8a6a10" '
            f'text-anchor="{item.get("anchor", "middle")}">{text}</text>')
