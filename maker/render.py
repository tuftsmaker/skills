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

    layout_over.setdefault("height", 1200)
    L = Layout({**spec, "layout": layout_over})
    # wires routed down the left side cross under the board in the corridor;
    # if those lanes would reach the notes band, push the notes down instead
    parts = {}
    for comp in spec.get("components") or []:
        if comp.get("id"):
            parts[comp["id"]] = comp_mod.component_terminals(L, comp)
    lanes = wire_mod.assign_lanes(L, board, spec.get("wires") or [], parts)
    left_wires = sum(1 for l in lanes if l.get("side") == "L")
    if left_wires:
        L.notes_top = max(L.notes_top, L.corridor0 + (left_wires - 1) * L.corridor_pitch + 26)
    if str(layout_over.get("notes_position", "bottom")).lower() == "right":
        L.notes_w = int(layout_over.get("notes_width", 640))
        L.notes_x = L.W + 30
        L.notes_position = "right"
        L.W += L.notes_w
        L.H = max(L.notes_top + 40,
                  notes_block_height(L, spec, steps, notes) + 30)
    else:
        legend = legend_rows(L, spec)
        L.H = L.notes_top + 44 + 33 * len(steps) + 18 + 33 * len(notes) + 44 + (legend - 1) * 36

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
        used.update(wire_mod.wire_holes(L, board, spec_wire, parts))
    for spec_comp in spec.get("components") or []:
        used.update(comp_mod.component_holes(L, spec_comp))
    explicit = (spec.get("breadboard") or {}).get("highlight_columns")
    if explicit is not None:
        holes = {(int(col), row) for col in explicit for row in ("a", "b", "c", "d", "e")}
    else:
        holes = used

    if not L.bb_hidden:
        bb_mod.draw_breadboard(add, L, {**spec, "breadboard": {
            **(spec.get("breadboard") or {}),
            "highlight_holes": sorted(holes),
        }})

    grid_paths = None
    if str(layout_over.get("router", "lanes")).lower() == "grid":
        from bbd import autoroute
        grid_paths = autoroute.route_all(L, board, spec, parts)
    for i, spec_wire in enumerate(spec.get("wires") or []):
        wire_mod.draw_wire(add, L, board, spec_wire, lanes[i], parts,
                           pts=grid_paths[i] if grid_paths else None)

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


def wrap_text(text, max_px, size=18):
    """Greedy word wrap, sized for the 18px note font."""
    per = max(8, int(max_px / (size * 0.53)))
    lines, line = [], ""
    for word in str(text).split():
        cand = (line + " " + word).strip()
        if len(cand) <= per:
            line = cand
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]


def notes_side(L):
    return str((L.notes_position or "bottom")).lower() == "right"


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
    if not L.bb_hidden:
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
    if notes_side(L):
        draw_notes_right(add, L, spec, steps, notes)
        return
    placements = legend_layout(L, spec, steps)
    rows = max(p[3] for p in placements) + 1
    for kind, payload, x, row in placements:
        y = L.notes_top + row * 36
        if kind == "wire":
            c, text = payload
            hexc = wire_mod.COLOURS.get(c, c)
            add(f'<rect class="legend" data-colour="{esc(c)}" x="{x}" y="{y-17}" '
                f'width="26" height="16" rx="4" fill="{hexc}"/>')
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


def notes_block_height(L, spec, steps, notes):
    """Height the side notes column will need, wrapped at its true width."""
    width = L.notes_w - 60
    h = 150 + 32 * len(legend_layout(L, spec, steps))
    if steps:
        h += 22 + 33
        for s in steps:
            text = s if isinstance(s, str) else s.get("text", "")
            h += 31 * len(wrap_text(text, width)) + 6
    if notes:
        h += 18
        for n in notes:
            text = n.get("text", "") if isinstance(n, dict) else n
            h += 31 * len(wrap_text(text, width)) + 8
    return h


