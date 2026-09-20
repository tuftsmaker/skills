"""Draw the ESP32 board with its real header layout."""

PCB_TOP = "#26262a"
PCB_BOT = "#131316"
PIN_GOLD = "#d9a441"
GPIO_LABEL = "#f2f2f2"
OTHER_LABEL = "#b9b9c2"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw_board(add, L, board):
    left = board["headers"]["left"]
    right = board["headers"]["right"]
    hot = set(board.get("highlight") or [])

    add(f'<rect x="{L.board_x}" y="{L.board_y}" width="{L.board_w}" '
        f'height="{L.board_h}" rx="16" fill="url(#pcbg)" stroke="#000" '
        f'stroke-width="3" filter="url(#sh)"/>')

    # --- radio module ---
    mx = L.board_x + 110
    add(f'<rect x="{mx}" y="196" width="160" height="250" rx="8" '
        f'fill="#3a3a3f" stroke="#55555c"/>')
    add(f'<rect x="{mx+8}" y="204" width="144" height="112" rx="4" '
        f'fill="#2c2c31" stroke="#4a4a52"/>')
    for i in range(6):
        x = mx + 16 + i * 22
        add(f'<path d="M{x} 214 v92" stroke="#4f4f58" stroke-width="6"/>')
    add(f'<text x="{mx+80}" y="336" font-size="13" font-weight="700" '
        f'fill="#c9c9d1" text-anchor="middle">{_esc(board.get("module", "ESP32"))}</text>')
    add(f'<text x="{mx+80}" y="356" font-size="11" fill="#8d8d97" '
        f'text-anchor="middle">module</text>')

    # --- silkscreen ---
    silk = board.get("silkscreen") or []
    if silk:
        add(f'<text x="{L.board_x + L.board_w/2}" y="560" font-size="20" '
            f'font-weight="700" fill="#e8e8ee" text-anchor="middle">{_esc(silk[0])}</text>')
    if len(silk) > 1:
        add(f'<text x="{L.board_x + L.board_w/2}" y="584" font-size="13" '
            f'fill="#9a9aa4" text-anchor="middle">{_esc(silk[1])}</text>')

    # --- USB ---
    add(f'<rect x="{L.board_x + 140}" y="946" width="100" height="42" rx="6" '
        f'fill="#6d6d76" stroke="#8a8a94"/>')
    add(f'<text x="{L.board_x + 190}" y="972" font-size="11" fill="#1b1b1d" '
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


def find_pin(L, board, name):
    """Return (x, y) for a pin.

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
        px = L.right_pin_x if which == "right" else L.left_pin_x
        return (px, L.pin_y(idx))

    matches = []
    for which, px in (("right", L.right_pin_x), ("left", L.left_pin_x)):
        for i, pin in enumerate(board["headers"][which]):
            if pin == name:
                matches.append((px, L.pin_y(i), which, i + 1))

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
