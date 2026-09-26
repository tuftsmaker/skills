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
        # sit clear of both this wire and the previous one
        add(f'<text x="{x - 26}" y="{ty}" font-size="16" fill="#444" '
            f'text-anchor="middle">{name}</text>')


def _pin_labels_vertical(add, xs, y, names, size=14, fill="#444"):
    """Pin names running up the wire, as modules like the HC-SR04 print them.

    A cabled part has no breadboard hole to label, and horizontal names run
    into the neighbouring wires, so these sit alongside each lead.
    """
    for x, name in zip(xs, names):
        add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'text-anchor="end" transform="rotate(-90 {x} {y})">{name}</text>')


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
    passive = str(spec.get("kind", "active")).lower() == "passive"

    add(f'<line x1="{x1}" y1="{y}" x2="{x1}" y2="{cy+r*0.4}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<line x1="{x2}" y1="{y}" x2="{x2}" y2="{cy+r*0.4}" stroke="#9a9a9a" stroke-width="3.5"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#2b2b30" stroke="#15151a" stroke-width="2.5"/>')
    if passive:
        # the passive part is open at the top: the pole piece and coil show
        add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.72}" fill="#1b1b1f"/>')
        add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.30}" fill="#4a4a52"/>')
        add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.12}" fill="#15151a"/>')
        for i in range(12):
            rad = math.radians(i * 30)
            add(f'<circle cx="{cx + math.cos(rad)*r*0.55:.1f}" '
                f'cy="{cy + math.sin(rad)*r*0.55:.1f}" r="2.2" fill="#8a6a3a" opacity="0.85"/>')
    else:
        # the active part is sealed, with its label ring on top
        add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.62}" fill="#dcdce4" opacity="0.85"/>')
        add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.18}" fill="#2b2b30"/>')
    add(f'<text x="{cx-r-8}" y="{cy-r+6}" font-size="12.5" fill="#8a8a8a" '
        f'text-anchor="end">+</text>')
    if spec.get("label", True):
        default = "passive buzzer" if passive else "active buzzer"
        add(f'<text x="{cx}" y="{cy-r-12}" font-size="15" font-weight="700" fill="#2b2b30" '
            f'text-anchor="middle">{spec.get("label_text", default)}</text>')


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
# Top view, proportions from the real SG90 (22.8 x 12.6 x 22.5 mm case,
# 32.5 mm over the ears) and from the true-scale Fritzing part (fritzing-parts
# / e-radionica, CC BY-SA 3.0). Drawn as the translucent blue case with its
# gear housing, mounting ears and screw holes.
#
# `horn:` picks the output horn: `single` (the blade arm the class mounts for
# steering) or `cross` (the four-arm horn from the kit). Default single.
SERVO_W = 168
SERVO_H = round(SERVO_W * 12.6 / 22.8)          # 93 px, the case proper
SERVO_EAR = 26                                  # mounting ear width, each side
SERVO_PIN_PITCH = 34                            # the 3-wire lead spacing


def holes_servo(L, spec):
    # connects by its own cable: no breadboard holes
    return []


def _servo_geom(L, spec):
    col, row = spec["at"]
    cx = L.col_x(col)
    y = L.row_y(row)
    _, top, bottom, _ = _module_slot(L, row, SERVO_H)
    xs = [cx + (i - 1) * SERVO_PIN_PITCH for i in range(3)]
    return xs, cx, y, top, bottom


def terminals_servo(L, spec):
    xs, cx, y, top, bottom = _servo_geom(L, spec)
    return {"GND": (xs[0], y), "5V": (xs[1], y), "SIG": (xs[2], y)}


