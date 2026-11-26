"""🧩 The mechanism kit: animated building blocks for ANY machine (gears, pistons, valves, pumps, fans, turbines,
belts, chains, pulleys, hydraulics, springs, levers, wheels, motors, batteries + wires, heating coils, tanks, drums,
lights, glowing emitters).

A kit piece is a list of recipe parts (the same JSON the object builder uses), so Gemini, hand-written recipes and
the built-in planner can all combine them. In a recipe:

    {"kit": "turbine", "name": "compressor", "pos": [0.4, 1.0, 0], "size": 0.8, "axis": "x", "stages": 4}

becomes parts called "compressor", "compressor_shaft", "compressor_case"… (the camera can aim at "eng1.compressor"),
plus their flow paths ("compressor_flow") and ports. `size` is the main size in metres; `axis` is the main axis
(shaft / travel direction). Every piece is also in the library as its own object (`kit_<name>`).

`compose(topic)` (no AI): a believable machine made from kit pieces for a topic the library doesn't have.
"""

from __future__ import annotations

import math
import re

import numpy as np

STEEL, DARK, COPPER, BRASS, RUBBER = "#9aa3ab", "#4b535b", "#c8763c", "#c9a227", "#26292d"
WHITE, GLASS, WATER, HOT = "#f2f2ee", "#bfe9ff", "#3aa6d9", "#ff6a2a"


def _p(name, shape, size, pos=(0, 0, 0), color=STEEL, **kw) -> dict:
    d = {"name": name, "shape": shape, "size": [float(x) for x in size], "pos": [float(x) for x in pos],
         "color": color}
    d.update({k: v for k, v in kw.items() if v is not None})
    return d


def _spin(speed=1.0, axis="x", **kw) -> dict:
    return {"type": "spin", "axis": axis, "speed": float(speed), **kw}


# ------------------------------------------------------------------------------------------------------------
# Pieces: every function builds its piece with the main axis along X, centred at the origin, size s (metres)
# ------------------------------------------------------------------------------------------------------------


def gear_train(s=0.3, teeth=12, count=2, **_):
    """Meshing gears in a row: each turns the other way; a small gear turns faster."""
    parts, x = [], 0.0
    radii = [s * (1.0 if k % 2 == 0 else 0.6) for k in range(max(2, min(4, int(count))))]
    for k, r in enumerate(radii):
        if k:
            x += radii[k - 1] + r - s * 0.08
        n = max(6, int(teeth * r / s))
        parts.append(_p("" if k == 0 else f"gear{k + 1}", "gear", [r, s * 0.2], (0, x, 0), BRASS if k % 2 else STEEL,
                        teeth=n, rot=[0, 90, 0], material="metal",
                        motion=_spin((1 if k % 2 == 0 else -1) * s / r, "x"), pivot=[0, x, 0]))
        parts.append(_p(f"axle{k + 1}", "cylinder", [s * 0.06, s * 0.5], (0, x, 0), DARK, rot=[0, 0, 90],
                        material="metal"))
    return {"parts": parts}


def piston_crank(s=0.3, **_):
    """A piston in a cylinder pushed by a crank: up and down becomes round and round."""
    r = s * 0.35
    return {"parts": [
        _p("cylinder", "cylinder", [s * 0.42, s * 1.3], (0, s * 0.9, 0), GLASS, opacity=0.35, shell=True,
           material="glass"),
        _p("", "cylinder", [s * 0.38, s * 0.4], (0, s * 0.9, 0), "#d3d8dc", material="metal",
           motion={"type": "slide", "axis": "y", "amp": r, "len": s * 0.9}),
        _p("rod", "box", [s * 0.1, s * 0.9, s * 0.08], (0, s * 0.35, 0), DARK, material="metal",
           motion={"type": "rod", "axis": "x", "r": r, "len": s * 0.9}, pivot=[0, -s * 0.1, 0]),
        _p("crank", "cylinder", [s * 0.45, s * 0.12], (0, -s * 0.1, -s * 0.1), STEEL, rot=[90, 0, 0],
           material="metal", motion=_spin(1, "z"), pivot=[0, -s * 0.1, 0]),
    ]}


