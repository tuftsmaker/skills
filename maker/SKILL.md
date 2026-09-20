---
name: maker
description: Generate beginner-friendly breadboard wiring diagrams (SVG + PNG) for the Freenove ESP32-WROVER / FNK0046 Super Starter Kit. Covers every part in the kit — LEDs, RGB LED, bar graph, 7-segment display, resistors, diodes, buttons, buzzers, speaker, transistors, potentiometer, photoresistor, thermistor, joystick, servo, TT motor, 9V battery, ultrasonic sensor, LCD1602, L298N driver, 74HC595 and the onboard camera. Use when asked for a wiring diagram, breadboard diagram, circuit diagram, Fritzing-style picture, jumper-wire instructions, or how to connect a part to an ESP32.
---

# Breadboard wiring diagrams

Renders a labelled, colour-coded breadboard diagram: the real Freenove
ESP32-WROVER board (or the same board on its GPIO extension board), a
breadboard with highlighted nets, components, and routed jumper wires.
Output is SVG plus PNG.

The board drawing is written once in `boards/`. A new lesson is a ~20-line
YAML file in `circuits/`. Everything the FNK0046 kit contains is supported —
see the component table below.

## Setup check

Run these first; they are cheap and the failure messages are otherwise confusing:

```bash
command -v python3
python3 -c "import yaml" || echo "no pyyaml — JSON circuits still work"
command -v rsvg-convert qlmanage
```

- PyYAML is optional. `.yml` circuits need it (`python3 -m pip install --user pyyaml`); `.json` circuits work with no installs at all.
- `rsvg-convert` (librsvg) is the preferred rasteriser. If it is missing the renderer falls back to `qlmanage` (macOS) or headless Chrome, and otherwise still writes the SVG.

## Run it

The skill lives wherever opencode installed it (often
`~/.cache/opencode/skills/maker`). Resolve that path from this file's
location — do not assume the current directory:

```bash
SKILL="<directory containing this SKILL.md>"
python3 "$SKILL/render.py" "$SKILL/circuits/led.yml" -o out/led
```

Writes `out/led.svg` and `out/led.png` **into the current project directory**
(never into the skill directory). Also useful:

```bash
render.py --list                       # boards and example circuits
render.py circuits/led.yml --no-png    # SVG only
render.py circuits/led.yml --scale 2   # bigger PNG
```

## Show the result inline

The desktop app renders a PNG inline when the reply contains plain markdown
image syntax with a workspace-relative path. After every render, finish your
reply with a line exactly like this (not inside a code fence):

```
![Add an external LED](out/led.png)
```

Also mention the file path in text. Never present a diagram by reading the PNG
back as a tool result, and never open an external viewer for the student.

Keep the PNG at or under 2000 px wide — the default scale already does.

Every render also writes `<name>.html`: the SVG inlined in a small page with
zoom and pan (scroll to zoom, drag to pan, Fit / 1:1 / Print buttons). Because
it is vector, zooming stays crisp at any level and printing is sharp.

**Showing the zoomable view inside the desktop app.** The app's browser pane
(enable it once in Settings → General → experimental browser) only accepts
HTTP(S), so serve the output folder on loopback and open that URL:

```bash
(cd out && nohup python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 &)
```

then open `http://127.0.0.1:8765/<name>.html` in a browser tab. The pane's
`localhost` is the student's own machine, so this works locally for them too.
Stop the server with `pkill -f "http.server 8765"` when done. A plain markdown
link to a local file does not open in current desktop builds — mention the
file path in text as well.

Verified desktop behaviour, so do not fight it:

- The app normalises local images before display, so rendering above ~2000 px
  gains nothing inline. The 1.1 default is the right size.
- The inline image viewer has no zoom or pan, and tall diagrams are clipped at
  the bottom (the box is roughly 1.9:1). Either keep the canvas wider than
  that — `layout: {notes_position: right}` moves the steps and notes into a
  side column, see `circuits/robot-drive.yml` — or accept that the tail of a
  tall diagram shows only in the fullscreen preview.
- For close inspection point students at `out/led.html` (zoom/pan/print) or the
  raw SVG; both scale losslessly. Local links may not be clickable in every
  desktop build, so mention the file path in text too.
- Keep output filenames plain: `@` is parsed as a context mention and spaces
  can break the link, so `out/led.png` works while `out/led@2x.png` does not.

## Writing a circuit

Copy `circuits/led.yml` and edit it. Full schema:

```yaml
board: freenove-esp32-wrover      # required; see render.py --list
# freenove-esp32-wrover-ext       # same board seated on the GPIO extension board

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

camera: true                      # optional: draw the camera on the board
```

### Endpoints

| Form           | Meaning                                              |
| -------------- | ---------------------------------------------------- |
| `board.GPIO2`  | pin by silkscreen name — only when the name is unique |
| `board.R17`    | right header, 17th pin from the top (1-based)         |
| `board.L1`     | left header, 1st pin from the top                     |
| `bb.2.a`       | breadboard column 2, row a                            |
| `driver.OUT1`  | a component terminal, when the component has an `id`  |

**Component terminals.** Give a component an `id:` and you can wire to its
terminals, e.g. the L298N's `OUT1`–`OUT4` screw outputs:

```yaml
components:
  - {type: l298n, id: driver, at: [0, a]}
wires:
  - {from: driver.OUT1, to: bb.2.j, color: red, label: left motor +}
```

The usual way to wire a motor is: plug the motor's leads into two breadboard
columns (`motor at: [2, j]`), then wire those columns to `driver.OUT1/OUT2` —
the column is the junction, exactly like on the real board. See
`circuits/robot-drive.yml`.

