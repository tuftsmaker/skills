"""Component library.

Each draw_* function takes (add, L, spec) and appends SVG elements. They also
expose the breadboard holes they occupy via `holes()`, which the renderer uses
to work out which tie-point group to highlight as a single net.

Footprints follow the real parts in the Freenove FNK0046 kit:
  - axial 2-lead parts span `span` columns (default 4 = 0.4")
  - 3-lead parts (potentiometer, transistor, servo) occupy 3 adjacent columns
  - 4-lead parts (RGB LED, LCD) occupy 4 adjacent columns
  - DIP packages (IC, 7-segment, bar graph) straddle the channel: pins/2 holes
    in row e and the same columns in row f, at true 0.3" row spacing
  - modules and cabled parts (servo, motor, battery, speaker) draw their body
    above a top-half row, or clear of the board edge for a bottom-half row,
    with leads down to the holes
"""

import math

from .layout import BOT_ROWS, TOP_ROWS

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

LEAD = "#9a9a9a"
DARK = "#2b2b30"
DARK_EDGE = "#15151a"
PAPER = "#fdfaf3"
WIRE_RED = "#e02020"
WIRE_BLACK = "#2b2b2b"


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
# small helpers
# --------------------------------------------------------------------------
def _lead(add, x1, y1, x2, y2, colour=LEAD, w=3.5):
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
        f'stroke-width="{w}"/>')


def _text(add, x, y, text, size=15, fill="#26262b", weight="700", anchor="middle"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{text}</text>')


def _bottom_half(row):
    return str(row).lower() in BOT_ROWS


def _attach_slot(L, row, height, pad=18):
    """Body hugging its row: above a top-half row, below a bottom-half row.

    Returns (row_y, top, bottom, direction), direction -1 = body above.
    """
    y = L.row_y(row)
    if _bottom_half(row):
        return y, y + pad, y + pad + height, +1
    return y, y - pad - height, y - pad, -1


def _module_slot(L, row, height, pad=18):
    """Like _attach_slot, but bottom-half bodies clear the breadboard edge."""
    y = L.row_y(row)
    if _bottom_half(row):
        top = max(y + pad, L.bb_y + L.bb_h + 10)
        return y, top, top + height, +1
    return y, y - pad - height, y - pad, -1


def _pin_labels(add, L, xs, row, names):
    """Pin names offset clear of the wire that arrives at each hole."""
    y = L.row_y(row)
    ty = y - 8 if _bottom_half(row) else y + 17
    for x, name in zip(xs, names):
        add(f'<text x="{x - 32}" y="{ty}" font-size="17" fill="#444" '
            f'text-anchor="middle">{name}</text>')


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
    if spec.get("polarity_notes", True):
        add(f'<text x="{x2+30}" y="{y+38}" font-size="15" fill="#8a8a8a">'
            f'flat side = cathode (\u2212)</text>')
        add(f'<text x="{x1-14}" y="{y+38}" font-size="15" font-weight="700" '
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
        f'fill="#2b2b30" stroke="#15151a" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="14" fill="#3a3a3f" stroke="#15151a" stroke-width="2"/>')
    add(f'<ellipse cx="{cx-4}" cy="{cy-5}" rx="5" ry="3" fill="#6d6d76" opacity="0.6"/>')
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
    # top label ring, like the real buzzers
    add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.62}" fill="#dcdce4" opacity="0.85"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.18}" fill="#2b2b30"/>')
    add(f'<text x="{cx+r+8}" y="{cy-r+6}" font-size="12.5" fill="#8a8a8a">+</text>')
    if spec.get("label", True):
        add(f'<text x="{cx}" y="{cy-r-12}" font-size="15" font-weight="700" fill="#2b2b30" '
            f'text-anchor="middle">{spec.get("label_text", "buzzer")}</text>')


# --------------------------------------------------------------------------
# axial diode (2 leads, polarity band)
# --------------------------------------------------------------------------
def holes_diode(L, spec):
    col, row = spec["from"]
    return [(col, row), (col + int(spec.get("span", 4)), row)]


def draw_diode(add, L, spec):
    col, row = spec["from"]
    span = int(spec.get("span", 4))
    y = L.row_y(row)
    x1, x2 = L.col_x(col), L.col_x(col + span)
    lead = min(34, (x2 - x1) / 4)

    _lead(add, x1, y, x1 + lead, y)
    _lead(add, x2 - lead, y, x2, y)
    bx1, bx2 = x1 + lead, x2 - lead
    add(f'<rect x="{bx1}" y="{y-15}" width="{bx2-bx1}" height="30" rx="7" '
        f'fill="{DARK}" stroke="{DARK_EDGE}" stroke-width="2"/>')
    band = spec.get("band", "right")
    bx = bx2 - 16 if band == "right" else bx1 + 4
    add(f'<rect x="{bx}" y="{y-15}" width="12" height="30" rx="3" fill="#c0c0c0"/>')
    if spec.get("label", True):
        _text(add, (x1 + x2) / 2, y - 28, spec.get("label_text", "diode"), 15, "#2b2b30")
    _text(add, bx2 + 14 if band == "right" else bx1 - 14, y + 6,
          "\u2212", 16, "#8a8a8a", anchor="start" if band == "right" else "end")