def valve(s=0.2, **_):
    """A pipe with a gate that opens and closes (water, gas, air)."""
    return {"parts": [
        _p("body", "cylinder", [s * 0.5, s * 0.8], (0, 0, 0), DARK, rot=[0, 0, 90], shell=True, material="metal"),
        _p("", "cylinder", [s * 0.44, s * 0.05], (0, 0, 0), BRASS, rot=[0, 0, 90], material="metal",
           motion={"type": "open", "axis": "y", "deg": 85}),
        _p("handle", "box", [s * 0.7, s * 0.06, s * 0.1], (0, s * 0.62, 0), "#d9534f", material="paint",
           motion={"type": "swing", "axis": "y", "deg": 85, "drive": "open"}, pivot=[0, s * 0.62, 0]),
    ], "ports": {"inlet": [-s * 0.4, 0, 0], "outlet": [s * 0.4, 0, 0]}}


def pump(s=0.3, **_):
    """A pump: a spinning impeller flings the liquid out of the outlet."""
    return {"parts": [
        _p("housing", "cylinder", [s * 0.6, s * 0.45], (0, 0, 0), "#2f6fb5", rot=[90, 0, 0], shell=True,
           material="paint"),
        _p("", "blades", [s * 0.5, s * 0.12, s * 0.3], (0, 0, 0), BRASS, count=6, material="metal",
           motion=_spin(2.0, "z")),
        _p("inlet_pipe", "cylinder", [s * 0.16, s * 0.6], (-s * 0.75, 0, 0), STEEL, rot=[0, 0, 90], material="metal"),
        _p("outlet_pipe", "cylinder", [s * 0.14, s * 0.55], (0, s * 0.8, 0), STEEL, material="metal"),
    ], "paths": {"flow": [[-s * 1.0, 0, 0], [-s * 0.2, 0, 0], [0, s * 0.3, 0], [0, s * 1.1, 0]]},
        "ports": {"inlet": [-s * 1.05, 0, 0], "outlet": [0, s * 1.1, 0]}}


def fan(s=0.4, blades=5, **_):
    """A fan: blades on a hub push air through a round guard."""
    return {"parts": [
        _p("", "blades", [s * 0.9, s * 0.28, s * 0.06], (0, 0, 0), "#e9eef1", count=int(blades), material="plastic",
           motion=_spin(2.5, "z")),
        _p("hub", "dome", [s * 0.18, s * 0.16], (0, 0, s * 0.04), DARK, rot=[90, 0, 0], material="plastic"),
        _p("guard", "torus", [s * 1.0, s * 0.03], (0, 0, 0), DARK, rot=[90, 0, 0], material="metal"),
    ], "paths": {"air": [[0, 0, -s * 1.2], [0, 0, s * 1.8]]}}


def turbine(s=0.6, stages=3, **_):
    """Turbine / compressor stages: discs of blades on one shaft, inside a casing (jet engines, power plants)."""
    n = max(1, min(8, int(stages)))
    parts = [_p("shaft", "cylinder", [s * 0.08, s * (0.4 + 0.35 * n)], (0, 0, 0), STEEL, rot=[0, 0, 90],
                material="metal", motion=_spin(3.0, "x"))]
    for k in range(n):
        x = -s * 0.175 * (n - 1) + s * 0.35 * k
        parts.append(_p("" if k == 0 else f"stage{k + 1}", "blades", [s * (0.95 - 0.05 * k), s * 0.12, s * 0.05],
                        (x, 0, 0), "#c3c9cf", count=14, rot=[0, 90, 0], material="metal", motion=_spin(3.0, "x")))
    parts.append(_p("case", "cylinder", [s * 1.02, s * (0.35 * n + 0.2)], (0, 0, 0), "#8f9ba8", rot=[0, 0, 90],
                    shell=True, opacity=1.0, material="metal"))
    return {"parts": parts, "paths": {"flow": [[-s * (0.3 * n + 0.6), 0, 0], [s * (0.3 * n + 0.6), 0, 0]]}}