def draw_servo(add, L, spec):
    col, row = spec["at"]
    xs, cx, y, top, bottom = _servo_geom(L, spec)
    attach = top if _bottom_half(row) else bottom
    cy = (top + bottom) / 2
    x1, x2 = cx - SERVO_W / 2, cx + SERVO_W / 2
    gx = cx + SERVO_W * 0.13                    # output-shaft position

    colours = ["#7a4a1e", WIRE_RED, "#e07a1f"]
    names = ["GND", "5V", "SIG"]
    for x, c in zip(xs, colours):
        _lead(add, x, y, x, attach, colour=c, w=5)

    # cable boot and the three leads where they enter the case
    add(f'<rect x="{xs[0]-10}" y="{attach-9}" width="{xs[2]-xs[0]+20}" height="18" rx="5" '
        f'fill="#202024"/>')

    # mounting ears with their screw holes (drawn under the case)
    for ex in (x1 - SERVO_EAR, x2):
        add(f'<rect x="{ex}" y="{cy - 16}" width="{SERVO_EAR}" height="32" rx="4" '
            f'fill="#24509a" stroke="#16376b" stroke-width="2"/>')
        add(f'<circle cx="{ex + SERVO_EAR/2}" cy="{cy}" r="7" fill="#0b1f3d"/>')
        add(f'<circle cx="{ex + SERVO_EAR/2}" cy="{cy}" r="3.5" fill="#3f6fb5"/>')

    # translucent blue case, with a lighter top face
    add(f'<rect x="{x1}" y="{top}" width="{SERVO_W}" height="{SERVO_H}" rx="10" '
        f'fill="#2d5ca8" stroke="#16376b" stroke-width="2.5"/>')
    add(f'<rect x="{x1+5}" y="{top+5}" width="{SERVO_W-10}" height="{SERVO_H-10}" rx="8" '
        f'fill="#3f74c4" opacity="0.55"/>')

    # gear housing around the output shaft, and the gears faintly through
    # the plastic
    add(f'<circle cx="{gx}" cy="{cy}" r="{SERVO_H*0.46:.1f}" fill="#2a559c" '
        f'stroke="#1d477f" stroke-width="1.5"/>')
    add(f'<circle cx="{gx}" cy="{cy}" r="{SERVO_H*0.34:.1f}" fill="#3568b5" '
        f'stroke="#1d477f" stroke-width="1.2"/>')
    add(f'<circle cx="{gx - SERVO_H*0.30:.1f}" cy="{cy + SERVO_H*0.12:.1f}" '
        f'r="{SERVO_H*0.11:.1f}" fill="#4f83cf" opacity="0.75"/>')
    add(f'<circle cx="{gx + SERVO_H*0.28:.1f}" cy="{cy - SERVO_H*0.10:.1f}" '
        f'r="{SERVO_H*0.09:.1f}" fill="#4f83cf" opacity="0.75"/>')

    # output horn: a single blade arm (default) or the four-arm cross
    horn = str(spec.get("horn", "single")).lower()
    add(f'<circle cx="{gx}" cy="{cy}" r="{SERVO_H*0.26:.1f}" fill="#dcdce4" '
        f'stroke="#a8a8b4" stroke-width="1.5"/>')
    if horn == "cross":
        arm_l, arm_w = SERVO_H * 0.72, SERVO_H * 0.18
        angles = (32, 122, 212, 302)
    else:
        arm_l, arm_w = SERVO_H * 1.25, SERVO_H * 0.22
        angles = (-32,)
    for ang in angles:
        rad = math.radians(ang)
        ux, uy = math.cos(rad), math.sin(rad)
        bx, by = gx + ux * SERVO_H * 0.18, cy + uy * SERVO_H * 0.18
        tx, ty = gx + ux * arm_l, cy + uy * arm_l
        add(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="#e8e8ec" '
            f'stroke-width="{arm_w:.1f}" stroke-linecap="round"/>')
        # row of lightening holes down the arm, as the real horn has
        for frac in ((0.45, 0.68, 0.9) if horn != "cross" else (1.0,)):
            hx, hy = gx + ux * arm_l * frac, cy + uy * arm_l * frac
            add(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{arm_w*0.17:.1f}" '
                f'fill="none" stroke="#b9b9c2" stroke-width="1.6"/>')
    add(f'<circle cx="{gx}" cy="{cy}" r="{SERVO_H*0.09:.1f}" fill="#b9b9c2"/>')
    add(f'<circle cx="{gx}" cy="{cy}" r="{SERVO_H*0.045:.1f}" fill="#8f8f9c"/>')
    _text(add, x1 + 40, cy + 5, "SG90", 13, "#dce8f8")
    _pin_labels_vertical(add, xs, y - 12 if _bottom_half(row) else y + 12, names)


