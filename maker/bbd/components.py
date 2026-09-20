"""Component library.

Each draw_* function takes (add, L, spec) and appends SVG elements. They also
expose the breadboard holes they occupy via `holes()`, which the renderer uses
to work out which columns to highlight as a single net.
"""

DIGIT_COLOUR = {0: "black", 1: "brown", 2: "red", 3: "orange", 4: "yellow",
                5: "green", 6: "blue", 7: "violet", 8: "grey", 9: "white"}
HEX = {"black": "#1a1a1a", "brown": "#7a4a1e", "red": "#d02a2a",
       "orange": "#e07a1f", "yellow": "#e8c22a", "green": "#2f9e44",
       "blue": "#2b6cb0", "violet": "#7a4fbf", "grey": "#9aa0a6",
       "white": "#f2f2f2", "gold": "#d4af37", "silver": "#c0c0c0"}
LED_COLOUR = {"red": ("#e03030", "#9c1616", "#f47c7c"),
              "green": ("#2fbf5a", "#187a35", "#7fe0a0"),
              "blue": ("#3b7dd8", "#1f4a8a", "#8fbaf0"),
              "yellow": ("#e8c22a", "#a88a10", "#f5e08a"),
              "white": ("#e8e8ee", "#9a9aa4", "#ffffff")}


def parse_ohms(value):
    s = str(value).strip().lower()
    for junk in ("\u03c9", "ohms", "ohm", "r"):
        s = s.replace(junk, "")
    mult = 1.0
    if s.endswith("k"):
        mult, s = 1e3, s[:-1]
    elif s.endswith("m"):
        mult, s = 1e6, s[:-1]
    return float(s) * mult


def bands_for(value):
    """Return the four band colours for a resistor value (2 sig digits)."""
    x, exp = float(parse_ohms(value)), 0
    while x >= 100:
        x, exp = x / 10, exp + 1
    while x < 10:
        x, exp = x * 10, exp - 1
    d1, d2 = int(x) // 10, int(x) % 10
    return [DIGIT_COLOUR[d1], DIGIT_COLOUR[d2], DIGIT_COLOUR[exp], "gold"]


# --------------------------------------------------------------------------
# resistor
# --------------------------------------------------------------------------
def holes_resistor(L, spec):
    col, row = spec["from"]
    return [(col, row), (col + int(spec.get("span", 4)), row)]


def draw_resistor(add, L, spec):
    col, row = spec["from"]
    span = int(spec.get("span", 4))
    y = L.row_y(row)
    x1, x2 = L.col_x(col), L.col_x(col + span)
    lead = min(34, (x2 - x1) / 4)

    add(f'<line x1="{x1}" y1="{y}" x2="{x1+lead}" y2="{y}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<line x1="{x2-lead}" y1="{y}" x2="{x2}" y2="{y}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<rect x="{x1+lead}" y="{y-16}" width="{x2-x1-2*lead}" height="32" rx="12" '
        f'fill="#ecdcae" stroke="#b09a6a" stroke-width="2"/>')

    bands = spec.get("bands") or bands_for(spec.get("value", 220))
    bx, bw = x1 + lead + 12, 13
    for i, name in enumerate(bands):
        add(f'<rect x="{bx + i*18}" y="{y-16}" width="{bw}" height="32" '
            f'fill="{HEX.get(name, name)}"/>')

    if spec.get("value") is not None:
        label = str(spec["value"])
        if not label.lower().endswith(("\u03a9", "ohm")):
            label += " \u03a9"
        add(f'<text x="{(x1+x2)/2}" y="{y-28}" font-size="16" font-weight="700" '
            f'fill="#6b4423" text-anchor="middle">{label}</text>')