def belt_drive(s=0.3, **_):
    """Two pulleys and a belt: the motor's pulley turns the big one (washing machines, cars)."""
    big, small, d = s, s * 0.35, s * 2.2
    loop = [[0, big, 0.02], [d, small, 0.02], [d + small, 0, 0.02], [d, -small, 0.02], [0, -big, 0.02],
            [-big, 0, 0.02], [0, big, 0.02]]
    return {"parts": [
        _p("", "cylinder", [big, s * 0.12], (0, 0, 0), STEEL, rot=[90, 0, 0], material="metal",
           motion=_spin(small / big, "z")),
        _p("small_pulley", "cylinder", [small, s * 0.14], (d, 0, 0), DARK, rot=[90, 0, 0], material="metal",
           motion=_spin(1.0, "z")),
        _p("belt", "tube", [s * 0.03], color=RUBBER, points=loop, material="rubber"),
    ], "paths": {"belt": loop}}


def chain_drive(s=0.3, **_):
    """Two sprockets and a chain (bikes, motorbikes, conveyors)."""
    out = belt_drive(s)
    for p in out["parts"]:
        if p["shape"] == "cylinder":
            p["shape"], p["teeth"] = "gear", 16 if p["name"] == "" else 9
            p["size"] = [p["size"][0], p["size"][1]]
            p["rot"] = [0, 0, 0]
        if p["name"] == "belt":
            p["name"], p["color"] = "chain", "#3a3f45"
    out["paths"] = {"chain": out["paths"]["belt"]}
    return out


def pulley_cable(s=0.4, **_):
    """A pulley, a cable and a load that goes up and down (cranes, lifts, flagpoles)."""
    h = s * 4
    return {"parts": [
        _p("", "cylinder", [s * 0.5, s * 0.15], (0, h, 0), STEEL, rot=[90, 0, 0], material="metal",
           motion={"type": "spin", "axis": "z", "drive": "lift", "ratio": -2.0}, pivot=[0, h, 0]),
        _p("cable", "cylinder", [s * 0.025, h - s * 0.8], (s * 0.5, s * 0.8, 0), "#2e3338", material="metal",
           motion={"type": "stretch", "axis": "y", "amp": s * 1.6}, pivot=[s * 0.5, h, 0]),
        _p("load", "box", [s * 0.7, s * 0.6, s * 0.7], (s * 0.5, s * 0.5, 0), "#e07b39", material="paint",
           motion={"type": "lift", "axis": "y", "amp": s * 1.6}),
        _p("frame", "box", [s * 0.12, h + s * 0.3, s * 0.12], (-s * 0.6, h / 2, 0), DARK, material="metal"),
    ]}


def hydraulic_cylinder(s=0.3, **_):
    """A hydraulic ram: oil pushed in moves the rod out with great force (diggers, car lifts, brakes)."""
    return {"parts": [
        _p("barrel", "cylinder", [s * 0.3, s * 1.4], (0, 0, 0), "#d9a400", rot=[0, 0, 90], shell=True,
           material="paint"),
        _p("oil", "cylinder", [s * 0.26, s * 0.9], (-s * 0.22, 0, 0), "#c98b1a", rot=[0, 0, 90], kind="liquid",
           opacity=0.85),
        _p("", "cylinder", [s * 0.12, s * 1.3], (s * 0.8, 0, 0), "#e6e9ec", rot=[0, 0, 90], material="metal",
           motion={"type": "slide", "axis": "x", "amp": s * 0.45}),
    ], "ports": {"inlet": [-s * 0.72, s * 0.3, 0]},
        "paths": {"oil": [[-s * 1.2, s * 0.6, 0], [-s * 0.72, s * 0.3, 0], [-s * 0.5, 0, 0]]}}


def spring(s=0.3, turns=6, **_):
    """A coil spring that squeezes and springs back."""
    return {"parts": [_p("", "spring", [s * 0.3, s * 1.2, s * 0.04], (0, 0, 0), "#b8c1c6", turns=int(turns),
                         rot=[0, 0, -90], material="metal",
                         motion={"type": "squash", "axis": "x", "amp": 0.35, "speed": 1.0},
                         pivot=[-s * 0.6, 0, 0])]}


def lever(s=0.5, **_):
    """A lever on a pivot: a small push on the long side lifts a big load on the short side."""
    return {"parts": [
        _p("", "box", [s * 2.4, s * 0.08, s * 0.2], (0, s * 0.42, 0), "#a0703f", material="paint",
           motion={"type": "swing", "axis": "z", "deg": 12}, pivot=[0, s * 0.42, 0]),
        _p("fulcrum", "wedge", [s * 0.35, s * 0.38, s * 0.25], (0, s * 0.2, 0), DARK, material="metal"),
    ]}