# --------------------------------------------------------------------------
# photoresistor / thermistor (2 leads)
# --------------------------------------------------------------------------
def holes_photoresistor(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_photoresistor(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    x1, x2 = L.col_x(col), L.col_x(col + 1)
    cx, cy = (x1 + x2) / 2, y - 46
    r = 24

    _lead(add, x1, y, cx - 9, cy + 18)
    _lead(add, x2, y, cx + 9, cy + 18)
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#efe9d8" stroke="#b09a6a" stroke-width="2.5"/>')
    add(f'<path d="M{cx-r*0.55} {cy} q{r*0.28} -{r*0.42} {r*0.55} 0 '
        f'q{r*0.28} {r*0.42} {r*0.55} 0" fill="none" stroke="#5a4a2a" stroke-width="2.5"/>')
    if spec.get("label", True):
        _text(add, cx, cy - r - 12, spec.get("label_text", "photoresistor"), 15, "#5a4a2a")


def holes_thermistor(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_thermistor(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    x1, x2 = L.col_x(col), L.col_x(col + 1)
    cx, cy = (x1 + x2) / 2, y - 42

    _lead(add, x1, y, cx - 12, cy + 8)
    _lead(add, x2, y, cx + 12, cy + 8)
    add(f'<ellipse cx="{cx}" cy="{cy}" rx="16" ry="12" fill="#3a3a3f" '
        f'stroke="{DARK_EDGE}" stroke-width="2"/>')
    add(f'<ellipse cx="{cx-4}" cy="{cy-3}" rx="5" ry="3.5" fill="#6d6d76" opacity="0.7"/>')
    if spec.get("label", True):
        _text(add, cx, cy - 24, spec.get("label_text", "thermistor"), 15, "#2b2b30")


# --------------------------------------------------------------------------
# potentiometer (3 legs in one row)
# --------------------------------------------------------------------------
def holes_potentiometer(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(3)]


def draw_potentiometer(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(3)]
    cx = (xs[0] + xs[2]) / 2
    _, top, bottom, _ = _attach_slot(L, row, 58, pad=16)
    attach = top if _bottom_half(row) else bottom

    for x in xs:
        _lead(add, x, y, x, attach)
    # metal body with a blue base, like the kit's pots
    add(f'<rect x="{xs[0]-24}" y="{top}" width="{xs[2]-xs[0]+48}" height="{bottom-top}" '
        f'rx="7" fill="#c9c9d1" stroke="#8a8a94" stroke-width="2"/>')
    add(f'<rect x="{xs[0]-24}" y="{bottom-14}" width="{xs[2]-xs[0]+48}" height="14" '
        f'rx="4" fill="#2b6cb0" stroke="#1a4a8a" stroke-width="1.5"/>')
    # threaded bushing + slotted shaft
    add(f'<circle cx="{cx}" cy="{(top+bottom)/2}" r="19" fill="#b9b9c2" '
        f'stroke="#8a8a94" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{(top+bottom)/2}" r="13" fill="#dcdce4" '
        f'stroke="#9a9aa4" stroke-width="1.5"/>')
    add(f'<line x1="{cx}" y1="{(top+bottom)/2 - 10}" x2="{cx}" y2="{(top+bottom)/2 + 10}" '
        f'stroke="#55555c" stroke-width="4" stroke-linecap="round"/>')
    if spec.get("label", True):
        _text(add, cx, top - 12, spec.get("label_text", "potentiometer"), 15, "#2b2b30")
    if spec.get("pins"):
        _pin_labels(add, L, xs, row, spec["pins"])


# --------------------------------------------------------------------------
# transistor (TO-92, 3 legs)
# --------------------------------------------------------------------------
def holes_transistor(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(3)]


def draw_transistor(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(3)]
    cx = (xs[0] + xs[2]) / 2
    _, top, bottom, _ = _attach_slot(L, row, 52, pad=14)
    attach = top if _bottom_half(row) else bottom
    r = (xs[2] - xs[0]) / 2 + 18

    for x in xs:
        _lead(add, x, y, x, attach)
    add(f'<path d="M{cx-r} {attach} A {r} {r} 0 0 1 {cx+r} {attach} Z" '
        f'fill="{DARK}" stroke="{DARK_EDGE}" stroke-width="2"/>')
    add(f'<line x1="{cx-r}" y1="{attach}" x2="{cx+r}" y2="{attach}" '
        f'stroke="{DARK_EDGE}" stroke-width="3"/>')
    kind = str(spec.get("kind", "npn")).upper()
    _text(add, cx, attach - 16, spec.get("label_text", kind), 14, "#e8e8ee")
    if spec.get("pins"):
        _pin_labels(add, L, xs, row, spec["pins"])


# --------------------------------------------------------------------------
# RGB LED (4 legs)
# --------------------------------------------------------------------------
def holes_rgb_led(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(4)]


def draw_rgb_led(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(4)]
    cx, cy, r = (xs[0] + xs[3]) / 2, y - 50, 46

    for i, x in enumerate(xs):
        spread = cx + (i - 1.5) * 12
        dy = (r * r - (spread - cx) ** 2) ** 0.5
        add(f'<polyline points="{x},{y} {x},{y-26} {spread},{cy+dy}" fill="none" '
            f'stroke="#9a9a9a" stroke-width="3.5" stroke-linejoin="round"/>')
    # clear water-clear lens with the three colour dies visible
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#e8eef4" stroke="#9a9aa4" stroke-width="2.5"/>')
    add(f'<circle cx="{cx-r*0.3}" cy="{cy-r*0.3}" r="{r*0.45}" fill="#ffffff" opacity="0.5"/>')
    for dx, dy, c in ((-13, -8, "#e03030"), (13, -8, "#2fbf5a"), (0, 11, "#3b7dd8")):
        add(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="7" fill="{c}" opacity="0.9"/>')
    if spec.get("label", True):
        _text(add, cx, cy - r - 12, spec.get("label_text", "RGB LED"), 15, "#3a3a3f")
    if spec.get("pins"):
        _pin_labels(add, L, xs, row, spec["pins"])


# --------------------------------------------------------------------------
# DIP packages straddling the channel (IC, 7-segment, bar graph)
# --------------------------------------------------------------------------
def _straddle(L, spec):
    """Shared geometry for dual-row parts: returns (xs, top, bottom)."""
    col = spec["at"][0]
    per = int(spec.get("pins", 16)) // 2
    xs = [L.col_x(col + i) for i in range(per)]
    ye, yf = L.row_y("e"), L.row_y("f")
    cy = (ye + yf) / 2
    h = int(spec.get("height", 76))
    return xs, ye, yf, cy - h / 2, cy + h / 2


def holes_ic(L, spec):
    col = spec["at"][0]
    per = int(spec.get("pins", 16)) // 2
    return [(col + i, "e") for i in range(per)] + [(col + i, "f") for i in range(per)]


def draw_ic(add, L, spec):
    xs, ye, yf, top, bottom = _straddle(L, spec)
    n = int(spec.get("pins", 16))
    per = n // 2
    x1, x2 = xs[0] - 30, xs[-1] + 30

    for x in xs:
        _lead(add, x, ye, x, top)
        _lead(add, x, yf, x, bottom)
    add(f'<rect x="{x1}" y="{top}" width="{x2-x1}" height="{bottom-top}" rx="7" '
        f'fill="{DARK}" stroke="{DARK_EDGE}" stroke-width="2.5"/>')
    # moulded top band and prominent silver legs, like a real DIP package
    add(f'<rect x="{x1+8}" y="{top+5}" width="{x2-x1-16}" height="9" rx="4" '
        f'fill="#3a3a3f" opacity="0.9"/>')
    for x in xs:
        add(f'<rect x="{x-7}" y="{top-8}" width="14" height="11" rx="2" '
            f'fill="#dcdce4" stroke="#9a9aa4" stroke-width="1"/>')
        add(f'<rect x="{x-7}" y="{bottom-3}" width="14" height="11" rx="2" '
            f'fill="#dcdce4" stroke="#9a9aa4" stroke-width="1"/>')
    # pin-1 end notch and dot
    cy = (top + bottom) / 2
    add(f'<path d="M{x1} {cy-13} A 13 13 0 0 1 {x1} {cy+13} Z" fill="{PAPER}"/>')
    add(f'<circle cx="{x1+20}" cy="{top+16}" r="5" fill="#55555c"/>')
    if spec.get("label_text"):
        _text(add, (x1 + x2) / 2, cy + 6, spec["label_text"], 16, "#e8e8ee")
    if spec.get("pin_labels"):
        for i in range(per):
            _text(add, xs[i], ye - 11, str(i + 1), 16, "#666")
            _text(add, xs[i], yf + 22, str(n - i), 16, "#666")


def holes_display_7seg(L, spec):
    return holes_ic(L, {**spec, "pins": int(spec.get("pins", 10))})


def draw_display_7seg(add, L, spec):
    xs, ye, yf, top, bottom = _straddle(L, {**spec, "pins": int(spec.get("pins", 10)), "height": 84})
    per = int(spec.get("pins", 10)) // 2
    x1, x2 = xs[0] - 36, xs[-1] + 36

    for x in xs:
        _lead(add, x, ye, x, top)
        _lead(add, x, yf, x, bottom)
    add(f'<rect x="{x1}" y="{top}" width="{x2-x1}" height="{bottom-top}" rx="8" '
        f'fill="{DARK}" stroke="{DARK_EDGE}" stroke-width="2.5"/>')

    # light grey face with lit red segments, like the real display
    fx, fy = x1 + 16, top + 10
    fw, fh = (x2 - x1) - 32, (bottom - top) - 20
    add(f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="4" '
        f'fill="#b9b9c2" stroke="#8a8a94" stroke-width="1.5"/>')
    cx, cy = (fx + fx + fw) / 2, (fy + fy + fh) / 2
    w, h, t = min(104, fw * 0.45), fh * 0.78, 8
    seg = "#e02020"
    def hseg(yy):
        add(f'<line x1="{cx-w/2}" y1="{yy}" x2="{cx+w/2}" y2="{yy}" stroke="{seg}" '
            f'stroke-width="{t}" stroke-linecap="round"/>')
    def vseg(xx, yy1, yy2):
        add(f'<line x1="{xx}" y1="{yy1}" x2="{xx}" y2="{yy2}" stroke="{seg}" '
            f'stroke-width="{t}" stroke-linecap="round"/>')
    hseg(cy - h / 2)
    vseg(cx - w / 2, cy - h / 2 + t, cy - t)
    vseg(cx + w / 2, cy - h / 2 + t, cy - t)
    hseg(cy)
    vseg(cx - w / 2, cy + t, cy + h / 2 - t)
    vseg(cx + w / 2, cy + t, cy + h / 2 - t)
    hseg(cy + h / 2)
    add(f'<circle cx="{cx+w/2+13}" cy="{cy+h/2}" r="4" fill="{seg}"/>')
    if spec.get("label_text"):
        _text(add, x1 + 22, top - 10, spec["label_text"], 14, "#3a3a3f", anchor="start")


def holes_bar_graph(L, spec):
    return holes_ic(L, {**spec, "pins": int(spec.get("pins", 20))})


def draw_bar_graph(add, L, spec):
    xs, ye, yf, top, bottom = _straddle(L, {**spec, "pins": int(spec.get("pins", 20)), "height": 84})
    per = int(spec.get("pins", 20)) // 2
    x1, x2 = xs[0] - 26, xs[-1] + 26

    for x in xs:
        _lead(add, x, ye, x, top)
        _lead(add, x, yf, x, bottom)
    add(f'<rect x="{x1}" y="{top}" width="{x2-x1}" height="{bottom-top}" rx="8" '
        f'fill="{DARK}" stroke="{DARK_EDGE}" stroke-width="2.5"/>')

    # ten lit red segment windows, like the tutorial's flowing-water demo
    inner_x1, inner_x2 = x1 + 18, x2 - 18
    step = (inner_x2 - inner_x1) / per
    for i in range(per):
        wx = inner_x1 + i * step
        add(f'<rect x="{wx}" y="{top+16}" width="{step-9}" height="{bottom-top-32}" '
            f'rx="4" fill="#e02020" opacity="0.92"/>')
        add(f'<rect x="{wx}" y="{top+16}" width="{step-9}" height="{bottom-top-32}" '
            f'rx="4" fill="none" stroke="#9c1616" stroke-width="1"/>')
    if spec.get("label_text"):
        _text(add, x1 + 20, top - 10, spec["label_text"], 14, "#3a3a3f", anchor="start")


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
    _, top, bottom, _ = _module_slot(L, row, h)
    attach = top if _bottom_half(row) else bottom

    for i in range(len(pins)):
        x = L.col_x(col + i)
        _lead(add, x, y, x, attach)
    add(f'<rect x="{x1}" y="{top}" width="{x2-x1}" height="{h}" rx="8" '
        f'fill="{spec.get("fill", "#2f6f4f")}" stroke="#1d4732" stroke-width="2.5"/>')
    _text(add, (x1 + x2) / 2, top + 34, spec.get("label_text", "module"), 16, "#fff")
    if pins:
        _pin_labels(add, L, [L.col_x(col + i) for i in range(len(pins))], row, pins)


# --------------------------------------------------------------------------
# servo (3 wires: brown GND, red 5V, orange signal)
# --------------------------------------------------------------------------
def holes_servo(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(3)]


def draw_servo(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(3)]
    cx = (xs[0] + xs[2]) / 2
    _, top, bottom, _ = _module_slot(L, row, 92)
    attach = top if _bottom_half(row) else bottom

    colours = ["#7a4a1e", WIRE_RED, "#e07a1f"]
    names = ["GND", "5V", "SIG"]
    for x, c in zip(xs, colours):
        _lead(add, x, y, x, attach, colour=c, w=5)

    bw, bh = 150, 92
    bx1 = cx - bw / 2
    up = -1 if not _bottom_half(row) else +1
    far = top if up < 0 else bottom
    # translucent blue SG90 case with a pale top and white horn
    add(f'<rect x="{bx1}" y="{top+10}" width="{bw}" height="{bh-10}" rx="10" '
        f'fill="#3a6ea5" stroke="#26496e" stroke-width="2.5"/>')
    for fx in (bx1 - 16, bx1 + bw - 12):
        add(f'<rect x="{fx}" y="{top}" width="28" height="16" rx="3" '
            f'fill="#5b8fc9" stroke="#26496e" stroke-width="1.5"/>')
        add(f'<circle cx="{fx+14}" cy="{top+8}" r="4" fill="#26496e"/>')
    add(f'<circle cx="{cx}" cy="{top+40}" r="24" fill="#cfe0f5" stroke="#26496e" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{top+40}" r="9" fill="#5b8fc9"/>')
    add(f'<circle cx="{cx+32}" cy="{top+52}" r="13" fill="#cfe0f5" stroke="#26496e" stroke-width="1.5"/>')
    add(f'<circle cx="{cx+32}" cy="{top+52}" r="4" fill="#5b8fc9"/>')
    # cable boot where the wires leave the case
    boot_y = attach - (10 if up < 0 else -10)
    add(f'<rect x="{xs[0]-8}" y="{boot_y-8}" width="{xs[2]-xs[0]+16}" height="16" rx="4" '
        f'fill="#202024"/>')
    horn_y = far + up * 26
    add(f'<rect x="{cx-7}" y="{horn_y + (up*34 if up < 0 else 0)}" width="14" height="46" rx="7" '
        f'fill="#f2f2f2" stroke="#c9c9d1" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{horn_y}" r="15" fill="#f2f2f2" stroke="#c9c9d1" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{horn_y}" r="4.5" fill="#9a9aa4"/>')
    _text(add, cx, (top + bottom) / 2 + 5, "SG90", 15, "#cfe0f5")
    _pin_labels(add, L, xs, row, names)


# --------------------------------------------------------------------------
# TT gearbox motor + wheel (2 wires)
# --------------------------------------------------------------------------
def holes_motor(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_motor(add, L, spec):
    """Yellow-gearbox TT motor with its wheel, seen from above: silver can,
    yellow gearbox, output shaft, and the wheel edge-on crossing the shaft."""
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col), L.col_x(col + 1)]
    cx = (xs[0] + xs[1]) / 2
    asm_h = 116
    _, top, bottom, _ = _module_slot(L, row, asm_h)
    attach = top if _bottom_half(row) else bottom

    for x, c in zip(xs, [WIRE_RED, WIRE_BLACK]):
        _lead(add, x, y, x, attach, colour=c, w=5)

    up = -1 if not _bottom_half(row) else 1
    cy = attach + up * (asm_h / 2 + 4)
    ax = cx - 186

    # motor can, with end cap and the two solder terminals
    add(f'<rect x="{ax}" y="{cy-33}" width="92" height="66" rx="12" '
        f'fill="#c9c9d1" stroke="#8a8a94" stroke-width="2.5"/>')
    add(f'<rect x="{ax}" y="{cy-33}" width="16" height="66" rx="10" fill="#9aa0a6"/>')
    for ty in (cy - 22, cy + 22):
        add(f'<circle cx="{ax+7}" cy="{ty}" r="5.5" fill="#c9a06a" stroke="#8a6a3a" stroke-width="1.5"/>')
    _text(add, ax + 54, cy + 5, "DC 9V", 11, "#55555c")

    # yellow gearbox
    gx = ax + 92
    add(f'<rect x="{gx}" y="{cy-42}" width="150" height="84" rx="8" '
        f'fill="#e8b32a" stroke="#b08a10" stroke-width="2.5"/>')
    add(f'<line x1="{gx+20}" y1="{cy-42}" x2="{gx+20}" y2="{cy+42}" '
        f'stroke="#d0a020" stroke-width="2"/>')
    add(f'<circle cx="{gx+9}" cy="{cy}" r="11" fill="#f0c85a" stroke="#b08a10" stroke-width="2"/>')

    # output shaft and the wheel mounted on it (edge-on)
    sx = gx + 150
    add(f'<rect x="{sx}" y="{cy-8}" width="104" height="16" rx="6" '
        f'fill="#f0c85a" stroke="#b08a10" stroke-width="2"/>')
    wx = sx + 66
    add(f'<rect x="{wx-15}" y="{cy-58}" width="30" height="116" rx="13" '
        f'fill="#f2f2f2" stroke="#c9c9d1" stroke-width="2"/>')
    add(f'<rect x="{wx-3}" y="{cy-58}" width="6" height="116" rx="3" fill="#dcdce4"/>')
    add(f'<circle cx="{wx}" cy="{cy}" r="9" fill="#b9b9c2" stroke="#8a8a94" stroke-width="1.5"/>')

    if spec.get("label", True):
        _text(add, cx, cy + up * (asm_h / 2 + 6) + (0 if up > 0 else 0),
              spec.get("label_text", "TT motor + wheel"), 17, "#3a3a3f",
              anchor="middle")
    _pin_labels(add, L, xs, row, spec.get("pins", ["+", "\u2212"]))


# --------------------------------------------------------------------------
# 9V battery + clip (2 wires)
# --------------------------------------------------------------------------
def holes_battery(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_battery(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col), L.col_x(col + 1)]
    cx = (xs[0] + xs[1]) / 2
    _, top, bottom, _ = _module_slot(L, row, 88)
    attach = top if _bottom_half(row) else bottom

    for x, c in zip(xs, [WIRE_RED, WIRE_BLACK]):
        _lead(add, x, y, x, attach, colour=c, w=5)

    bw, bh = 116, 78
    bx1 = cx - bw / 2
    # 9V body: dark case, amber top band and a clip, like the real battery
    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="{bh}" rx="8" '
        f'fill="#2b2b30" stroke="#15151a" stroke-width="2.5"/>')
    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="24" rx="8" '
        f'fill="#c08a4a" stroke="#8a5f30" stroke-width="1.5"/>')
    add(f'<rect x="{bx1+16}" y="{top-12}" width="{bw-32}" height="14" rx="4" '
        f'fill="#3a3a3f" stroke="#15151a" stroke-width="1.5"/>')
    for sx in (cx - 26, cx + 26):
        add(f'<rect x="{sx-8}" y="{top-16}" width="16" height="8" rx="2" fill="#c9c9d1"/>')
    _text(add, cx, top + bh / 2 + 16, "9V", 22, "#f2f2f2")
    if spec.get("label", True):
        _text(add, cx, top - 26, spec.get("label_text", "battery pack"), 17, "#3a3a3f")
    _pin_labels(add, L, xs, row, spec.get("pins", ["+", "\u2212"]))


# --------------------------------------------------------------------------
# speaker (2 wires)
# --------------------------------------------------------------------------
def holes_speaker(L, spec):
    col, row = spec["at"]
    return [(col, row), (col + 1, row)]


def draw_speaker(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col), L.col_x(col + 1)]
    cx = (xs[0] + xs[1]) / 2
    _, top, bottom, _ = _module_slot(L, row, 84)
    attach = top if _bottom_half(row) else bottom

    for x, c in zip(xs, [WIRE_RED, WIRE_BLACK]):
        _lead(add, x, y, x, attach, colour=c, w=5)

    cy = (top + bottom) / 2
    # square black frame with a silver-ringed cone, like the real speaker
    add(f'<rect x="{cx-46}" y="{cy-46}" width="92" height="92" rx="8" '
        f'fill="#2b2b30" stroke="#15151a" stroke-width="2.5"/>')
    for hx2, hy2 in ((cx-36, cy-36), (cx+36, cy-36), (cx-36, cy+36), (cx+36, cy+36)):
        add(f'<circle cx="{hx2}" cy="{hy2}" r="4" fill="#15151a"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="33" fill="#3a3a3f" stroke="#202024" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="28" fill="none" stroke="#c9c9d1" stroke-width="3"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="12" fill="#15151a"/>')
    add(f'<ellipse cx="{cx-4}" cy="{cy-4}" rx="4" ry="3" fill="#55555c" opacity="0.7"/>')
    add(f'<rect x="{cx-20}" y="{cy+46}" width="40" height="12" fill="#1a1a1a"/>')
    if spec.get("label", True):
        _text(add, cx, top - 12, spec.get("label_text", "speaker"), 17, "#3a3a3f")


# --------------------------------------------------------------------------
# HC-SR04 ultrasonic ranging module (4 pins)
# --------------------------------------------------------------------------
def holes_ultrasonic(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(4)]


def draw_ultrasonic(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(4)]
    cx = (xs[0] + xs[3]) / 2
    _, top, bottom, _ = _module_slot(L, row, 96)
    attach = top if _bottom_half(row) else bottom

    for x in xs:
        _lead(add, x, y, x, attach)
    bw = xs[3] - xs[0] + 110
    bx1 = cx - bw / 2
    # blue PCB like the real HC-SR04
    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="96" rx="8" '
        f'fill="#2b6cb0" stroke="#1a4a8a" stroke-width="2.5"/>')
    # black pin header along the bottom edge
    add(f'<rect x="{xs[0]-14}" y="{attach-26 if not _bottom_half(row) else attach+4}" '
        f'width="{xs[3]-xs[0]+28}" height="20" rx="3" fill="#1a1a1a"/>')
    # two silver mesh transducers
    for dx, tag in ((-44, "T"), (44, "R")):
        cxx, cyy = cx + dx, top + 46
        add(f'<circle cx="{cxx}" cy="{cyy}" r="34" fill="#f2f2f2" stroke="#9a9aa4" stroke-width="2"/>')
        for i in range(7):
            for j in range(7):
                mx, my = cxx - 21 + i*7, cyy - 21 + j*7
                if (mx-cxx)**2 + (my-cyy)**2 <= 21*21:
                    add(f'<circle cx="{mx}" cy="{my}" r="1.1" fill="#c9c9d1"/>')
        add(f'<circle cx="{cxx}" cy="{cyy}" r="15" fill="#d0d0d6" stroke="#9a9aa4" stroke-width="1.5"/>')
        add(f'<circle cx="{cxx}" cy="{cyy}" r="7" fill="#8a8a94"/>')
        _text(add, cxx, cyy + 50, tag, 14, "#cfe0f5")
    _text(add, cx, top + 14, spec.get("label_text", "HC-SR04"), 13, "#fff")
    _pin_labels(add, L, xs, row, spec.get("pins", ["VCC", "TRIG", "ECHO", "GND"]))


