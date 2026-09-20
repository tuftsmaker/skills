"""Draw the ESP32 board with its real header layout.

Two mounts are supported:
  - `bare` (default): the ESP32-WROVER board on its own, header pins labelled.
  - `extension`: the ESP32 seated on the Freenove GPIO extension board, where
    every pin breaks out to a horizontal row of holes (5 by default) that a
    jumper can plug into. Wires attach at the outer end of the row.
"""

PCB_TOP = "#26262a"
PCB_BOT = "#131316"
PIN_GOLD = "#d9a441"
GPIO_LABEL = "#f2f2f2"
OTHER_LABEL = "#b9b9c2"
HOLE = "#b9b3a6"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw_camera(add, L, cx, top):
    """Camera module on its FPC ribbon, mounted over the ESP32 module."""
    w, h = 124, 64
    add(f'<rect x="{cx-w/2}" y="{top}" width="{w}" height="{h}" rx="6" '
        f'fill="#1a1a1a" stroke="#3a3a3f" stroke-width="2"/>')
    cy = top + h / 2
    add(f'<circle cx="{cx}" cy="{cy}" r="20" fill="#3a3a3f" stroke="#15151a" stroke-width="2"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="11" fill="#111"/>')
    add(f'<circle cx="{cx-5}" cy="{cy-5}" r="3" fill="#55555c"/>')
    add(f'<rect x="{cx-14}" y="{top+h}" width="28" height="36" rx="3" '
        f'fill="#e07a1f" opacity="0.9"/>')
    add(f'<text x="{cx}" y="{top-8}" font-size="12" fill="#c9c9d1" '
        f'text-anchor="middle">camera</text>')


def draw_board(add, L, board):
    if L.mount == "extension":
        draw_extension_board(add, L, board)
        return

    left = board["headers"]["left"]
    right = board["headers"]["right"]
    hot = set(board.get("highlight") or [])

    add(f'<rect x="{L.board_x}" y="{L.board_y}" width="{L.board_w}" '
        f'height="{L.board_h}" rx="16" fill="url(#pcbg)" stroke="#000" '
        f'stroke-width="3" filter="url(#sh)"/>')

    # --- radio module ---
    mx = L.board_x + 110
    my = L.board_y + 76
    add(f'<rect x="{mx}" y="{my}" width="160" height="250" rx="8" '
        f'fill="#3a3a3f" stroke="#55555c"/>')
    add(f'<rect x="{mx+8}" y="{my+8}" width="144" height="112" rx="4" '
        f'fill="#2c2c31" stroke="#4a4a52"/>')
    for i in range(6):
        x = mx + 16 + i * 22
        add(f'<path d="M{x} {my+18} v92" stroke="#4f4f58" stroke-width="6"/>')
    add(f'<text x="{mx+80}" y="{my+140}" font-size="13" font-weight="700" '
        f'fill="#c9c9d1" text-anchor="middle">{_esc(board.get("module", "ESP32"))}</text>')
    add(f'<text x="{mx+80}" y="{my+160}" font-size="11" fill="#8d8d97" '
        f'text-anchor="middle">module</text>')

    # --- silkscreen ---
    silk = board.get("silkscreen") or []
    sy = L.board_y + L.board_h * 0.5
    if silk:
        add(f'<text x="{L.board_x + L.board_w/2}" y="{sy}" font-size="20" '
            f'font-weight="700" fill="#e8e8ee" text-anchor="middle">{_esc(silk[0])}</text>')
    if len(silk) > 1:
        add(f'<text x="{L.board_x + L.board_w/2}" y="{sy+24}" font-size="13" '
            f'fill="#9a9aa4" text-anchor="middle">{_esc(silk[1])}</text>')

    if board.get("camera"):
        draw_camera(add, L, L.board_x + L.board_w / 2, L.board_y + 14)

    # --- USB ---
    uy = L.board_y + L.board_h - 54
    add(f'<rect x="{L.board_x + 140}" y="{uy}" width="100" height="42" rx="6" '
        f'fill="#6d6d76" stroke="#8a8a94"/>')
    add(f'<text x="{L.board_x + 190}" y="{uy+26}" font-size="11" fill="#1b1b1d" '
        f'text-anchor="middle">{_esc(board.get("usb_label", "USB"))}</text>')

    # --- headers ---
    for pins, px, anchor, tx in (
        (left, L.left_pin_x, "start", L.left_pin_x + 20),
        (right, L.right_pin_x, "end", L.right_pin_x - 20),
    ):
        for i, name in enumerate(pins):
            y = L.pin_y(i)
            add(f'<rect x="{px-9}" y="{y-8}" width="18" height="16" rx="3" '
                f'fill="#111" stroke="#3a3a3f"/>')
            glow = ' filter="url(#glow)"' if name in hot else ''
            add(f'<circle cx="{px}" cy="{y}" r="5.5" fill="{PIN_GOLD}"{glow}/>')
            is_gpio = str(name).startswith("GPIO")
            colour = GPIO_LABEL if is_gpio else OTHER_LABEL
            label = str(name)[4:] if is_gpio else str(name)
            add(f'<text x="{tx}" y="{y+5}" font-size="14" fill="{colour}" '
                f'text-anchor="{anchor}">{_esc(label)}</text>')