def wheel_axle(s=0.35, **_):
    """Two wheels on an axle (carts, cars, robots)."""
    return {"parts": [
        _p("", "cylinder", [s, s * 0.3], (0, s, -s * 0.9), RUBBER, rot=[90, 0, 0], kind="wheel", axis="z",
           pivot=[0, s, -s * 0.9], material="rubber", motion=_spin(1.0, "z")),
        _p("wheel2", "cylinder", [s, s * 0.3], (0, s, s * 0.9), RUBBER, rot=[90, 0, 0], kind="wheel", axis="z",
           pivot=[0, s, s * 0.9], material="rubber", motion=_spin(1.0, "z")),
        _p("axle", "cylinder", [s * 0.08, s * 1.9], (0, s, 0), STEEL, rot=[90, 0, 0], material="metal"),
    ]}


def motor(s=0.25, **_):
    """An electric motor: coils and magnets spin the shaft."""
    return {"parts": [
        _p("", "cylinder", [s * 0.5, s * 1.2], (0, 0, 0), "#2f6fb5", rot=[0, 0, 90], shell=True, material="paint"),
        _p("rotor", "cylinder", [s * 0.32, s * 0.9], (0, 0, 0), COPPER, rot=[0, 0, 90], material="metal",
           motion=_spin(2.0, "x")),
        _p("shaft", "cylinder", [s * 0.07, s * 0.6], (s * 0.85, 0, 0), STEEL, rot=[0, 0, 90], material="metal",
           motion=_spin(2.0, "x")),
        _p("fins", "box", [s * 1.0, s * 1.08, s * 0.05], (0, 0, 0), "#255a94", material="paint"),
    ], "ports": {"power": [-s * 0.65, s * 0.3, 0]}}


def battery_wire(s=0.3, **_):
    """A battery, a wire loop and a bulb: electricity flows round the circuit and the bulb lights up."""
    loop = [[s * 0.4, s * 0.6, 0], [s * 2.0, s * 0.6, 0], [s * 2.0, -s * 0.2, 0], [s * 1.2, -s * 0.2, 0],
            [s * 0.4, -s * 0.2, 0]]
    return {"parts": [
        _p("", "cylinder", [s * 0.28, s * 0.9], (0, s * 0.2, 0), "#2b2f35", rot=[0, 0, 90], material="plastic"),
        _p("terminal", "cylinder", [s * 0.1, s * 0.12], (s * 0.5, s * 0.2, 0), "#c9a227", rot=[0, 0, 90],
           material="metal"),
        _p("wire", "tube", [s * 0.03], color="#d9534f", points=loop, material="plastic"),
        _p("bulb", "sphere", [s * 0.22], (s * 2.0, s * 0.85, 0), "#fff6d8", kind="light", opacity=0.8,
           material="glass"),
    ], "paths": {"current": loop}, "ports": {"power": [s * 0.5, s * 0.2, 0]}}


def heating_coil(s=0.3, **_):
    """A heating coil: electricity makes the wire glow hot (toasters, kettles, dryers)."""
    return {"parts": [
        _p("", "spring", [s * 0.2, s * 1.4, s * 0.03], (0, 0, 0), "#7a5a4a", turns=10, rot=[0, 0, -90],
           kind="heater", material="metal"),
        _p("holder", "box", [s * 1.7, s * 0.08, s * 0.3], (0, -s * 0.28, 0), "#e9e3d6", material="ceramic"),
    ], "ports": {"power": [-s * 0.8, 0, 0]}}


def tank_pipe(s=0.5, **_):
    """A tank of liquid with a pipe out of the bottom (water heaters, washing machines, fuel)."""
    return {"parts": [
        _p("", "cylinder", [s * 0.55, s * 1.2], (0, s * 0.6, 0), GLASS, opacity=0.3, shell=True, material="glass"),
        _p("liquid", "cylinder", [s * 0.5, s * 0.8], (0, s * 0.42, 0), WATER, kind="liquid", opacity=0.75,
           material="water"),
        _p("pipe", "tube", [s * 0.07], color=STEEL, points=[[0, s * 0.02, 0], [0, -s * 0.0, 0], [s * 1.1, 0, 0]],
           material="metal"),
    ], "paths": {"water": [[0, s * 0.4, 0], [0, s * 0.02, 0], [s * 1.1, 0, 0]]},
        "ports": {"outlet": [s * 1.1, 0, 0], "inlet": [0, s * 1.2, 0]}}


