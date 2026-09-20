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
    layout_over = spec.get("layout") or {}

    layout_over.setdefault(
        "height",
        1040 + 40 + 26 * len(steps) + 46 + 26 * len(notes) + 40,
    )
    L = Layout({**spec, "layout": layout_over})

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
        add(f'<text x="{L.W/2}" y="88" font-size="16" fill="#6b6b70" '
            f'text-anchor="middle">{esc(spec["subtitle"])}</text>')

    board_mod.draw_board(add, L, board)

    # which breadboard columns carry a net (used by wires or component legs)
    used = set()
    for spec_wire in spec.get("wires") or []:
        for col, _row in wire_mod.wire_holes(L, board, spec_wire):
            used.add(col)
    for spec_comp in spec.get("components") or []:
        for col, _row in comp_mod.component_holes(L, spec_comp):
            used.add(col)
    explicit = (spec.get("breadboard") or {}).get("highlight_columns")
    cols = sorted(set(explicit) if explicit is not None else used)

    bb_mod.draw_breadboard(add, L, {**spec, "breadboard": {
        **(spec.get("breadboard") or {}),
        "highlight_columns": cols,
    }})

    for i, spec_wire in enumerate(spec.get("wires") or []):
        wire_mod.draw_wire(add, L, board, spec_wire, lane=i)

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


def draw_notes(add, L, spec, steps, notes):
    y = L.notes_top

    used_colours = []
    for w in spec.get("wires") or []:
        c = str(w.get("color", "red")).lower()
        if c not in used_colours:
            used_colours.append(c)

    def wire_label(c):
        for w in spec.get("wires") or []:
            if str(w.get("color", "red")).lower() == c and w.get("label"):
                return w["label"]
        return f"{c} wire"

    x = 90
    for c in used_colours:
        hexc = wire_mod.COLOURS.get(c, c)
        text = wire_label(c)
        add(f'<rect x="{x}" y="{y-14}" width="22" height="14" rx="4" fill="{hexc}"/>')
        add(f'<text x="{x+30}" y="{y-2}" font-size="15" fill="#444">{esc(text)}</text>')
        x += 30 + 8 * len(text) + 60
    add(f'<circle cx="{x+8}" cy="{y-7}" r="8" fill="{PIN_GOLD}"/>')
    add(f'<text x="{x+26}" y="{y-2}" font-size="15" fill="#444">board pin</text>')
    x += 190
    add(f'<rect x="{x}" y="{y-15}" width="22" height="18" rx="8" fill="{NET}"/>')
    add(f'<text x="{x+32}" y="{y-2}" font-size="15" fill="#444">'
        f'one connected net (5 holes)</text>')
    x += 350
    if any(s.get("at") for s in steps):
        add(f'<circle cx="{x+9}" cy="{y-7}" r="9" fill="{BADGE}" stroke="#fff" stroke-width="3"/>')
        add(f'<text x="{x+28}" y="{y-2}" font-size="15" fill="#444">build order</text>')

    y += 40
    if steps:
        add(f'<text x="90" y="{y}" font-size="15" font-weight="700" fill="#26262b">Steps</text>')
        y += 26
        for i, s in enumerate(steps, start=1):
            text = s if isinstance(s, str) else s.get("text", "")
            add(f'<text x="90" y="{y}" font-size="15" fill="#444">{i}.  {esc(text)}</text>')
            y += 26
        y += 20

    for n in notes:
        warn = isinstance(n, dict)
        text = n.get("text", "") if warn else n
        fill = "#8a5a00" if warn else "#666"
        add(f'<text x="90" y="{y}" font-size="15" fill="{fill}">{esc(text)}</text>')
        y += 26


def main():
    ap = argparse.ArgumentParser(description="Render a breadboard wiring diagram.")
    ap.add_argument("circuit", nargs="?", help="circuit file (.yml or .json)")
    ap.add_argument("-o", "--out", help="output basename, e.g. out/led (writes .svg and .png)")
    ap.add_argument("--list", action="store_true", help="list boards and example circuits")
    ap.add_argument("--scale", type=float, default=2.0, help="PNG scale factor (default 2)")
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
    if not shutil.which("rsvg-convert"):
        print("note: rsvg-convert not found, so no PNG was written.")
        print("      install with:  brew install librsvg")
        return
    png_path = base + ".png"
    subprocess.run(["rsvg-convert", "-z", str(args.scale), svg_path, "-o", png_path],
                   check=True)
    print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