# --------------------------------------------------------------------------
# KY-023 joystick (5 pins)
# --------------------------------------------------------------------------
def holes_joystick(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(5)]


def draw_joystick(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(5)]
    cx = (xs[0] + xs[4]) / 2
    _, top, bottom, _ = _module_slot(L, row, 100)
    attach = top if _bottom_half(row) else bottom

    for x in xs:
        _lead(add, x, y, x, attach)
    bw = xs[4] - xs[0] + 80
    bx1 = cx - bw / 2
    # black PCB like the real KY-023
    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="100" rx="8" '
        f'fill="#1a1a1a" stroke="#3a3a3f" stroke-width="2.5"/>')
    for mx in (bx1 + 20, bx1 + bw - 20):
        add(f'<circle cx="{mx}" cy="{top + 16}" r="5" fill="none" stroke="#55555c" stroke-width="2"/>')
        add(f'<circle cx="{mx}" cy="{top + 84}" r="5" fill="none" stroke="#55555c" stroke-width="2"/>')
    # tactile push button beside the stick
    add(f'<rect x="{bx1+bw-64}" y="{top+58}" width="26" height="26" rx="3" '
        f'fill="#2b2b30" stroke="#55555c"/>')
    add(f'<circle cx="{bx1+bw-51}" cy="{top+71}" r="7" fill="#8a8a94"/>')
    # black pin header with gold pads along the bottom edge
    hy = attach - 26 if not _bottom_half(row) else attach + 4
    add(f'<rect x="{xs[0]-16}" y="{hy}" width="{xs[4]-xs[0]+32}" height="22" rx="3" fill="#111"/>')
    for x in xs:
        add(f'<rect x="{x-7}" y="{hy+4}" width="14" height="14" rx="2" fill="#d9a441"/>')
    # two-tier rubber stick cap
    cyy = top + 46
    add(f'<rect x="{cx-9}" y="{cyy-6}" width="18" height="36" rx="5" fill="#202024"/>')
    add(f'<circle cx="{cx}" cy="{cyy}" r="36" fill="#2b2b30" stroke="#15151a" stroke-width="2"/>')
    add(f'<ellipse cx="{cx-12}" cy="{cyy-12}" rx="12" ry="7" fill="#55555c" opacity="0.45"/>')
    add(f'<circle cx="{cx}" cy="{cyy-26}" r="20" fill="#202024" stroke="#15151a" stroke-width="2"/>')
    add(f'<ellipse cx="{cx-7}" cy="{cyy-32}" rx="7" ry="4.5" fill="#55555c" opacity="0.45"/>')
    _text(add, cx, top + 16, spec.get("label_text", "KY-023"), 13, "#e8e8ee")
    _pin_labels(add, L, xs, row, spec.get("pins", ["GND", "+5V", "VRx", "VRy", "SW"]))