def drum(s=0.4, **_):
    """A drum with holes that tumbles what is inside (washing machines, dryers, concrete mixers)."""
    parts = [_p("", "cylinder", [s, s * 1.1], (0, 0, 0), "#c3c9cf", rot=[0, 0, 90], shell=True, material="metal",
                motion=_spin(1.2, "x"))]
    for k in range(3):  # paddles inside that lift the clothes
        a = k * 2 * math.pi / 3
        parts.append(_p(f"paddle{k + 1}", "box", [s * 1.0, s * 0.14, s * 0.1],
                        (0, s * 0.88 * math.cos(a), s * 0.88 * math.sin(a)), "#9aa3ab", material="metal",
                        rot=[math.degrees(a), 0, 0], motion=_spin(1.2, "x"), pivot=[0, 0, 0]))
    return {"parts": parts}


def light(s=0.15, **_):
    """A lamp that turns on (light_on)."""
    return {"parts": [_p("", "sphere", [s], (0, 0, 0), "#fff6d8", kind="light", opacity=0.85, material="glass"),
                      _p("socket", "cylinder", [s * 0.5, s * 0.6], (0, s * 0.9, 0), DARK, material="metal")]}


def emitter(s=0.2, **_):
    """A glowing source that pulses (a magnetron, a laser, a spark gap): add flows from it for waves or heat."""
    return {"parts": [_p("", "cylinder", [s * 0.6, s * 0.8], (0, 0, 0), COPPER, material="metal"),
                      _p("glow", "sphere", [s * 0.35], (0, s * 0.55, 0), "#9fd8ff", emissive=0.9,
                         motion={"type": "pulse", "speed": 2.0})],
            "paths": {"waves": [[0, s * 0.6, 0], [0, s * 2.0, 0], [s * 1.5, s * 2.6, 0]]}}


KIT = {f.__name__: f for f in (gear_train, piston_crank, valve, pump, fan, turbine, belt_drive, chain_drive,
                               pulley_cable, hydraulic_cylinder, spring, lever, wheel_axle, motor, battery_wire,
                               heating_coil, tank_pipe, drum, light, emitter)}
ALIASES = {"gears": "gear_train", "gear": "gear_train", "piston": "piston_crank", "crank": "piston_crank",
           "impeller": "pump", "propeller": "fan", "blades": "fan", "compressor": "turbine", "belt": "belt_drive",
           "chain": "chain_drive", "pulley": "pulley_cable", "cable": "pulley_cable", "hydraulic": "hydraulic_cylinder",
           "ram": "hydraulic_cylinder", "coil_spring": "spring", "wheel": "wheel_axle", "wheels": "wheel_axle",
           "electric_motor": "motor", "battery": "battery_wire", "circuit": "battery_wire", "heater": "heating_coil",
           "element": "heating_coil", "tank": "tank_pipe", "lamp": "light", "bulb": "light", "magnetron": "emitter"}


def describe() -> str:
    """One line per piece (shown to the AI designer)."""
    return "\n".join(f"- {k}: {f.__doc__.strip()}" for k, f in KIT.items())


# ------------------------------------------------------------------------------------------------------------
# Expanding a kit part inside a recipe
# ------------------------------------------------------------------------------------------------------------

_AXES = {"x": np.eye(3), "y": np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], float),  # x → y (stand up)
         "z": np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float),  # x → z (towards the camera)
         "-x": np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], float),  # turned around
         "-y": np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], float),  # x → -y (hanging down)
         "-z": np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)}  # x → -z (away from the camera)
_ROT_OF = {"x": (0.0, 0.0, 0.0), "y": (0.0, 0.0, 90.0), "z": (0.0, -90.0, 0.0), "-x": (0.0, 180.0, 0.0),
           "-y": (0.0, 0.0, -90.0), "-z": (0.0, 90.0, 0.0)}