# --------------------------------------------------------------------------
# LED
# --------------------------------------------------------------------------
def holes_led(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_led(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    x1, x2 = L.col_x(col), L.col_x(col + 1)
    cx, cy = (x1 + x2) / 2, y - 40
    r = max(20, min(26, L.dcol / 2.8))
    body, edge, shine = LED_COLOUR.get(spec.get("color", "red"), LED_COLOUR["red"])

    add(f'<line x1="{x1}" y1="{y}" x2="{x1}" y2="{cy}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<line x1="{x2}" y1="{y}" x2="{x2}" y2="{cy}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{body}" stroke="{edge}" stroke-width="2.5"/>')
    add(f'<circle cx="{cx-r*0.3}" cy="{cy-r*0.3}" r="{r*0.38}" fill="{shine}" opacity="0.6"/>')
    add(f'<path d="M{cx-r*0.7} {cy+r*0.7} l{r*1.4} 0" stroke="{edge}" '
        f'stroke-width="3.5" stroke-linecap="round"/>')

    if spec.get("label", True):
        add(f'<text x="{cx}" y="{cy-r-14}" font-size="15" font-weight="700" '
            f'fill="{edge}" text-anchor="middle">{spec.get("label_text", "LED")}</text>')
    add(f'<text x="{x2+30}" y="{y+34}" font-size="12.5" fill="#8a8a8a">'
        f'flat side = cathode (\u2212)</text>')
    add(f'<text x="{x1-14}" y="{y+34}" font-size="12.5" font-weight="700" '
        f'fill="{edge}" text-anchor="end">anode (+)</text>')


# --------------------------------------------------------------------------
# push button (4 legs, 0.3" spacing)
# --------------------------------------------------------------------------
def holes_button(L, spec):
    col, row = spec["at"]
    rows = L.row_top if str(row).lower() in "abcde" else L.row_bot
    i = rows.index(L.row_y(row))
    r2 = "abcde"[i + 1] if rows is L.row_top else "fghij"[i + 1]
    return [(col, row), (col, r2), (col + 3, row), (col + 3, r2)]


def draw_button(add, L, spec):
    col, row = spec["at"]
    y1, y2 = L.row_y(row), L.row_y(_next_row(row))
    x1, x2 = L.col_x(col), L.col_x(col + 3)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

    for x in (x1, x2):
        for y in (y1, y2):
            add(f'<circle cx="{x}" cy="{y}" r="6" fill="#b9b3a6"/>')
    add(f'<rect x="{x1+10}" y="{y1-14}" width="{x2-x1-20}" height="{y2-y1+28}" rx="8" '
        f'fill="#3a3a3f" stroke="#202024" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="14" fill="#e03030" stroke="#9c1616" stroke-width="2"/>')
    if spec.get("label", True):
        add(f'<text x="{cx}" y="{y1-26}" font-size="15" font-weight="700" fill="#3a3a3f" '
            f'text-anchor="middle">{spec.get("label_text", "button")}</text>')


def _next_row(row):
    r = str(row).lower()
    if r in "abcde":
        return "abcde"["abcde".index(r) + 1]
    return "fghij"["fghij".index(r) + 1]


# --------------------------------------------------------------------------
# buzzer
# --------------------------------------------------------------------------
def holes_buzzer(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_buzzer(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    x1, x2 = L.col_x(col), L.col_x(col + 1)
    cx, cy = (x1 + x2) / 2, y - 42
    r = max(24, L.dcol * 0.42)

    add(f'<line x1="{x1}" y1="{y}" x2="{x1}" y2="{cy+r*0.4}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<line x1="{x2}" y1="{y}" x2="{x2}" y2="{cy+r*0.4}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#2b2b30" stroke="#15151a" stroke-width="2.5"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.35}" fill="#111"/>')
    add(f'<text x="{cx+r+8}" y="{cy-r+6}" font-size="12.5" fill="#8a8a8a">+</text>')
    if spec.get("label", True):
        add(f'<text x="{cx}" y="{cy-r-12}" font-size="15" font-weight="700" fill="#2b2b30" '
            f'text-anchor="middle">{spec.get("label_text", "buzzer")}</text>')


# --------------------------------------------------------------------------
# generic module (sensor boards etc.) — a labelled box with pins in one row
# --------------------------------------------------------------------------
def holes_module(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(len(spec.get("pins") or []))]


def draw_module(add, L, spec):
    col, row = spec["at"]
    pins = spec.get("pins") or []
    y = L.row_y(row)
    x1 = L.col_x(col) - L.dcol * 0.4
    x2 = L.col_x(col + max(len(pins) - 1, 1)) + L.dcol * 0.4
    h = int(spec.get("height", 110))
    top = y - h - 18

    for i in range(len(pins)):
        x = L.col_x(col + i)
        add(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{top+h}" stroke="#9a9a9a" stroke-width="3.5"/>')

    add(f'<rect x="{x1}" y="{top}" width="{x2-x1}" height="{h}" rx="8" '
        f'fill="{spec.get("fill", "#2f6f4f")}" stroke="#1d4732" stroke-width="2.5"/>')
    add(f'<text x="{(x1+x2)/2}" y="{top+34}" font-size="16" font-weight="700" fill="#fff" '
        f'text-anchor="middle">{spec.get("label_text", "module")}</text>')

    for i, name in enumerate(pins):
        x = L.col_x(col + i)
        add(f'<text x="{x}" y="{top+h+18}" font-size="11.5" fill="#444" '
            f'text-anchor="middle">{name}</text>')


REGISTRY = {
    "resistor": (draw_resistor, holes_resistor),
    "led": (draw_led, holes_led),
    "button": (draw_button, holes_button),
    "buzzer": (draw_buzzer, holes_buzzer),
    "module": (draw_module, holes_module),
}


def draw_component(add, L, spec):
    kind = spec.get("type")
    if kind not in REGISTRY:
        raise ValueError(f"unknown component {kind!r}. Known: {', '.join(sorted(REGISTRY))}")
    REGISTRY[kind][0](add, L, spec)


def component_holes(L, spec):
    kind = spec.get("type")
    if kind not in REGISTRY:
        raise ValueError(f"unknown component {kind!r}. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[kind][1](L, spec)