# --------------------------------------------------------------------------
# TT gearbox motor + wheel (2 wires)
# --------------------------------------------------------------------------
MOTOR_PIN_PITCH = 44


def holes_motor(L, spec):
    # wires, not breadboard pins
    return []


def _motor_geom(L, spec):
    col, row = spec["at"]
    cx = L.col_x(col)
    y = L.row_y(row)
    asm_h = 116
    _, top, bottom, _ = _module_slot(L, row, asm_h)
    xs = [cx - MOTOR_PIN_PITCH / 2, cx + MOTOR_PIN_PITCH / 2]
    return xs, cx, y, top, bottom


def terminals_motor(L, spec):
    xs, cx, y, top, bottom = _motor_geom(L, spec)
    return {"M+": (xs[0], y), "M-": (xs[1], y)}


def draw_motor(add, L, spec):
    """Yellow-gearbox TT motor with its wheel, seen from above: silver can,
    yellow gearbox, output shaft, and the wheel edge-on crossing the shaft."""
    col, row = spec["at"]
    xs, cx, y, top, bottom = _motor_geom(L, spec)
    asm_h = bottom - top
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
# True proportions from the true-scale Fritzing part (fritzing-parts,
# CC BY-SA 3.0): board 45.1 x 20.0 mm => 2.25:1, not the 3.3:1 old drawing.
# Transducers are 14.1 mm (31% of the board width) centred at 20% and 80% of
# the board, the crystal is 15.0 x 7.2 mm at top centre, and the 4-pin header
# spans only 2.54 x 3 = 7.6 mm (17% of the width). The body is never stretched
# to reach the breadboard: the pins stay at their true pitch and the wires make
# up the difference.
ULTRA_W = 314
ULTRA_H = round(ULTRA_W * 20.0 / 45.1)          # 139 px, true 2.25:1
ULTRA_PITCH = 30                                # close to the true 2.54 mm header pitch
ULTRA_PAD = 46                                  # clearance for the header + labels


def _ultrasonic_geom(L, spec):
    col, row = spec["at"]
    y = L.row_y(row)
    cx = L.col_x(col)
    _, top, bottom, _ = _module_slot(L, row, ULTRA_H, pad=ULTRA_PAD)
    xs = [cx + (i - 1.5) * ULTRA_PITCH for i in range(4)]
    return xs, cx, y, top, bottom


def holes_ultrasonic(L, spec):
    # wired with jumpers from the module's own pins; the body is far wider than
    # the 4-hole group, so it is not plugged into the breadboard grid
    return []


def terminals_ultrasonic(L, spec):
    xs, cx, y, top, bottom = _ultrasonic_geom(L, spec)
    names = spec.get("pins") or ["VCC", "TRIG", "ECHO", "GND"]
    return {n: (xs[i], y) for i, n in enumerate(names)}