def _axis_letter(R: np.ndarray, a: str) -> str:
    v = R @ np.eye(3)["xyz".index(a)]
    return "xyz"[int(np.argmax(np.abs(v)))]


def expand(kp: dict) -> tuple[list, dict, dict]:
    """A recipe part {"kit": …} → (parts, paths, ports), placed at its pos, turned to its axis, names prefixed."""
    kind = re.sub(r"[^a-z0-9_]+", "_", str(kp.get("kit") or "").lower()).strip("_")
    kind = ALIASES.get(kind, kind)
    fn = KIT.get(kind)
    if fn is None:
        return [], {}, {}
    try:
        size = float(kp.get("size", 0) if not isinstance(kp.get("size"), (list, tuple)) else kp["size"][0]) or 0.0
    except (TypeError, ValueError):
        size = 0.0
    extra = {k: v for k, v in kp.items() if k in ("teeth", "count", "stages", "blades", "turns")}
    out = fn(size, **extra) if size > 0 else fn(**extra)
    name = re.sub(r"[^a-z0-9_]+", "_", str(kp.get("name") or kind).lower()).strip("_") or kind
    ax = kp.get("axis") if kp.get("axis") in _AXES else "x"
    R = _AXES[ax]
    pos = np.asarray([float(x) for x in (list(kp.get("pos") or [0, 0, 0]) + [0, 0, 0])[:3]])
    color = kp.get("color")
    parts = []
    for p in out["parts"]:
        q = dict(p)
        q["name"] = name if not p["name"] else f"{name}_{p['name']}"
        q["pos"] = list(R @ np.asarray(p.get("pos", [0, 0, 0]), float) + pos)
        if "points" in q:
            q["points"] = [list(R @ np.asarray(pt, float) + pos) for pt in q["points"]]
        if "pivot" in q:
            q["pivot"] = list(R @ np.asarray(q["pivot"], float) + pos)
        elif q.get("motion"):
            q["pivot"] = list(R @ np.asarray(p.get("pos", [0, 0, 0]), float) + pos)
        if ax != "x":  # turn the shape with the piece (rot is applied after the shape's own rot)
            q["post_rot"] = list(_ROT_OF[ax])
        mos = q.get("motion")
        if mos:
            ml = mos if isinstance(mos, list) else [mos]
            ml = [{**m, "axis": _axis_letter(R, m["axis"])} if m.get("axis") in ("x", "y", "z") else m for m in ml]
            q["motion"] = ml if isinstance(mos, list) else ml[0]
        if q.get("axis") in ("x", "y", "z"):
            q["axis"] = _axis_letter(R, q["axis"])
        if color and not p["name"]:
            q["color"] = color
        parts.append(q)
    paths = {(f"{name}_{k}" if k else name): [list(R @ np.asarray(pt, float) + pos) for pt in pts]
             for k, pts in (out.get("paths") or {}).items()}
    ports = {}
    for k, pt in (out.get("ports") or {}).items():  # "drain_pump_outlet", and plain "outlet" (pipes connect to it)
        ports[f"{name}_{k}" if k != name else k] = list(R @ np.asarray(pt, float) + pos)
        ports.setdefault(k, ports[f"{name}_{k}" if k != name else k])
    return parts, paths, ports


# ------------------------------------------------------------------------------------------------------------
# No AI: a believable machine for a topic the library doesn't have, made of kit pieces
# ------------------------------------------------------------------------------------------------------------

def _case(name, w, h, d, color=WHITE, y=None):
    return _p(name, "box", [w, h, d], (0, h / 2 if y is None else y, 0), color, shell=True, material="paint")