def draw_notes_right(add, L, spec, steps, notes):
    """Steps and notes in a column beside the drawing (keeps the canvas wide)."""
    x0 = L.notes_x
    width = L.notes_w - 60
    y = 150
    placements = legend_layout(L, spec, steps)
    for kind, payload, _x, _row in placements:
        if kind == "wire":
            c, text = payload
            hexc = wire_mod.COLOURS.get(c, c)
            add(f'<rect class="legend" data-colour="{esc(c)}" x="{x0}" y="{y-17}" '
                f'width="26" height="16" rx="4" fill="{hexc}"/>')
            add(f'<text x="{x0+34}" y="{y-2}" font-size="18" fill="#444">{esc(text)}</text>')
            y += 32
        elif kind == "pin":
            add(f'<circle cx="{x0+13}" cy="{y-9}" r="9" fill="{PIN_GOLD}"/>')
            add(f'<text x="{x0+30}" y="{y-2}" font-size="18" fill="#444">board pin</text>')
            y += 32
        elif kind == "net":
            add(f'<rect x="{x0}" y="{y-20}" width="26" height="20" rx="9" fill="{NET}"/>')
            add(f'<text x="{x0+36}" y="{y-2}" font-size="18" fill="#444">'
                f'one connected net (5 holes)</text>')
            y += 32
        elif kind == "badge":
            add(f'<circle cx="{x0+10}" cy="{y-9}" r="10" fill="{BADGE}" stroke="#fff" stroke-width="3"/>')
            add(f'<text x="{x0+32}" y="{y-2}" font-size="18" fill="#444">build order</text>')
            y += 32
    if steps:
        y += 22
        add(f'<text x="{x0}" y="{y}" font-size="18" font-weight="700" fill="#26262b">Steps</text>')
        y += 33
        for i, s in enumerate(steps, start=1):
            text = s if isinstance(s, str) else s.get("text", "")
            for j, line in enumerate(wrap_text(text, width)):
                prefix = f"{i}.  " if j == 0 else "    "
                add(f'<text x="{x0}" y="{y}" font-size="18" fill="#444">{prefix}{esc(line)}</text>')
                y += 31
            y += 6
    if notes:
        y += 18
        for n in notes:
            warn = isinstance(n, dict)
            text = n.get("text", "") if warn else n
            fill = "#8a5a00" if warn else "#666"
            for line in wrap_text(text, width):
                add(f'<text x="{x0}" y="{y}" font-size="18" fill="{fill}">{esc(line)}</text>')
                y += 31
            y += 8


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body { margin: 0; height: 100%; background: #f6f4ef; }
  body { display: flex; flex-direction: column;
         font: 15px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
  header { display: flex; gap: 8px; align-items: center; padding: 10px 14px;
           background: #fff; border-bottom: 1px solid #e2ddd3; flex: 0 0 auto; flex-wrap: wrap; }
  header .name { font-weight: 600; margin-right: auto; }
  #status { min-width: 220px; color: #1f4a8a; font-weight: 600; }
  button { font: inherit; padding: 4px 12px; border: 1px solid #cfc9bb;
           border-radius: 8px; background: #fff; cursor: pointer; }
  button:hover { background: #f0ede6; }
  button.active { background: #1f4a8a; color: #fff; border-color: #1f4a8a; }
  #stage { flex: 1 1 auto; overflow: hidden; position: relative; cursor: grab;
           touch-action: none; }
  #stage.dragging { cursor: grabbing; }
  #panel { position: absolute; top: 0; left: 0; transform-origin: 0 0; will-change: transform; }
  #panel svg { display: block; background: #fdfaf3; box-shadow: 0 2px 16px rgba(0,0,0,.12); }
  .wire { cursor: pointer; }
  #panel.focus .wire { opacity: .12; }
  #panel.focus .wire.on { opacity: 1; stroke-width: 10; }
  #panel.flow .wire.on, #panel.flow:not(.focus) .wire {
    stroke-dasharray: 16 12; animation: dash 1.1s linear infinite; }
  @keyframes dash { to { stroke-dashoffset: -28; } }
  .legend { cursor: pointer; }
  @media print {
    header { display: none; }
    #stage { overflow: visible; }
    #panel { position: static; transform: none !important; }
    #panel svg { width: 100%; height: auto; box-shadow: none; }
    #panel .wire { opacity: 1 !important; stroke-width: 7 !important; animation: none !important; }
  }
</style>
</head>
<body>
<header>
  <span class="name">{title}</span>
  <span id="status">click a wire to trace it</span>
  <button id="flow" title="Animate the current path">Flow</button>
  <button id="clear" title="Clear the trace">Clear</button>
  <button id="zoomout">&minus;</button>
  <button id="zoomin">+</button>
  <button id="fit">Fit</button>
  <button id="one">1:1</button>
  <button id="print">Print</button>
</header>
<div id="stage"><div id="panel">{svg}</div></div>
<script>
(function () {
  var stage = document.getElementById('stage');
  var panel = document.getElementById('panel');
  var svg = panel.querySelector('svg');
  var status = document.getElementById('status');
  var HINT = 'click a wire to trace it';
  var scale = 1, tx = 0, ty = 0, moved = false, down = null;

  function size() {
    var vb = svg.viewBox && svg.viewBox.baseVal;
    return { w: (vb && vb.width) || svg.getBoundingClientRect().width,
             h: (vb && vb.height) || svg.getBoundingClientRect().height };
  }
  function apply() { panel.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')'; }
  function fit() {
    var s = size(), r = stage.getBoundingClientRect();
    scale = Math.min(r.width / s.w, r.height / s.h) * 0.98;
    tx = (r.width - s.w * scale) / 2;
    ty = (r.height - s.h * scale) / 2;
    apply();
  }
  function actual() { var s = size(), r = stage.getBoundingClientRect(); scale = 1; tx = (r.width - s.w) / 2; ty = 10; apply(); }
  function zoomAt(cx, cy, factor) {
    var next = Math.min(24, Math.max(0.05, scale * factor)), k = next / scale;
    tx = cx - (cx - tx) * k; ty = cy - (cy - ty) * k; scale = next; apply();
  }
  stage.addEventListener('wheel', function (e) {
    e.preventDefault();
    var r = stage.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, { passive: false });
  stage.addEventListener('dblclick', fit);
  document.getElementById('zoomin').onclick = function () { var r = stage.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 1.25); };
  document.getElementById('zoomout').onclick = function () { var r = stage.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 0.8); };
  document.getElementById('fit').onclick = fit;
  document.getElementById('one').onclick = actual;
  document.getElementById('print').onclick = function () { window.print(); };
  window.addEventListener('beforeprint', function () { panel.style.transform = 'none'; });
  window.addEventListener('afterprint', fit);
  window.addEventListener('resize', fit);

  // --- wire tracing ---------------------------------------------------------
  function clearFocus() {
    panel.classList.remove('focus');
    var on = panel.querySelectorAll('.wire.on');
    for (var i = 0; i < on.length; i++) on[i].classList.remove('on');
  }
  function focusWire(el) {
    clearFocus();
    if (!el) { status.textContent = HINT; return; }
    el.classList.add('on');
    panel.classList.add('focus');
    status.textContent = el.getAttribute('data-label') || 'wire';
  }
  function focusColour(name) {
    clearFocus();
    var list = panel.querySelectorAll('.wire[data-colour="' + name + '"]');
    if (!list.length) { status.textContent = HINT; return; }
    panel.classList.add('focus');
    for (var i = 0; i < list.length; i++) list[i].classList.add('on');
    var label = list[0].getAttribute('data-label') || name;
    status.textContent = label + (list.length > 1 ? '  (+' + (list.length - 1) + ' more)' : '');
  }
  function pick(clientX, clientY) {
    var el = document.elementFromPoint(clientX, clientY);
    if (!el || !el.closest) return null;
    return el.closest('.wire') || el.closest('.legend') || null;
  }
  stage.addEventListener('pointermove', function (e) {
    if (down || panel.classList.contains('focus')) return;
    var el = pick(e.clientX, e.clientY);
    status.textContent = (el && el.classList.contains('wire'))
      ? (el.getAttribute('data-label') || 'wire') : HINT;
  });
  document.getElementById('clear').onclick = function () {
    focusWire(null);
    panel.classList.remove('flow');
    document.getElementById('flow').classList.remove('active');
  };
  document.getElementById('flow').onclick = function () {
    panel.classList.toggle('flow');
    this.classList.toggle('active');
  };

  stage.addEventListener('pointerdown', function (e) {
    down = { x: e.clientX - tx, y: e.clientY - ty, sx: e.clientX, sy: e.clientY };
    moved = false;
    stage.classList.add('dragging');
    try { if (stage.setPointerCapture) stage.setPointerCapture(e.pointerId); } catch (err) {}
  });
  stage.addEventListener('pointermove', function (e) {
    if (!down) return;
    if (Math.abs(e.clientX - down.sx) + Math.abs(e.clientY - down.sy) > 4) moved = true;
    tx = e.clientX - down.x; ty = e.clientY - down.y; apply();
  });
  stage.addEventListener('pointerup', function (e) {
    var wasDown = down;
    down = null;
    stage.classList.remove('dragging');
    if (!wasDown || moved) return;               // a drag, not a click
    var el = pick(e.clientX, e.clientY);
    if (!el) { focusWire(null); return; }
    if (el.classList.contains('legend')) { focusColour(el.getAttribute('data-colour')); return; }
    focusWire(el);
  });
  fit();
})();
</script>
</body>
</html>
"""


def write_html(svg_path, html_path, title):
    """A zoomable, pannable wrapper around the SVG for a browser."""
    import re as _re
    svg = open(svg_path).read()
    svg = _re.sub(r'<\?xml[^>]*\?>', '', svg)
    html = HTML_TEMPLATE.replace('{title}', title or 'Wiring diagram').replace('{svg}', svg)
    with open(html_path, 'w') as f:
        f.write(html)


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
    ap.add_argument("--no-html", action="store_true", help="skip the zoomable HTML wrapper")
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

    if not args.no_html:
        html_path = base + ".html"
        write_html(svg_path, html_path, spec.get("title"))
        print(f"wrote {html_path}")

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