def draw_ultrasonic(add, L, spec):
    col, row = spec["at"]
    xs, cx, y, top, bottom = _ultrasonic_geom(L, spec)
    attach = top if _bottom_half(row) else bottom
    bx1, bw = cx - ULTRA_W / 2, ULTRA_W
    up = -1 if not _bottom_half(row) else 1

    for x in xs:
        _lead(add, x, y, x, attach)

    # blue PCB like the real HC-SR04
    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="{ULTRA_H}" rx="8" '
        f'fill="#2b6cb0" stroke="#1a4a8a" stroke-width="2.5"/>')
    # 15.0 x 7.2 mm quartz crystal at top centre
    cw, ch = bw * 15.0 / 45.1, ULTRA_H * 7.2 / 20.0
    add(f'<rect x="{cx-cw/2}" y="{top+ULTRA_H*0.05}" width="{cw}" height="{ch}" rx="{ch/2}" '
        f'fill="#c9c9d1" stroke="#9a9aa4" stroke-width="1.5"/>')
    # four corner mounting holes, 3.4 mm in from each corner
    hr = bw * 1.7 / 45.1
    for hx in (bx1 + bw*3.4/45.1, bx1 + bw - bw*3.4/45.1):
        for hy in (top + ULTRA_H*3.4/20.0, top + ULTRA_H - ULTRA_H*3.4/20.0):
            add(f'<circle cx="{hx}" cy="{hy}" r="{hr}" fill="#f2f2f2" stroke="#9a9aa4" stroke-width="1"/>')
            add(f'<circle cx="{hx}" cy="{hy}" r="{hr*0.45}" fill="#2b2b30"/>')
    # two mesh transducers: 14.1 mm (31% of the width) at 20% and 80%.
    # Ring order from the real part: pale bezel, black ring, dark silver mesh,
    # pale centre dish.
    tr = ULTRA_W * 0.5 * 14.1 / 45.1
    for frac in (0.20, 0.80):
        cxx, cyy = bx1 + bw*frac, top + ULTRA_H*0.5
        add(f'<circle cx="{cxx}" cy="{cyy}" r="{tr*1.16:.1f}" fill="#f2f2f2" stroke="#c9c9d1" stroke-width="1.5"/>')
        add(f'<circle cx="{cxx}" cy="{cyy}" r="{tr:.1f}" fill="#191919"/>')
        add(f'<circle cx="{cxx}" cy="{cyy}" r="{tr*0.74:.1f}" fill="#6d7773"/>')
        add(f'<circle cx="{cxx}" cy="{cyy}" r="{tr*0.50:.1f}" fill="#e6e6e6" stroke="#9a9aa4" stroke-width="1"/>')
        # fine mesh dot grid across the inner silver face only
        step = max(2.6, tr * 0.09)
        span = tr * 0.46
        n = int(span / step)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                mx, my = cxx + i*step, cyy + j*step
                if (mx-cxx)**2 + (my-cyy)**2 <= span*span:
                    add(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="0.9" fill="#9a9aa4" opacity="0.5"/>')
    # 4-pin header: a small block on the board edge
    hw = xs[-1] - xs[0] + 22
    hy = attach - 11 if up < 0 else attach + 2
    add(f'<rect x="{cx-hw/2}" y="{hy}" width="{hw}" height="16" rx="3" fill="#1a1a1a"/>')
    # transmitter / receiver markers, tucked between the transducers and the
    # bottom edge so they clear the corner mounting holes
    for frac, tag in ((0.20, "T"), (0.80, "R")):
        _text(add, bx1 + bw*frac, top + ULTRA_H*0.92, tag, 11, "#cfe0f5", weight="400")
    # title sits between the transducers, where the real silkscreen prints it
    _text(add, cx, top + ULTRA_H*0.52, spec.get("label_text", "HC-SR04"), 10, "#cfe0f5")
    # pin names vertical along each pin, as the real module prints them
    _pin_labels_vertical(add, xs, y - 12 if _bottom_half(row) else y + 12,
                         spec.get("pins", ["VCC", "TRIG", "ECHO", "GND"]))


# --------------------------------------------------------------------------
# KY-023 joystick (5 pins)
# --------------------------------------------------------------------------
JOY_W, JOY_H, JOY_PITCH = 260, 325, 44


def holes_joystick(L, spec):
    # wired with jumpers, never plugged into a breadboard
    return []


def _joystick_geom(L, spec):
    col, row = spec["at"]
    cx = L.col_x(col)
    y = L.row_y(row)
    xs = [cx + (i - 2) * JOY_PITCH for i in range(5)]
    top = y - 14 - JOY_H
    return xs, cx, y, top, y - 14


def terminals_joystick(L, spec):
    xs, cx, y, top, attach = _joystick_geom(L, spec)
    names = spec.get("pins") or ["GND", "+5V", "VRx", "VRy", "SW"]
    return {name: (x, y) for name, x in zip(names, xs)}


def draw_joystick(add, L, spec):
    """Black KY-023 at the reference part's proportions: the stick cap fills a
    near-square board with four corner holes and the five-pin header along the
    bottom edge. Its pins are jumpers, so the pitch is free."""
    xs, cx, y, top, attach = _joystick_geom(L, spec)
    bw, bh = JOY_W, JOY_H
    bx1 = cx - bw / 2

    for x in xs:
        _lead(add, x, y, x, attach)

    add(f'<rect x="{bx1}" y="{top}" width="{bw}" height="{bh}" rx="10" '
        f'fill="#1a1a1a" stroke="#3a3a3f" stroke-width="2.5"/>')
    for mx, my in ((bx1+22, top+22), (bx1+bw-22, top+22),
                   (bx1+22, top+bh-22), (bx1+bw-22, top+bh-22)):
        add(f'<circle cx="{mx}" cy="{my}" r="13" fill="#f2f2f2"/>')
    _text(add, bx1 + 46, top + bh - 34, spec.get("label_text", "KY-023"), 15, "#e8e8ee",
          anchor="start")

    ccy = top + bh * 0.42
    # the cap must fit inside the board, ring included, like the reference
    r = min(bh * 0.40, (bw / 2 - 12) / 1.14)
    add(f'<circle cx="{cx}" cy="{ccy}" r="{r*1.14:.0f}" fill="#111"/>')
    add(f'<circle cx="{cx}" cy="{ccy}" r="{r:.0f}" fill="#2b2b30" stroke="#15151a" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{ccy}" r="{r*0.8:.0f}" fill="#3a3a3f"/>')
    add(f'<ellipse cx="{cx-r*0.3:.0f}" cy="{ccy-r*0.36:.0f}" rx="{r*0.32:.0f}" ry="{r*0.19:.0f}" '
        f'fill="#6d6d76" opacity="0.5"/>')

    hy = attach - 22
    add(f'<rect x="{xs[0]-20}" y="{hy}" width="{xs[4]-xs[0]+40}" height="20" rx="3" fill="#111"/>')
    for x in xs:
        add(f'<rect x="{x-9}" y="{hy+3}" width="18" height="14" rx="2" '
            f'fill="#d9a441" stroke="#f2f2f2" stroke-width="1.2"/>')
    _pin_labels(add, L, xs, spec["at"][1], spec.get("pins", ["GND", "+5V", "VRx", "VRy", "SW"]))


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
    # never plugged into a breadboard: its pins are wireable terminals only
    return []


DEFAULT_L298N_PINS = ["ENA", "IN1", "IN2", "IN3", "IN4", "ENB"]
L298_SIZE = 350          # the module never plugs into the breadboard: square, like the real board
L298_PIN_PITCH = 45      # its logic pins are connected by jumpers, so the pitch is free


def _l298_pins(L, spec):
    """(xs, cx, pins, top, attach): pin positions are centred on the column."""
    col, row = spec["at"]
    pins = spec.get("pins") or DEFAULT_L298N_PINS
    cx = L.col_x(col)
    n = len(pins)
    xs = [cx + (i - (n - 1) / 2) * L298_PIN_PITCH for i in range(n)]
    y = L.row_y(row)
    top = y - 18 - L298_SIZE
    return xs, cx, pins, top, y - 18


def draw_l298n(add, L, spec):
    """The classic red L298N module at the reference part's square proportions:
    heatsink and Multiwatt chip up top, diodes down the sides, capacitors and
    regulator in the middle, output terminals on the edges, the 12V/GND/5V
    block and the logic header along the bottom."""
    xs, cx, pins, top, attach = _l298_pins(L, spec)
    bx1, bh = cx - L298_SIZE / 2, L298_SIZE
    y = L.row_y(spec["at"][1])

    for x in xs:
        _lead(add, x, y, x, attach)

    add(f'<rect x="{bx1}" y="{top}" width="{bh}" height="{bh}" rx="6" '
        f'fill="#b03030" stroke="#7a2020" stroke-width="2.5"/>')
    for mx, my in ((bx1+18, top+18), (bx1+bh-18, top+18),
                   (bx1+18, top+bh-18), (bx1+bh-18, top+bh-18)):
        add(f'<circle cx="{mx}" cy="{my}" r="10" fill="#e8e8ee"/>')
        add(f'<circle cx="{mx}" cy="{my}" r="5.5" fill="#c9c9d1"/>')

    hs_w, hs_h = 140, 44
    hx1, hy1 = cx - hs_w/2, top + 30
    add(f'<rect x="{hx1}" y="{hy1}" width="{hs_w}" height="{hs_h}" rx="3" '
        f'fill="#2b2b30" stroke="#15151a" stroke-width="2"/>')
    for i in range(5):
        add(f'<line x1="{hx1+14+i*28}" y1="{hy1+5}" x2="{hx1+14+i*28}" y2="{hy1+hs_h}" '
            f'stroke="#43434a" stroke-width="12"/>')
    for dx in (14, hs_w-14):
        add(f'<circle cx="{hx1+dx}" cy="{hy1+hs_h-7}" r="5" fill="#8a8a94"/>')

    ic_w, ic_h = 136, 24
    ix1, iy1 = cx - ic_w/2, top + 84
    for i in range(15):
        lx = ix1 + 5 + i * (ic_w - 10) / 14
        legh = 16 if i % 2 else 22
        add(f'<rect x="{lx-3}" y="{iy1+ic_h}" width="6" height="{legh}" rx="1.5" '
            f'fill="#dcdce4" stroke="#9a9aa4" stroke-width="0.8"/>')
    add(f'<rect x="{ix1}" y="{iy1}" width="{ic_w}" height="{ic_h}" rx="2" '
        f'fill="#1a1a1a" stroke="#000"/>')
    add(f'<rect x="{ix1}" y="{iy1}" width="{ic_w}" height="5" rx="2" fill="#3a3a3f"/>')
    for dx in (20, ic_w-20):
        add(f'<circle cx="{ix1+dx}" cy="{iy1-5}" r="5" fill="#9aa0a6" stroke="#6d6d76"/>')
    _text(add, cx, top + 152, "L298N", 16, "#fff")

    for dx in (bx1 + 68, bx1 + bh - 68):
        for i in range(4):
            dy = top + 34 + i * 21
            add(f'<rect x="{dx-11}" y="{dy}" width="22" height="11" rx="2" '
                f'fill="#1a1a1a" stroke="#000"/>')
            add(f'<rect x="{dx-15}" y="{dy}" width="5" height="11" rx="1.5" fill="#c9c9d1"/>')
            add(f'<rect x="{dx+10}" y="{dy}" width="5" height="11" rx="1.5" fill="#c9c9d1"/>')

    for cxx, cyy in ((cx - 62, top + 200), (cx + 52, top + 214)):
        add(f'<circle cx="{cxx}" cy="{cyy}" r="15" fill="#e8e8ee" stroke="#9a9aa4" stroke-width="1.5"/>')
        add(f'<path d="M{cxx+11} {cyy-11} A 15 15 0 0 1 {cxx+11} {cyy+11} Z" fill="#3a3a3f"/>')

    add(f'<rect x="{cx+92}" y="{top+168}" width="34" height="28" rx="2.5" fill="#1a1a1a" stroke="#000"/>')
    add(f'<rect x="{cx+98}" y="{top+162}" width="22" height="8" rx="2" fill="#c9c9d1"/>')
    add(f'<rect x="{cx-104}" y="{top+188}" width="22" height="18" rx="2.5" fill="#1a1a1a"/>')
    for k in range(2):
        add(f'<rect x="{cx-100+k*10}" y="{top+191}" width="8" height="12" rx="1.5" fill="#d9a441"/>')
    _text(add, cx - 68, top + 202, "5VEN", 11, "#fff")

    for side, names in ((-1, ("OUT1", "OUT2")), (1, ("OUT3", "OUT4"))):
        tx = bx1 + 6 if side < 0 else bx1 + bh - 58
        exit_x = bx1 - 8 if side < 0 else bx1 + bh + 8
        for k, name in enumerate(names):
            ty = top + 64 + k * 76
            add(f'<line x1="{tx+26}" y1="{ty+18}" x2="{exit_x}" y2="{ty+18}" '
                f'stroke="#8a8a94" stroke-width="3.5"/>')
            add(f'<rect x="{tx}" y="{ty}" width="52" height="36" rx="3" '
                f'fill="#3b8ed0" stroke="#1a4a8a" stroke-width="1.8"/>')
            add(f'<circle cx="{tx+26}" cy="{ty+18}" r="10.5" fill="#c9c9d1" stroke="#8a8a94"/>')
            add(f'<line x1="{tx+17}" y1="{ty+18}" x2="{tx+35}" y2="{ty+18}" '
                f'stroke="#55555c" stroke-width="2.5"/>')
            _text(add, tx+26, ty+50, name, 11, "#fff")

    px1 = cx - 66
    add(f'<rect x="{px1}" y="{top+232}" width="132" height="38" rx="3" '
        f'fill="#3b8ed0" stroke="#1a4a8a" stroke-width="1.8"/>')
    for k, name in enumerate(("12V", "GND", "5V")):
        sx = px1 + 24 + k * 42
        add(f'<circle cx="{sx}" cy="{top+251}" r="10.5" fill="#c9c9d1" stroke="#8a8a94"/>')
        add(f'<line x1="{sx-7}" y1="{top+251}" x2="{sx+7}" y2="{top+251}" '
            f'stroke="#55555c" stroke-width="2.5"/>')
        _text(add, sx, top+267, name, 11, "#fff")

    hy = attach - 20 if attach > top + bh / 2 else attach + 2
    add(f'<rect x="{xs[0]-26}" y="{hy}" width="{xs[-1]-xs[0]+52}" height="18" rx="3" fill="#111"/>')
    for x in xs:
        add(f'<rect x="{x-5}" y="{hy+4}" width="10" height="10" rx="1.5" fill="#d9a441"/>')
    _text(add, cx, top + 18, spec.get("label_text", "L298N motor driver"), 14, "#fff")
    _pin_labels(add, L, xs, spec["at"][1], pins)


def terminals_l298n(L, spec):
    """Everything wireable: the six logic pins, OUT1-OUT4, and 12V/GND/5V."""
    xs, cx, pins, top, attach = _l298_pins(L, spec)
    y = L.row_y(spec["at"][1])
    t = {name: (x, y) for name, x in zip(pins, xs)}
    for side, names in ((-1, ("OUT1", "OUT2")), (1, ("OUT3", "OUT4"))):
        exit_x = cx - L298_SIZE/2 - 8 if side < 0 else cx + L298_SIZE/2 + 8
        for k, name in enumerate(names):
            t[name] = (exit_x, top + 64 + k * 76 + 18)
    px1 = cx - 66
    for k, name in enumerate(("12V", "GND", "5V")):
        t[name] = (px1 + 24 + k * 42, top + 251)
    return t


def component_bounds(L, spec):
    """Approximate body rectangle (x, y, w, h) for obstacle avoidance, or None."""
    kind = spec.get("type")
    col, row = spec.get("at") or spec.get("from") or (0, "a")
    y = L.row_y(row)
    if kind == "motor":
        cx = L.col_x(col)
        _, top, bottom, _ = _module_slot(L, row, 116)
        cy = (top + bottom) / 2
        return (cx - 190, cy - 62, 380, 124)
    if kind == "servo":
        cx = L.col_x(col)
        _, top, bottom, _ = _module_slot(L, row, SERVO_H)
        return (cx - SERVO_W/2 - SERVO_EAR, top - 4, SERVO_W + 2*SERVO_EAR, (bottom - top) + 8)
    if kind == "l298n":
        cx = L.col_x(col)
        top = L.row_y(row) - 18 - L298_SIZE
        return (cx - L298_SIZE / 2, top, L298_SIZE, L298_SIZE)
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
    if kind == "joystick":
        xs, cx, _, top, _ = _joystick_geom(L, spec)
        return (cx - JOY_W / 2, top, JOY_W, JOY_H)
    if kind in ("lcd", "ultrasonic"):
        n = {"lcd": 4, "ultrasonic": 4}[kind]
        pad = {"lcd": 0, "ultrasonic": 0}[kind]
        h = {"lcd": 148, "ultrasonic": ULTRA_H}[kind]
        w = {"lcd": 420, "ultrasonic": ULTRA_W}[kind]
        xs = [L.col_x(col + i) for i in range(n)]
        cx = (xs[0] + xs[-1]) / 2
        if kind == "ultrasonic":
            cx = L.col_x(col)
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
    "servo": terminals_servo,
    "motor": terminals_motor,
    "joystick": terminals_joystick,
    "ultrasonic": terminals_ultrasonic,
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
