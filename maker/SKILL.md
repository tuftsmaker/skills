---
name: maker
description: Generate beginner-friendly breadboard wiring diagrams (SVG + PNG) for Freenove ESP32-WROVER / FNK0046 circuits from a short YAML file. Use when asked for a wiring diagram, breadboard diagram, circuit diagram, Fritzing-style picture, jumper-wire instructions, or to show how to connect an LED, button, buzzer or sensor to an ESP32.
---

# Breadboard wiring diagrams

Renders a labelled, colour-coded breadboard diagram: the real Freenove
ESP32-WROVER board with its true header layout, a breadboard with highlighted
nets, components, and routed jumper wires. Output is SVG plus PNG.

The board drawing is written once in `boards/`. A new lesson is a ~20-line
YAML file in `circuits/`.

## Setup check

Run these first; they are cheap and the failure messages are otherwise confusing:

```bash
command -v python3 rsvg-convert
python3 -c "import yaml" || python3 -m pip install pyyaml
```

`rsvg-convert` comes from `brew install librsvg`. If it is missing the SVG is
still written — say so rather than treating it as a failure.

## Run it

```bash
python3 .opencode/skills/maker/render.py \
    .opencode/skills/maker/circuits/led.yml \
    -o out/led
```

Writes `out/led.svg` and `out/led.png`. Also useful:

```bash
render.py --list                       # boards and example circuits
render.py circuits/led.yml --no-png    # SVG only
render.py circuits/led.yml --scale 3   # bigger PNG
```

Always show the result to the user. Inline images often do not render in a
terminal, so on macOS open it: `open out/led.png`.

## Writing a circuit

Copy `circuits/led.yml` and edit it. Full schema:

```yaml
board: freenove-esp32-wrover      # required; see render.py --list

title: Add an external LED
subtitle: Four steps, two jumper wires

components:
  - type: resistor
    value: "220"                  # band colours are derived automatically
    from: [2, b]                  # column 2, row b
    span: 4                       # columns the body spans (default 4)
  - type: led
    color: red                    # red | green | blue | yellow | white
    at: [6, d]                    # anode in column 6; cathode is column 7

wires:
  - from: board.GPIO2
    to: bb.2.a
    color: red
    label: signal — GPIO 2        # optional legend text
  - from: bb.7.e
    to: board.R17
    color: black
    via: [[556, 629]]             # optional explicit waypoints

breadboard:
  labels:
    - {text: "one net", at: [2, a], offset: [0, -30]}

steps:                            # numbered list under the diagram
  - text: "Red jumper: board GPIO 2 → breadboard column 2, top row."
    at: [496, 732]                # optional badge position, in canvas units

notes:                            # plain string = grey; {text, warn} = amber
  - text: "Never wire an LED without the resistor — it will burn out."
    warn: true
```

### Endpoints

| Form           | Meaning                                              |
| -------------- | ---------------------------------------------------- |
| `board.GPIO2`  | pin by silkscreen name — only when the name is unique |
| `board.R17`    | right header, 17th pin from the top (1-based)         |
| `board.L1`     | left header, 1st pin from the top                     |
| `bb.2.a`       | breadboard column 2, row a                            |

Rows `a`–`e` are the top half, `f`–`j` the bottom half. Holes in one column
within the same half are already connected — that is the whole point of a
breadboard, and the renderer highlights those columns automatically.

**GND is not unique on this board** (it appears five times). `board.GND` raises
an error listing the candidates; use `board.R17` style instead. Same for any
repeated name.

## Component library

Defined in `bbd/components.py`; add new ones there.

| `type`     | Required keys         | Notes                                       |
| ---------- | --------------------- | ------------------------------------------- |
| `resistor` | `value`, `from`       | `span` defaults to 4 columns (0.4")         |
| `led`      | `at`                  | anode at `at`, cathode one column right     |
| `button`   | `at`                  | 4 legs, 0.3" wide, 2 rows tall              |
| `buzzer`   | `at`                  | 2 pins, one column apart                    |
| `module`   | `at`, `pins`, `label_text` | generic labelled sensor board          |

## Pitfalls

- Component legs and wire endpoints must land on real columns. If a wire looks
  wrong, check the column number against the rendered image before editing code.
- `span` on a resistor is the gap between legs, in columns. 4 columns is the
  standard 0.4" lead spacing.
- Wires are auto-routed through a gutter between the board and the breadboard,
  one lane per wire. If two wires overlap, give one an explicit `via:`.
- Re-render and actually look at the PNG after every edit. Layout is geometry;
  reasoning about coordinates in your head is unreliable.

## Adding a board

Copy `boards/freenove-esp32-wrover.yml`, replace `headers.left` / `headers.right`
with the pin names in physical top-to-bottom order, and set `highlight:` to the
pins that should glow. Geometry lives in `bbd/layout.py` and can be overridden
per circuit under a `layout:` key.