# --------------------------------------------------------------------------
# LCD1602 with I2C backpack (4 pins)
# --------------------------------------------------------------------------
def holes_lcd(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(4)]


def draw_lcd(add, L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    xs = [L.col_x(col + i) for i in range(4)]
    cx = (xs[0] + xs[3]) / 2
    _, top, bottom, _ = _module_slot(L, row, 148)
    attach = top if _bottom_half(row) else bottom

    for x in xs:
        _lead(add, x, y, x, attach)
    bw, bh = 420, 148
    bx1, by1 = cx - bw / 2, top
    # green PCB, dark bezel and the backlit screen, like the kit's LCD1602
    add(f'<rect x="{bx1}" y="{by1}" width="{bw}" height="{bh}" rx="8" '
        f'fill="#2f6f4f" stroke="#1d4732" stroke-width="2.5"/>')
    for mx, my in ((bx1+16, by1+16), (bx1+bw-16, by1+16),
                   (bx1+16, by1+bh-16), (bx1+bw-16, by1+bh-16)):
        add(f'<circle cx="{mx}" cy="{my}" r="6" fill="#fdfaf3" stroke="#1d4732" stroke-width="1.5"/>')
    add(f'<rect x="{bx1+28}" y="{by1+14}" width="{bw-56}" height="{bh-30}" rx="4" '
        f'fill="#1a1a1a"/>')
    sx, sy, sw, sh = bx1 + 42, by1 + 24, bw - 84, bh - 50
    add(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="3" '
        f'fill="#1a4a8a" stroke="#0f2f57" stroke-width="1.5"/>')
    for r in range(2):
        for c in range(16):
            add(f'<rect x="{sx+10+c*(sw-20)/16}" y="{sy+13+r*40}" width="{(sw-20)/16-5}" '
                f'height="28" rx="2" fill="#cfe8ff" opacity="0.75"/>')
    _text(add, cx, by1 + bh - 5, spec.get("label_text", "LCD1602 (I2C)"), 15, "#e8f2ff")
    _pin_labels(add, L, xs, row, spec.get("pins", ["GND", "VCC", "SDA", "SCL"]))


# --------------------------------------------------------------------------
# L298N dual H-bridge motor driver board
# --------------------------------------------------------------------------
def holes_l298n(L, spec):
    col, row = spec["at"]
    return [(col + i, row) for i in range(len(spec.get("pins") or []))]


DEFAULT_L298N_PINS = ["ENA", "IN1", "IN2", "IN3", "IN4", "ENB"]


DEFAULT_L298N_PINS = ["ENA", "IN1", "IN2", "IN3", "IN4", "ENB"]
L298_W, L298_H = 700, 260


def _l298_geom(L, spec):
    """Shared geometry for drawing and terminals: (bx1, top, bw, bh, xs, cx)."""
    col, row = spec["at"]
    pins = spec.get("pins") or DEFAULT_L298N_PINS
    xs = [L.col_x(col + i) for i in range(len(pins))]
    cx = (xs[0] + xs[-1]) / 2
    _, top, _, _ = _module_slot(L, row, L298_H)
    bw = max(L298_W, xs[-1] - xs[0] + 200)
    return L.col_x(col), top, bw, L298_H, xs, cx, pins, (bw and (cx - bw / 2))


def draw_l298n(add, L, spec):
    """The classic red L298N module: heatsink, Multiwatt chip, eight diodes,
    two capacitors, regulator, output terminals and a 12V/GND/5V block."""
    col, row = spec["at"]
    _, top, bw, bh, xs, cx, pins, bx1 = _l298_geom(L, spec)
    y = L.row_y(row)
    attach = top if _bottom_half(row) else top + bh

    for x in xs:
        _lead(add, x, y, x, attach)

    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="{bh}" rx="6" '
        f'fill="#b03030" stroke="#7a2020" stroke-width="2.5"/>')
    for mx, my in ((bx1+22, top+22), (bx1+bw-22, top+22),
                   (bx1+22, top+bh-22), (bx1+bw-22, top+bh-22)):
        add(f'<circle cx="{mx}" cy="{my}" r="12" fill="#e8e8ee"/>')
        add(f'<circle cx="{mx}" cy="{my}" r="6.5" fill="#c9c9d1"/>')

    # heatsink, top centre
    hx1, hy1, hs_w, hs_h = cx - 96, top + 34, 192, 52
    add(f'<rect x="{hx1}" y="{hy1}" width="{hs_w}" height="{hs_h}" rx="4" '
        f'fill="#2b2b30" stroke="#15151a" stroke-width="2"/>')
    for i in range(5):
        add(f'<line x1="{hx1+20+i*38}" y1="{hy1+6}" x2="{hx1+20+i*38}" y2="{hy1+hs_h}" '
            f'stroke="#43434a" stroke-width="16"/>')
    for dx in (20, hs_w-20):
        add(f'<circle cx="{hx1+dx}" cy="{hy1+hs_h-9}" r="6.5" fill="#8a8a94"/>')

    # the chip: Multiwatt15, one staggered row of legs, two solder tabs
    ic_w, ic_h = 176, 30
    ix1, iy1 = cx - ic_w/2, top + 96
    for i in range(15):
        lx = ix1 + 7 + i * (ic_w - 14) / 14
        legh = 20 if i % 2 else 27
        add(f'<rect x="{lx-4}" y="{iy1+ic_h}" width="8" height="{legh}" rx="2" '
            f'fill="#dcdce4" stroke="#9a9aa4" stroke-width="1"/>')
    add(f'<rect x="{ix1}" y="{iy1}" width="{ic_w}" height="{ic_h}" rx="3" '
        f'fill="#1a1a1a" stroke="#000"/>')
    add(f'<rect x="{ix1}" y="{iy1}" width="{ic_w}" height="7" rx="2" fill="#3a3a3f"/>')
    for dx in (26, ic_w-26):
        add(f'<circle cx="{ix1+dx}" cy="{iy1-7}" r="7" fill="#9aa0a6" stroke="#6d6d76"/>')
    _text(add, cx, top + 190, "L298N", 19, "#fff")

    # eight rectifier diodes, four a side, inside the terminals
    for dx in (bx1 + 150, bx1 + bw - 150):
        for i in range(4):
            dy = top + 40 + i * 24
            add(f'<rect x="{dx-14}" y="{dy}" width="28" height="15" rx="2" '
                f'fill="#1a1a1a" stroke="#000"/>')
            add(f'<rect x="{dx-19}" y="{dy}" width="7" height="15" rx="2" fill="#c9c9d1"/>')
            add(f'<rect x="{dx+12}" y="{dy}" width="7" height="15" rx="2" fill="#c9c9d1"/>')

    # two electrolytic capacitors
    for cxx, cyy in ((cx - 150, top + 186), (cx + 132, top + 196)):
        add(f'<circle cx="{cxx}" cy="{cyy}" r="21" fill="#e8e8ee" stroke="#9a9aa4" stroke-width="2"/>')
        add(f'<path d="M{cxx+15} {cyy-15} A 21 21 0 0 1 {cxx+15} {cyy+15} Z" fill="#3a3a3f"/>')

    # TO-220 regulator with its tab, and the 5VEN jumper
    rx1 = cx + 168
    add(f'<rect x="{rx1}" y="{top+126}" width="46" height="36" rx="3" fill="#1a1a1a" stroke="#000"/>')
    add(f'<rect x="{rx1+8}" y="{top+118}" width="30" height="10" rx="2" fill="#c9c9d1"/>')
    add(f'<rect x="{cx-262}" y="{top+150}" width="28" height="24" rx="3" fill="#1a1a1a"/>')
    for k in range(2):
        add(f'<rect x="{cx-257+k*13}" y="{top+154}" width="11" height="16" rx="2" fill="#d9a441"/>')
    _text(add, cx - 214, top + 168, "5VEN", 13, "#fff")

    # output terminals: OUT1/OUT2 left, OUT3/OUT4 right
    for side, names in ((-1, ("OUT1", "OUT2")), (1, ("OUT3", "OUT4"))):
        tx = bx1 + 10 if side < 0 else bx1 + bw - 74
        exit_x = bx1 - 8 if side < 0 else bx1 + bw + 8
        for k, name in enumerate(names):
            ty = top + 62 + k * 74
            add(f'<line x1="{tx+32}" y1="{ty+22}" x2="{exit_x}" y2="{ty+22}" '
                f'stroke="#8a8a94" stroke-width="4"/>')
            add(f'<rect x="{tx}" y="{ty}" width="64" height="44" rx="4" '
                f'fill="#3b8ed0" stroke="#1a4a8a" stroke-width="2"/>')
            add(f'<circle cx="{tx+32}" cy="{ty+22}" r="13" fill="#c9c9d1" stroke="#8a8a94"/>')
            add(f'<line x1="{tx+20}" y1="{ty+22}" x2="{tx+44}" y2="{ty+22}" '
                f'stroke="#55555c" stroke-width="3"/>')
            _text(add, tx+32, ty+60, name, 13, "#fff")

    # 12V/GND/5V power block
    px1 = cx - 82
    add(f'<rect x="{px1}" y="{top+196}" width="164" height="46" rx="4" '
        f'fill="#3b8ed0" stroke="#1a4a8a" stroke-width="2"/>')
    for k, name in enumerate(("12V", "GND", "5V")):
        sx = px1 + 30 + k * 52
        add(f'<circle cx="{sx}" cy="{top+219}" r="13" fill="#c9c9d1" stroke="#8a8a94"/>')
        add(f'<line x1="{sx-9}" y1="{top+219}" x2="{sx+9}" y2="{top+219}" '
            f'stroke="#55555c" stroke-width="3"/>')
        _text(add, sx, top+236, name, 12, "#fff")

    # logic header along the bottom edge
    hy = attach - 22 if not _bottom_half(row) else attach + 2
    add(f'<rect x="{xs[0]-14}" y="{hy}" width="{xs[-1]-xs[0]+28}" height="20" rx="3" fill="#111"/>')
    for x in xs:
        add(f'<rect x="{x-7}" y="{hy+4}" width="14" height="12" rx="2" fill="#d9a441"/>')
    _text(add, cx, top + 26, spec.get("label_text", "L298N motor driver"), 15, "#fff")
    _pin_labels(add, L, xs, row, pins)