Rows `a`–`e` are the top half, `f`–`j` the bottom half. Holes in one column
within the same half are already connected — that is the whole point of a
breadboard, and the renderer highlights those columns automatically.

**GND is not unique on this board** (it appears five times). `board.GND` raises
an error listing the candidates; use `board.R17` style instead. Same for any
repeated name.

### Component library

Defined in `bbd/components.py`. Footprints follow the real kit parts.

| `type`            | Required keys            | Notes                                              |
| ----------------- | ------------------------ | -------------------------------------------------- |
| `resistor`        | `value`, `from`          | `span` defaults to 4 columns (0.4")                 |
| `led`             | `at`                     | anode at `at`, cathode one column right             |
| `diode`           | `from`                   | axial, silver band = cathode; `band: left` to flip  |
| `photoresistor`   | `at`                     | LDR, 2 legs one column apart                        |
| `thermistor`      | `at`                     | 2 legs one column apart                             |
| `button`          | `at`                     | 4 legs, 0.3" wide, 2 rows tall                      |
| `buzzer`          | `at`                     | 2 pins, one column apart                            |
| `speaker`         | `at`                     | 2 wires (red/black), body above the board           |
| `potentiometer`   | `at`                     | 3 legs; `pins: [left, wiper, right]` to label them  |
| `transistor`      | `at`                     | TO-92, 3 legs; `kind: npn\|pnp`, `pins: [E, B, C]`  |
| `rgb_led`         | `at`                     | 4 legs; `pins: [R, common, G, B]`, `common_at: 1`   |
| `ic`              | `at`                     | DIP straddling the channel; `pins: 16`, `label_text`, `pin_labels: true` |
| `display_7seg`    | `at`                     | 10 pins (5+5) straddling; `pins: 10`                |
| `bar_graph`       | `at`                     | 20 pins (10+10) straddling; `pins: 20`              |
| `servo`           | `at`                     | 3 wires (brown/red/orange)                          |
| `motor`           | `at`                     | TT gearbox + wheel, 2 wires                         |
| `battery`         | `at`                     | 9V clip, 2 wires                                    |
| `ultrasonic`      | `at`                     | HC-SR04, 4 pins; `pins:` to relabel                 |
| `joystick`        | `at`                     | KY-023, 5 pins; `pins:` to relabel                  |
| `lcd`             | `at`                     | LCD1602 + I2C backpack, 4 pins                      |
| `l298n`           | `at`                     | motor driver board, 8 pins; `pins:` to relabel      |
| `module`          | `at`, `pins`, `label_text` | generic labelled sensor board                     |

DIP parts (`ic`, `display_7seg`, `bar_graph`) always straddle the centre
channel: pins land in row `e` and row `f`, so `at: [col, e]` and the row part
is ignored. 3- and 4-lead parts occupy consecutive columns starting at `at`.

## MicroPython rules

The class runs MicroPython (Thonny + the kit's Python tutorial), and the pin
choices in the examples follow it. Keep these in mind:

- **Analog inputs only on ADC1: GPIO 32-39.** ADC2 does not work while Wi-Fi is on. GPIO 34-39 are input-only (no output, no pull-up).
- **Buttons**: use `Pin.PULL_UP` in code and wire the button between the pin and GND — no resistor needed.
- **Servo**: signal on GPIO 15, 50 Hz PWM; power from 5 V.
- **Ultrasonic HC-SR04**: 5 V powered, Trig GPIO 13, Echo GPIO 14.
- **LCD1602 I2C**: `I2C(scl=Pin(14), sda=Pin(13))` — the class's pins, not MicroPython's defaults.
- **Motor driver (L298N)**: IN1 GPIO 12, IN2 GPIO 14, ENA GPIO 13 (PWM); battery + common ground.
- **74HC595**: DS GPIO 14, ST_CP GPIO 12, SH_CP GPIO 13, OE GPIO 5, MR tied high.
- **Camera**: needs custom firmware (lemariva/micropython-camera-driver) and claims GPIO 4, 5, 18, 19, 21, 22, 23, 25, 26, 27, 34, 35, 36, 39 — pot/joystick/LDR circuits stop working while it is flashed. Say so in a note.

The examples in `circuits/` already follow this table — start from the closest one.

## Boards

| board                          | when                                            |
| ------------------------------ | ----------------------------------------------- |
| `freenove-esp32-wrover`        | bare board; wires go straight to its header pins |
| `freenove-esp32-wrover-ext`    | ESP32 seated on the GPIO extension board — the class setup |

On the extension board every pin has a single pad that a jumper plugs into
(gold when the pin is highlighted), and the labels sit inside the board so
wires never cross them. Use it for class handouts; use the bare board when
showing the board itself.

## Pitfalls

- Component legs and wire endpoints must land on real columns. If a wire looks
  wrong, check the column number against the rendered image before editing code.
- `span` on a resistor is the gap between legs, in columns. 4 columns is the
  standard 0.4" lead spacing.
- Wires are auto-routed: right-hand pins through the gutter, left-hand pins
  down the left side and across the corridor under the board. If two runs
  overlap, give one an explicit `via:`.
- Tall parts (modules, LCD, servo, motor, battery) sit above their row. Leave
  the rows above them clear of other parts, or move the part to a lower row.
- **Re-render and actually look at the PNG after every edit.** Layout is
  geometry; reasoning about coordinates in your head is unreliable.

## Adding a board

Copy `boards/freenove-esp32-wrover.yml`, replace `headers.left` /
`headers.right` with the pin names in physical top-to-bottom order, and set
`highlight:` to the pins that should glow. Geometry lives in `bbd/layout.py`
and can be overridden per circuit under a `layout:` key (board YAML defaults
merge with circuit overrides).
