"""Breadboard wiring diagram generator (opencode skill).

Loads a board definition and a circuit description, draws an SVG, and (when
rsvg-convert is available) rasterises it to PNG.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bbd import board as board_mod          # noqa: E402
from bbd import breadboard as bb_mod        # noqa: E402
from bbd import components as comp_mod      # noqa: E402
from bbd import wires as wire_mod           # noqa: E402
from bbd.layout import Layout               # noqa: E402

FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"
PIN_GOLD = "#d9a441"
NET = "#ffe9a8"
BADGE = "#1f6feb"

DEFS = '''<defs>
  <filter id="sh" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000" flood-opacity="0.16"/>
  </filter>
  <filter id="glow" x="-90%" y="-90%" width="280%" height="280%">
    <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#ffcc00" flood-opacity="0.95"/>
  </filter>
  <linearGradient id="pcbg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#26262a"/><stop offset="1" stop-color="#131316"/>
  </linearGradient>
</defs>'''


def load(path):
    if not os.path.exists(path):
        raise SystemExit(f"no such file: {path}")
    with open(path) as f:
        text = f.read()
    if path.endswith(".json"):
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "PyYAML is not installed, so .yml files cannot be read.\n"
            "  Fix A:  python3 -m pip install pyyaml\n"
            "  Fix B:  convert the circuit to JSON and pass the .json file\n"
            "          (JSON needs no extra packages)"
        )
    return yaml.safe_load(text)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(spec, board):
    steps = spec.get("steps") or []
    notes = spec.get("notes") or []
    # board-level layout defaults, then circuit overrides
    bl = board.get("layout") or {}
    sl = spec.get("layout") or {}
    layout_over = {**bl, **sl}
    for key in ("board", "breadboard"):
        merged = {**(bl.get(key) or {}), **(sl.get(key) or {})}
        if merged:
            layout_over[key] = merged

    layout_over.setdefault(
        "height",
        1040 + 40 + 33 * len(steps) + 52 + 33 * len(notes) + 44,
    )
    L = Layout({**spec, "layout": layout_over})
    L.H += (legend_rows(L, spec) - 1) * 36

    out = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{L.W}" height="{L.H}" '
        f'viewBox="0 0 {L.W} {L.H}" font-family="{FONT}">')
    add(DEFS)
    add(f'<rect width="{L.W}" height="{L.H}" fill="#fdfaf3"/>')

    if spec.get("title"):
        add(f'<text x="{L.W/2}" y="58" font-size="30" font-weight="700" fill="#26262b" '
            f'text-anchor="middle">{esc(spec["title"])}</text>')
    if spec.get("subtitle"):
        add(f'<text x="{L.W/2}" y="92" font-size="19" fill="#6b6b70" '
            f'text-anchor="middle">{esc(spec["subtitle"])}</text>')

    board_mod.draw_board(add, L, {**board, "camera": spec.get("camera", board.get("camera"))})

    # Breadboard holes that carry a net (touched by a wire or a component leg).
    # The top half (a-e) and the bottom half (f-j) of a column are separate nets,
    # so the renderer highlights the tie-point group each hole belongs to.
    used = set()
    for spec_wire in spec.get("wires") or []:
        used.update(wire_mod.wire_holes(L, board, spec_wire))
    for spec_comp in spec.get("components") or []:
        used.update(comp_mod.component_holes(L, spec_comp))
    explicit = (spec.get("breadboard") or {}).get("highlight_columns")
    if explicit is not None:
        holes = {(int(col), row) for col in explicit for row in ("a", "b", "c", "d", "e")}
    else:
        holes = used

    bb_mod.draw_breadboard(add, L, {**spec, "breadboard": {
        **(spec.get("breadboard") or {}),
        "highlight_holes": sorted(holes),
    }})

    lanes = wire_mod.assign_lanes(L, board, spec.get("wires") or [])
    for i, spec_wire in enumerate(spec.get("wires") or []):
        wire_mod.draw_wire(add, L, board, spec_wire, lanes[i])

    for spec_comp in spec.get("components") or []:
        comp_mod.draw_component(add, L, spec_comp)

    for i, step in enumerate(steps, start=1):
        if step.get("at"):
            x, y = step["at"]
            add(f'<circle cx="{x}" cy="{y}" r="16" fill="{BADGE}" stroke="#fff" '
                f'stroke-width="3"/>')
            add(f'<text x="{x}" y="{y+6}" font-size="18" font-weight="700" fill="#fff" '
                f'text-anchor="middle">{i}</text>')

    draw_notes(add, L, spec, steps, notes)
    add("</svg>")
    return "\n".join(out)


def legend_layout(L, spec, steps):
    """Place legend items, wrapping at the canvas edge.

    Returns [(kind, payload, x, row)] with kind in wire | pin | net | badge.
    """
    items = []
    seen = []
    for w in spec.get("wires") or []:
        c = str(w.get("color", "red")).lower()
        if c in seen:
            continue
        seen.append(c)
        text = next((w2.get("label") for w2 in spec.get("wires") or []
                     if str(w2.get("color", "red")).lower() == c and w2.get("label")),
                    f"{c} wire")
        items.append(("wire", (c, text), 34 + 9.6 * len(text) + 64))
    items.append(("pin", None, 215))
    items.append(("net", None, 400))
    if any(s.get("at") for s in steps):
        items.append(("badge", None, 200))

    placements = []
    row, x = 0, 90
    for kind, payload, width in items:
        if x + width > L.W - 60:
            row += 1
            x = 90
        placements.append((kind, payload, x, row))
        x += width
    return placements


def legend_rows(L, spec):
    """How many rows the legend needs at this canvas width."""
    return max(p[3] for p in legend_layout(L, spec, spec.get("steps") or [])) + 1


def draw_notes(add, L, spec, steps, notes):
    placements = legend_layout(L, spec, steps)
    rows = max(p[3] for p in placements) + 1
    for kind, payload, x, row in placements:
        y = L.notes_top + row * 36
        if kind == "wire":
            c, text = payload
            hexc = wire_mod.COLOURS.get(c, c)
            add(f'<rect x="{x}" y="{y-17}" width="26" height="16" rx="4" fill="{hexc}"/>')
            add(f'<text x="{x+34}" y="{y-2}" font-size="18" fill="#444">{esc(text)}</text>')
        elif kind == "pin":
            add(f'<circle cx="{x+13}" cy="{y-9}" r="9" fill="{PIN_GOLD}"/>')
            add(f'<text x="{x+30}" y="{y-2}" font-size="18" fill="#444">board pin</text>')
        elif kind == "net":
            add(f'<rect x="{x}" y="{y-20}" width="26" height="20" rx="9" fill="{NET}"/>')
            add(f'<text x="{x+36}" y="{y-2}" font-size="18" fill="#444">'
                f'one connected net (5 holes)</text>')
        else:
            add(f'<circle cx="{x+10}" cy="{y-9}" r="10" fill="{BADGE}" stroke="#fff" stroke-width="3"/>')
            add(f'<text x="{x+32}" y="{y-2}" font-size="18" fill="#444">build order</text>')

    y = L.notes_top + (rows - 1) * 36 + 44
    if steps:
        add(f'<text x="90" y="{y}" font-size="18" font-weight="700" fill="#26262b">Steps</text>')
        y += 33
        for i, s in enumerate(steps, start=1):
            text = s if isinstance(s, str) else s.get("text", "")
            add(f'<text x="90" y="{y}" font-size="18" fill="#444">{i}.  {esc(text)}</text>')
            y += 33
        y += 18

    for n in notes:
        warn = isinstance(n, dict)
        text = n.get("text", "") if warn else n
        fill = "#8a5a00" if warn else "#666"
        add(f'<text x="90" y="{y}" font-size="18" fill="{fill}">{esc(text)}</text>')
        y += 33


def svg_size(path):
    """Read width/height attributes from the SVG header."""
    import re
    with open(path) as f:
        head = f.read(400)
    w = re.search(r'width="(\d+)"', head)
    h = re.search(r'height="(\d+)"', head)
    return (int(w.group(1)) if w else 1800, int(h.group(1)) if h else 1260)


def find_chrome():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome", "chromium", "chromium-browser",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
    ]
    for c in candidates:
        if os.path.sep in c and os.path.exists(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def rasterise(svg_path, png_path, scale):
    """SVG -> PNG with the first rasteriser available. Returns a note or None."""
    w, h = svg_size(svg_path)
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-z", str(scale), svg_path, "-o", png_path],
                       check=True)
        return None
    if sys.platform == "darwin" and shutil.which("qlmanage"):
        out_dir = os.path.dirname(os.path.abspath(png_path))
        subprocess.run(["qlmanage", "-t", "-s", str(int(max(w, h) * scale)),
                        "-o", out_dir, svg_path], check=True, capture_output=True)
        produced = os.path.join(out_dir, os.path.basename(svg_path) + ".png")
        if os.path.exists(produced):
            os.replace(produced, png_path)
            return None
    chrome = find_chrome()
    if chrome:
        subprocess.run([chrome, "--headless=new", "--disable-gpu",
                        f"--screenshot={png_path}",
                        f"--window-size={int(w*scale)},{int(h*scale)}",
                        "--hide-scrollbars", f"file://{os.path.abspath(svg_path)}"],
                       check=True, capture_output=True)
        return None
    return ("no rasteriser found, so no PNG was written. Install librsvg "
            "(brew install librsvg), or open the SVG directly.")


def main():
    ap = argparse.ArgumentParser(description="Render a breadboard wiring diagram.")
    ap.add_argument("circuit", nargs="?", help="circuit file (.yml or .json)")
    ap.add_argument("-o", "--out", help="output basename, e.g. out/led (writes .svg and .png)")
    ap.add_argument("--list", action="store_true", help="list boards and example circuits")
    ap.add_argument("--scale", type=float, default=1.1,
                    help="PNG scale factor (default 1.1 — stays under 2000 px for inline previews)")
    ap.add_argument("--no-png", action="store_true", help="only write the SVG")
    args = ap.parse_args()

    if args.list or not args.circuit:
        print("boards:")
        for f in sorted(os.listdir(os.path.join(HERE, "boards"))):
            print("  " + os.path.splitext(f)[0])
        print("example circuits:")
        for f in sorted(os.listdir(os.path.join(HERE, "circuits"))):
            print("  " + os.path.join("circuits", f))
        return

    spec = load(args.circuit)
    board_name = spec.get("board")
    if not board_name:
        raise SystemExit("circuit file must set 'board:' (see --list)")
    board = load(os.path.join(HERE, "boards", f"{board_name}.yml"))

    svg = build_svg(spec, board)

    base = args.out or os.path.splitext(args.circuit)[0]
    os.makedirs(os.path.dirname(os.path.abspath(base)), exist_ok=True)
    svg_path = base + ".svg"
    with open(svg_path, "w") as f:
        f.write(svg)
    print(f"wrote {svg_path}")

    if args.no_png:
        return
    png_path = base + ".png"
    note = rasterise(svg_path, png_path, args.scale)
    if note:
        print("note: " + note)
    elif os.path.exists(png_path):
        print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