def terminals_l298n(L, spec):
    """OUT1-OUT4 at the screw terminals; 12V/GND/5V on the power block."""
    _, top, bw, _, _, cx, _, bx1 = _l298_geom(L, spec)
    t = {}
    for side, names in ((-1, ("OUT1", "OUT2")), (1, ("OUT3", "OUT4"))):
        exit_x = bx1 - 8 if side < 0 else bx1 + bw + 8
        for k, name in enumerate(names):
            t[name] = (exit_x, top + 62 + k * 74 + 22)
    px1 = cx - 82
    for k, name in enumerate(("12V", "GND", "5V")):
        t[name] = (px1 + 30 + k * 52, top + 219)
    return t


def component_bounds(L, spec):
    """Approximate body rectangle (x, y, w, h) for obstacle avoidance, or None."""
    kind = spec.get("type")
    col, row = spec.get("at") or spec.get("from") or (0, "a")
    y = L.row_y(row)
    if kind == "motor":
        cx = (L.col_x(col) + L.col_x(col + 1)) / 2
        _, top, bottom, _ = _module_slot(L, row, 116)
        cy = (top + bottom) / 2
        return (cx - 190, cy - 62, 380, 124)
    if kind == "servo":
        cx = (L.col_x(col) + L.col_x(col + 2)) / 2
        _, top, bottom, _ = _module_slot(L, row, 92)
        return (cx - 100, top - 50, 200, (bottom - top) + 60)
    if kind == "l298n":
        pins = spec.get("pins") or DEFAULT_L298N_PINS
        xs = [L.col_x(col + i) for i in range(len(pins))]
        cx = (xs[0] + xs[-1]) / 2
        _, top, _, _ = _module_slot(L, row, L298_H)
        bw = max(L298_W, xs[-1] - xs[0] + 200)
        return (cx - bw / 2, top, bw, L298_H)
    if kind in ("ic", "display_7seg", "bar_graph"):
        n = int(spec.get("pins", {"ic": 16, "display_7seg": 10, "bar_graph": 20}[kind])) // 2
        xs = [L.col_x(col + i) for i in range(n)]
        top = min(L.row_y("e"), L.row_y("f")) - 8
        bottom = max(L.row_y("e"), L.row_y("f")) + 8
        return (xs[0] - 36, top, xs[-1] - xs[0] + 72, bottom - top)
    if kind == "battery":
        cx = (L.col_x(col) + L.col_x(col + 1)) / 2
        _, top, bottom, _ = _module_slot(L, row, 88)
        return (cx - 64, top - 20, 128, (bottom - top) + 24)
    if kind == "speaker":
        cx = (L.col_x(col) + L.col_x(col + 1)) / 2
        _, top, bottom, _ = _module_slot(L, row, 84)
        cy = (top + bottom) / 2
        return (cx - 50, cy - 50, 100, 100)
    if kind == "module":
        pins = spec.get("pins") or []
        h = int(spec.get("height", 110))
        if not pins:
            return None
        x1 = L.col_x(col) - L.dcol * 0.4
        x2 = L.col_x(col + len(pins) - 1) + L.dcol * 0.4
        _, top, _, _ = _module_slot(L, row, h)
        return (x1, top, x2 - x1, h)
    if kind in ("joystick", "lcd", "ultrasonic"):
        n = {"joystick": 5, "lcd": 4, "ultrasonic": 4}[kind]
        pad = {"joystick": 80, "lcd": 0, "ultrasonic": 110}[kind]
        h = {"joystick": 100, "lcd": 148, "ultrasonic": 96}[kind]
        w = {"joystick": 420, "lcd": 420, "ultrasonic": 0}[kind]
        xs = [L.col_x(col + i) for i in range(n)]
        cx = (xs[0] + xs[-1]) / 2
        bw = w or (xs[-1] - xs[0] + pad)
        _, top, _, _ = _module_slot(L, row, h)
        return (cx - bw / 2, top, bw, h)
    return None


