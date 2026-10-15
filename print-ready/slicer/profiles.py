"""Machine profiles for the two printers in the Nolop makerspace.

Both machines print **PLA only** in this class, on a 0.4 mm nozzle. That is not
a simplification for convenience: PrusaSlicer's printer profiles carry their
start/end G-code as *template* text (placeholders, `{if}` blocks, ternaries and
regex matches). For PLA on a 0.4 nozzle every one of those conditions collapses
to a constant, so the template can be resolved once and shipped as literal
G-code. Switch this skill to PETG or ASA and the chamber block on the CORE One
stops being a no-op - see `docs` in SKILL.md.

Values were read out of PrusaSlicer's own vendor bundle
(`PrusaResearch.ini`, PrusaSlicer 2.9.6):

    printer   : Prusa CORE One HF0.4 nozzle
    printer   : Original Prusa MK4 Input Shaper 0.4 nozzle
    filament  : Prusament PLA @COREONE   (inherits Prusament PLA @PGIS)
    filament  : Prusament PLA @PGIS

Prusament PLA @COREONE inherits @PGIS, so both machines print PLA at the same
temperature. What differs is the build volume, the firmware model string, the
fan ramp, and - on the CORE One - the enclosure.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Machine:
    key: str
    name: str
    #: PrusaSlicer's `printer_model`: the firmware checks this with M862.3.
    model: str
    #: The firmware version the profile is written against (M115).
    firmware: str
    bed_x: float
    bed_y: float
    bed_z: float
    nozzle: float
    #: PLA. first layer / other layers.
    first_layer_temp: int
    temp: int
    #: Temperature held during mesh bed levelling.
    mbl_temp: int
    bed_temp: int
    #: PrusaSlicer's fan settings for PLA on this machine.
    min_fan_speed: int
    max_fan_speed: int
    fan_below_layer_time: int
    #: CORE One has a heated chamber; MK4 does not.
    chamber_temp: int | None = None
    notes: str = ""


MK4 = Machine(
    key="mk4",
    name="Original Prusa MK4",
    model="MK4",
    firmware="U6.1.3+7898",
    bed_x=250.0,
    bed_y=210.0,
    bed_z=220.0,
    nozzle=0.4,
    first_layer_temp=230,
    temp=225,
    mbl_temp=170,
    bed_temp=60,
    min_fan_speed=70,
    max_fan_speed=100,
    fan_below_layer_time=17,
    notes="open frame, no enclosure",
)

COREONE = Machine(
    key="coreone",
    name="Prusa CORE One",
    model="COREONE",
    firmware="U6.3.0+10073",
    bed_x=250.0,
    bed_y=220.0,
    bed_z=270.0,
    nozzle=0.4,
    first_layer_temp=230,
    temp=225,
    mbl_temp=170,
    bed_temp=60,
    min_fan_speed=85,
    max_fan_speed=100,
    fan_below_layer_time=40,
    chamber_temp=20,
    notes="enclosed; PLA runs with the chamber at 20 C",
)

MACHINES = {m.key: m for m in (MK4, COREONE)}


def _m555(m: Machine, bounds: tuple[float, float, float, float]) -> str:
    """The M555 print-area rectangle, from the model's own first-layer bounds.

    PrusaSlicer computes this rather than hardcoding it, and the CORE One and
    MK4 differ in where their purge line sits, so the rectangle differs too.
    `bounds` is (minx, miny, maxx, maxy) in printer coordinates.
    """
    minx, miny, maxx, maxy = bounds
    x0 = min(m.bed_x, minx + 32.0) - 32.0
    y0 = max(0.0, miny) - 4.0
    x1 = min(m.bed_x, max(minx + 32.0, maxx))
    y1 = maxy
    return f"M555 X{x0:.0f} Y{y0:.0f} W{x1 - x0:.0f} H{y1 - y0:.0f}"


def start_gcode(m: Machine, bounds: tuple[float, float, float, float]) -> str:
    """The printer's own start sequence, resolved for PLA on a 0.4 nozzle."""
    chamber = ""
    if m.chamber_temp is not None:
        chamber = f"\nM141 S{m.chamber_temp} ; set nominal chamber temp\n"
    return f"""M17 ; enable steppers
M862.1 P{m.nozzle} A0 F0 ; nozzle check
M862.3 P "{m.model}" ; printer model check
M862.5 P2 ; g-code level check
M862.6 P"Input shaper" ; FW feature check
M115 {m.firmware}

{_m555(m, bounds)}

G90 ; use absolute coordinates
M83 ; extruder relative mode

M140 S{m.bed_temp} ; set bed temp
M104 T0 S{m.mbl_temp} ; set extruder temp for bed leveling
M109 T0 R{m.mbl_temp} ; wait for temp{chamber}
M84 E ; turn off E motor

G28 ; home all without mesh bed level

G1 X42 Y-4 Z5 F4800

M302 S160 ; lower cold extrusion limit to 160C

G1 E-2 F2400 ; retraction

M84 E ; turn off E motor

G29 P9 X10 Y-4 W32 H4

M106 S100

G0 Z40 F10000

M190 S{m.bed_temp} ; wait for bed temp

M107

;
; MBL
;
M84 E ; turn off E motor
G29 P1 ; invalidate mbl & probe print area
G29 P1 X0 Y0 W50 H20 C ; probe near purge place
G29 P3.2 ; interpolate mbl probes
G29 P3.13 ; extrapolate mbl outside probe area
G29 A ; activate mbl

; prepare for purge
M104 S{m.first_layer_temp}
G0 X0 Y-4 Z15 F4800 ; move away and ready for the purge
M109 S{m.first_layer_temp}

G92 E0
M569 S0 E ; set spreadcycle mode for extruder

;
; Extrude purge line
;
G92 E0 ; reset extruder position
G1 E2 F2400 ; deretraction after the initial one before nozzle cleaning
G0 E7 X15 Z0.2 F500 ; purge
G0 X25 E4 F500 ; purge
G0 X35 E4 F650 ; purge
G0 X45 E4 F800 ; purge
G0 X48 Z0.05 F8000 ; wipe, move close to the bed
G0 X51 Z0.2 F8000 ; wipe, move quickly away from the bed

G92 E0
M221 S100 ; set flow to 100%
"""


def end_gcode(m: Machine, max_layer_z: float) -> str:
    """The printer's own end sequence, with the head parked clear of the part."""
    out = [f"G1 Z{min(max_layer_z + 1, m.bed_z):.1f} F720 ; Move print head up"]
    if m.chamber_temp is not None:
        out.append("G1 E-1 F2400 ; additional retraction")
    out += [
        "M104 S0 ; turn off temperature",
        "M140 S0 ; turn off heatbed",
    ]
    if m.chamber_temp is not None:
        out.append("M141 S0 ; disable chamber control")
    out += [
        "M107 ; turn off fan",
        f"G1 X{241 if m.key == 'mk4' else 242} "
        f"Y{170 if m.key == 'mk4' else -9} F{'3600' if m.key == 'mk4' else '10200'} ; park",
        f"G1 Z{min(max_layer_z + 23, m.bed_z):.1f} F300 ; Move print head up",
        "G4 ; wait",
        "M572 S0 ; reset PA",
        "M593 X T2 F0 ; disable IS",
        "M593 Y T2 F0 ; disable IS",
        "M84 X Y E ; disable motors",
        f"; max_layer_z = {max_layer_z:.1f}",
    ]
    return "\n".join(out) + "\n"