def draw_extension_board(add, L, board):
    """The ESP32 seated on the Freenove GPIO extension board.

    Each pin gets a horizontal row of `strip_holes` holes; wires attach at the
    outer end of the row (nearest the board edge), so every pin is reachable
    from the same side of the board as the breadboard.
    """
    left = board["headers"]["left"]
    right = board["headers"]["right"]
    hot = set(board.get("highlight") or [])

    add(f'<rect x="{L.board_x}" y="{L.board_y}" width="{L.board_w}" '
        f'height="{L.board_h}" rx="16" fill="url(#pcbg)" stroke="#000" '
        f'stroke-width="3" filter="url(#sh)"/>')
    add(f'<text x="{L.board_x + L.board_w/2}" y="{L.board_y + 30}" font-size="15" '
        f'font-weight="700" fill="#e8e8ee" text-anchor="middle">'
        f'{_esc(board.get("board_title", "Freenove ESP32 GPIO Extension Board"))}</text>')

    # --- ESP32 module between the two pin columns ---
    mx1 = L.board_x + 150
    mx2 = L.board_x + L.board_w - 160
    my1 = L.board_y + 60
    add(f'<rect x="{mx1}" y="{my1}" width="{mx2-mx1}" height="290" rx="10" '
        f'fill="#3a3a3f" stroke="#55555c"/>')
    add(f'<rect x="{mx1+12}" y="{my1+12}" width="{mx2-mx1-24}" height="120" rx="5" '
        f'fill="#2c2c31" stroke="#4a4a52"/>')
    for i in range(6):
        x = mx1 + 24 + i * ((mx2 - mx1 - 48) / 5)
        add(f'<path d="M{x:.0f} {my1+22} v100" stroke="#4f4f58" stroke-width="6"/>')
    add(f'<text x="{(mx1+mx2)/2}" y="{my1+170}" font-size="14" font-weight="700" '
        f'fill="#c9c9d1" text-anchor="middle">{_esc(board.get("module", "ESP32-WROVER"))}</text>')
    add(f'<text x="{(mx1+mx2)/2}" y="{my1+192}" font-size="11" fill="#8d8d97" '
        f'text-anchor="middle">mounted on top</text>')
    add(f'<rect x="{(mx1+mx2)/2-40}" y="{my1+230}" width="80" height="30" rx="5" '
        f'fill="#6d6d76" stroke="#8a8a94"/>')
    add(f'<text x="{(mx1+mx2)/2}" y="{my1+250}" font-size="10" fill="#1b1b1d" '
        f'text-anchor="middle">{_esc(board.get("usb_label", "USB"))}</text>')

    if board.get("camera"):
        draw_camera(add, L, (mx1 + mx2) / 2, my1 + 14)

    # --- pin strips ---
    for pins, which, anchor in ((left, "left", "end"), (right, "right", "start")):
        x0 = L.pin_strip_x(which)
        label_x = x0 - 12 if which == "left" else x0 + 12
        for i, name in enumerate(pins):
            y = L.pin_y(i)
            xs = [L.strip_x(which, k) for k in range(L.strip_holes)]
            add(f'<line x1="{min(xs)}" y1="{y}" x2="{max(xs)}" y2="{y}" '
                f'stroke="#e2dccd" stroke-width="8"/>')
            for k, x in enumerate(xs):
                glow = ' filter="url(#glow)"' if name in hot and k == 0 else ''
                fill = PIN_GOLD if name in hot else HOLE
                add(f'<circle cx="{x}" cy="{y}" r="3.6" fill="{fill}"{glow}/>')
            is_gpio = str(name).startswith("GPIO")
            colour = GPIO_LABEL if is_gpio else OTHER_LABEL
            label = str(name)[4:] if is_gpio else str(name)
            add(f'<text x="{label_x}" y="{y+5}" font-size="13" fill="{colour}" '
                f'text-anchor="{anchor}">{_esc(label)}</text>')


def find_pin(L, board, name):
    """Return (x, y) where a wire attaches to a pin.

    Three ways to name a pin:
      GPIO2   - by silkscreen name; must be unambiguous
      R17     - right header, 17th pin from the top (1-based, as printed)
      L1      - left header, 1st pin from the top

    GND appears five times on this board, so it has to be addressed
    positionally. Asking for an ambiguous name raises with the options listed
    rather than silently picking one.
    """
    name = str(name).strip()

    if len(name) >= 2 and name[0] in "RrLl" and name[1:].isdigit():
        which = "right" if name[0] in "Rr" else "left"
        pins = board["headers"][which]
        idx = int(name[1:]) - 1
        if not 0 <= idx < len(pins):
            raise ValueError(f"{which} header has {len(pins)} pins, so {name} is out of range")
        return (L.pin_strip_x(which), L.pin_y(idx))

    matches = []
    for which in ("right", "left"):
        for i, pin in enumerate(board["headers"][which]):
            if pin == name:
                matches.append((L.pin_strip_x(which), L.pin_y(i), which, i + 1))

    if not matches:
        valid = ", ".join(board["headers"]["left"] + board["headers"]["right"])
        raise ValueError(f"board has no pin {name!r}. Available pins: {valid}")

    if len(matches) > 1:
        where = ", ".join(f"{w[0].upper()}{n}" for _x, _y, w, n in matches)
        raise ValueError(
            f"pin {name!r} appears {len(matches)} times ({where}). "
            f"Address it by header position instead, e.g. board.{matches[0][2][0].upper()}{matches[0][3]}"
        )

    return matches[0][0], matches[0][1]