def component_terminals(L, spec):
    kind = spec.get("type")
    if kind in TERMINALS:
        return TERMINALS[kind](L, spec)
    return {}


TERMINALS = {
    "l298n": terminals_l298n,
}


REGISTRY = {
    "resistor": (draw_resistor, holes_resistor),
    "led": (draw_led, holes_led),
    "button": (draw_button, holes_button),
    "buzzer": (draw_buzzer, holes_buzzer),
    "diode": (draw_diode, holes_diode),
    "photoresistor": (draw_photoresistor, holes_photoresistor),
    "thermistor": (draw_thermistor, holes_thermistor),
    "potentiometer": (draw_potentiometer, holes_potentiometer),
    "transistor": (draw_transistor, holes_transistor),
    "rgb_led": (draw_rgb_led, holes_rgb_led),
    "ic": (draw_ic, holes_ic),
    "display_7seg": (draw_display_7seg, holes_display_7seg),
    "bar_graph": (draw_bar_graph, holes_bar_graph),
    "servo": (draw_servo, holes_servo),
    "motor": (draw_motor, holes_motor),
    "battery": (draw_battery, holes_battery),
    "speaker": (draw_speaker, holes_speaker),
    "ultrasonic": (draw_ultrasonic, holes_ultrasonic),
    "joystick": (draw_joystick, holes_joystick),
    "lcd": (draw_lcd, holes_lcd),
    "l298n": (draw_l298n, holes_l298n),
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