TEMPLATES = {
    "washing_machine": (r"washing machine|washer|laundry", lambda: {
        "about": "a front-loading washing machine cut open: drum, paddles, motor, belt, water pump, door",
        "tags": ["machine", "laundry"], "key_part": "drum",
        "parts": [_case("cabinet", 0.6, 0.85, 0.6),
                  _p("door", "torus", [0.2, 0.04], (0, 0.5, 0.31), "#c3c9cf", rot=[90, 0, 0], material="metal",
                     motion={"type": "open", "axis": "y", "deg": -100}, pivot=[-0.2, 0.5, 0.31]),
                  _p("door_glass", "cylinder", [0.18, 0.03], (0, 0.5, 0.31), GLASS, rot=[90, 0, 0], opacity=0.4,
                     material="glass", motion={"type": "open", "axis": "y", "deg": -100}, pivot=[-0.2, 0.5, 0.31]),
                  {"kit": "drum", "name": "drum", "pos": [0, 0.5, 0], "size": 0.24, "axis": "z"},
                  _p("water", "box", [0.5, 0.14, 0.45], (0, 0.33, 0), WATER, kind="liquid", opacity=0.6,
                     material="water"),
                  {"kit": "motor", "name": "motor", "pos": [0.0, 0.12, -0.12], "size": 0.12, "axis": "z"},
                  {"kit": "belt_drive", "name": "pulley", "pos": [0, 0.5, -0.27], "size": 0.15, "axis": "-y"},
                  {"kit": "pump", "name": "pump", "pos": [-0.18, 0.1, 0.1], "size": 0.08, "axis": "z"},
                  _p("detergent_drawer", "box", [0.18, 0.06, 0.1], (-0.17, 0.8, 0.28), "#e9eef1", material="plastic")],
        "tour": [["door", "You load the clothes through a sealed door."],
                 ["water", "Water flows in and soaks everything."],
                 ["drum", "The drum turns one way, then the other."],
                 ["motor", "A motor turns the drum through a belt."],
                 ["pump", "A pump drains the dirty water out."]]}),
    "jet_engine": (r"jet engine|turbofan|jet turbine|aircraft engine|airplane engine", lambda: {
        "about": "a turbofan jet engine cut open: fan, compressor, combustion chamber, turbine, nozzle",
        "tags": ["machine", "vehicle"], "key_part": "combustor",
        "parts": [_p("nacelle", "lathe", [1.0], (0, 1.2, 0), "#e9eef1", shell=True, material="paint", caps=False,
                     profile=[[0.95, -1.5], [1.0, -1.0], [0.95, 0.6], [0.7, 1.6]], rot=[0, 0, -90]),
                  {"kit": "fan", "name": "fan", "pos": [-1.25, 1.2, 0], "size": 0.9, "axis": "x", "blades": 18},
                  {"kit": "turbine", "name": "compressor", "pos": [-0.45, 1.2, 0], "size": 0.5, "stages": 5},
                  _p("combustor", "cylinder", [0.5, 0.45], (0.25, 1.2, 0), "#c8763c", rot=[0, 0, 90], material="metal",
                     shell=True),
                  _p("flame", "cylinder", [0.32, 0.4], (0.25, 1.2, 0), HOT, rot=[0, 0, 90], kind="flame",
                     emissive=1.0, opacity=0.85),
                  {"kit": "turbine", "name": "turbine", "pos": [0.75, 1.2, 0], "size": 0.45, "stages": 3},
                  _p("nozzle", "lathe", [0.5], (1.25, 1.2, 0), "#5b6672", material="metal",
                     profile=[[0.5, 0.0], [0.3, 0.6]], rot=[0, 0, -90]),
                  _p("pylon", "box", [1.2, 0.5, 0.12], (0, 2.3, 0), "#c3c9cf", material="paint")],
        "paths": {"air": [[-2.0, 1.2, 0], [-0.8, 1.2, 0], [0.25, 1.2, 0], [1.0, 1.2, 0], [2.4, 1.2, 0]],
                  "bypass": [[-2.0, 1.95, 0], [0.0, 1.95, 0], [1.8, 1.85, 0]]},
        "tour": [["fan", "A giant fan sucks in air."], ["compressor", "Spinning blades squeeze the air."],
                 ["combustor", "Fuel burns in the squeezed air."], ["turbine", "Hot gas spins the turbine."],
                 ["nozzle", "The gas blasts out the back and pushes the plane forward."]]}),
    "microwave": (r"microwave", lambda: {
        "about": "a microwave oven cut open: magnetron, waveguide, turntable, glass plate, door, light",
        "tags": ["machine", "kitchen"], "key_part": "magnetron",
        "parts": [_case("cabinet", 0.5, 0.3, 0.38, "#e9eef1"),
                  _p("cavity", "box", [0.32, 0.24, 0.32], (-0.06, 0.15, 0), "#d8dde1", material="metal", opacity=1.0),
                  _p("door", "box", [0.36, 0.26, 0.02], (-0.06, 0.15, 0.2), "#2b2f35", material="glass", opacity=0.6,
                     motion={"type": "open", "axis": "y", "deg": -95}, pivot=[-0.24, 0.15, 0.2]),
                  {"kit": "emitter", "name": "magnetron", "pos": [0.17, 0.08, 0], "size": 0.07},
                  _p("waveguide", "box", [0.06, 0.04, 0.1], (0.13, 0.25, 0), "#9aa3ab", material="metal"),
                  _p("turntable", "cylinder", [0.14, 0.01], (-0.06, 0.04, 0), "#e9f6ff", opacity=0.6,
                     material="glass", motion={"type": "spin", "axis": "y", "speed": 0.15}),
                  _p("food", "box", [0.12, 0.05, 0.12], (-0.06, 0.07, 0), "#d98c4a",
                     motion={"type": "spin", "axis": "y", "speed": 0.15}, pivot=[-0.06, 0.07, 0]),
                  _p("light", "sphere", [0.02], (-0.06, 0.26, -0.1), "#fff6d8", kind="light"),
                  _p("control_panel", "box", [0.1, 0.24, 0.02], (0.19, 0.15, 0.2), "#2b2f35", emissive=0.2)],
        "paths": {"waves": [[0.17, 0.12, 0], [0.13, 0.25, 0], [0.0, 0.2, 0], [-0.06, 0.08, 0]]},
        "tour": [["magnetron", "A magnetron makes microwaves."], ["waveguide", "A metal channel guides them in."],
                 ["food", "The waves make water in the food jiggle, and that makes heat."],
                 ["turntable", "The plate turns, so the food heats evenly."]]}),
    "hair_dryer": (r"hair ?dryer|blow ?dryer", lambda: {
        "about": "a hair dryer cut open: fan, motor, heating coil, nozzle", "tags": ["machine"], "key_part": "coil",
        "parts": [_p("body", "cylinder", [0.06, 0.24], (0, 0.3, 0), "#9a6ad6", rot=[0, 0, 90], shell=True,
                     material="plastic"),
                  _p("handle", "box", [0.05, 0.18, 0.05], (-0.04, 0.17, 0), "#9a6ad6", material="plastic"),
                  {"kit": "fan", "name": "fan", "pos": [-0.09, 0.3, 0], "size": 0.05, "axis": "x"},
                  {"kit": "motor", "name": "motor", "pos": [-0.04, 0.3, 0], "size": 0.04},
                  {"kit": "heating_coil", "name": "coil", "pos": [0.05, 0.3, 0], "size": 0.08}],
        "paths": {"air": [[-0.15, 0.3, 0], [0.2, 0.3, 0]]},
        "tour": [["fan", "A fan pulls air in."], ["coil", "A glowing coil heats it."]]}),
    "blender": (r"blender|food processor", lambda: {
        "about": "a kitchen blender: jar, blades, motor base", "tags": ["machine", "kitchen"], "key_part": "blades",
        "parts": [_p("base", "box", [0.18, 0.12, 0.18], (0, 0.06, 0), "#2b2f35", material="plastic"),
                  {"kit": "motor", "name": "motor", "pos": [0, 0.06, 0], "size": 0.06, "axis": "y"},
                  _p("jar", "lathe", [0.08], (0, 0.13, 0), GLASS, opacity=0.35, shell=True, material="glass",
                     profile=[[0.05, 0.0], [0.08, 0.2], [0.08, 0.24]]),
                  {"kit": "fan", "name": "blades", "pos": [0, 0.15, 0], "size": 0.04, "axis": "y", "blades": 4}],
        "tour": [["motor", "A fast motor sits in the base."], ["blades", "Sharp blades spin thousands of times."]]}),
}


def compose(topic: str) -> dict | None:
    """A recipe made of kit pieces for a machine the library doesn't have (None if nothing fits)."""
    t = (topic or "").lower()
    for name, (pattern, make) in TEMPLATES.items():
        if re.search(pattern, t):
            r = make()
            r["name"] = name
            r.setdefault("aliases", [])
            return r
    return None
