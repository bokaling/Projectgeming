"""How a machine's parts move: real working parts for "how it works" videos.

A part can carry `motion` (a small dict). The world evaluates it at time T from the object's state:

* run (the `spin` action, machines running): the machine turns; its angle is st["spin"] (radians)
    {"type": "spin", "axis": "x", "speed": 1.0}                  crankshaft, fan, gears (speed = turns per machine turn)
    {"type": "slide", "axis": "y", "amp": 0.045, "phase": 0, "len": 0.145}
                                                                  a piston (with "len": the exact crank + rod motion)
    {"type": "rod", "axis": "x", "r": 0.045, "len": 0.145, "phase": 0}
                                                                  a connecting rod (bottom on the crank pin, top on
                                                                  the piston pin; pivot = the crank centre)
    {"type": "valve", "axis": "y", "amp": -0.01, "speed": 0.5, "phase": 135}
                                                                  opens once per 2 turns (a cam pushes it)
    {"type": "swing", "axis": "z", "deg": 18, "phase": 0}        rocker arms, pumpjack heads, wipers
    {"type": "pulse", "speed": 0.5, "phase": 0}                   a spark / flash once per cycle (glows)
    {"type": "chamber", "r": 0.045, "len": 0.145, "phase": 0, "cycle": 0, "top": 0.42}
                                                                  the gas above a piston: squeezed by the piston, its
                                                                  colour shows the stroke (intake, squeeze, bang, out)
* open (the `open` / `close` actions): {"type": "open", "axis": "x", "amp": 0.4} slides, or "deg": 100 swings
* lift (the `lift` action, 0..1): {"type": "lift", "axis": "y", "amp": 9.0}   elevator car (negative = counterweight)
    {"type": "stretch", "axis": "y", "amp": 9.0}   a rope/cable: its pivot end stays, the other end follows the lift
    {"type": "spin", "drive": "lift", "ratio": 6}   a pulley that turns while the lift moves
* level: {"type": "level", "of": "tank_water", "axis": "y", "amp": 0.2}   a float that rides on a liquid part's level

Everything is a pure function of the state (and so of T): resume and single-shot renders still match.
"""

from __future__ import annotations

import math

import numpy as np

from .mesh import rot_matrix

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
STROKE_COLORS = [(1.0, 0.55, 0.16), (0.55, 0.55, 0.58), (0.31, 0.7, 1.0), (0.5, 0.86, 1.0)]  # bang, out, in, squeeze
STROKE_GLOW = [1.3, 0.05, 0.25, 0.35]
TYPES = {"spin", "slide", "rod", "valve", "swing", "pulse", "chamber", "open", "lift", "stretch", "level", "flicker"}


def _axis(m: dict) -> np.ndarray:
    return np.asarray(AXES.get(str(m.get("axis", "y")), AXES["y"]), np.float64)


def _about(rot: np.ndarray, pivot) -> np.ndarray:
    """A rotation around a pivot point, as a 4x4."""
    out = np.eye(4, dtype=np.float32)
    pv = np.asarray(pivot, np.float32)
    out[:3, :3] = rot
    out[:3, 3] = pv - rot @ pv
    return out


def _move(v) -> np.ndarray:
    out = np.eye(4, dtype=np.float32)
    out[:3, 3] = v
    return out


def crank_slider(theta: float, r: float, length: float) -> float:
    """How far a piston pin is below top dead centre (0 at the top, 2r at the bottom) for crank angle theta."""
    s = r * math.sin(theta)
    return (r + length) - (r * math.cos(theta) + math.sqrt(max(length * length - s * s, 1e-12)))


def check(m) -> dict | None:
    """A clean motion dict (or None): unknown types and bad numbers are dropped, never raised."""
    if not isinstance(m, dict) or str(m.get("type", "")) not in TYPES:
        return None
    out = {"type": str(m["type"])}
    if m.get("axis") in AXES:
        out["axis"] = m["axis"]
    for k, lo, hi in (("amp", -60.0, 60.0), ("phase", -720.0, 720.0), ("speed", 0.0, 8.0), ("len", 0.001, 60.0),
                      ("r", 0.0, 30.0), ("deg", -360.0, 360.0), ("ratio", -40.0, 40.0), ("cycle", -720.0, 720.0),
                      ("top", -60.0, 120.0)):
        if isinstance(m.get(k), (int, float)) and not isinstance(m.get(k), bool):
            v = float(m[k])
            if v == v:
                out[k] = max(lo, min(hi, v))
    for k in ("drive", "of"):
        if isinstance(m.get(k), str) and m[k].strip():
            out[k] = m[k].strip()[:24]
    return out


def evaluate(part, st: dict, T: float, m: dict | None = None) -> tuple[np.ndarray | None, float, tuple | None]:
    """(local 4x4 or None, extra glow, colour override or None) for one part with a motion (m: one of its motions)."""
    m = m if m is not None else part.motion
    kind = m.get("type")
    run = st.get("spin_on", False)
    theta = float(st.get("spin", 0.0))
    pv = np.asarray(part.pivot, np.float32)
    ax = _axis(m)
    if kind == "spin":
        if m.get("drive") == "lift":
            ang = float(st.get("lift", 0.0)) * float(m.get("ratio", 4.0)) * 2 * math.pi
        elif run:
            ang = theta * float(m.get("speed", 1.0))
        else:
            return None, 0.0, None
        return _about(rot_matrix(*(ax * math.degrees(ang))), pv), 0.0, None
    if kind == "slide":
        if not run:
            return None, 0.0, None
        a = theta * float(m.get("speed", 1.0)) + math.radians(float(m.get("phase", 0.0)))
        amp = float(m.get("amp", 0.2))
        if m.get("len"):
            d = -crank_slider(a, abs(amp), float(m["len"])) * (1 if amp >= 0 else -1)
        else:
            d = amp * (math.cos(a) - 1.0) / 2 * 2  # 0 at the top, -2*amp at the bottom
        return _move(ax * d), 0.0, None
    if kind == "rod":
        if not run:
            return None, 0.0, None
        a = theta + math.radians(float(m.get("phase", 0.0)))
        r, ln = float(m.get("r", 0.05)), float(m.get("len", 0.15))
        # in the plane across the crank axis: "up" is +y; "side" is the other axis (z for a crank along x)
        up = np.array([0.0, 1.0, 0.0])
        side = np.cross(ax, up)
        pin_rest = pv + up * r
        pin = pv + up * (r * math.cos(a)) + side * (r * math.sin(a))
        beta = math.asin(max(-1.0, min(1.0, -r * math.sin(a) / ln)))  # tilt: the rod's top stays on the cylinder line
        rot = rot_matrix(*(ax * math.degrees(beta)))  # rotate around the crank axis (through the pin)
        out = _move(pin - pin_rest) @ _about(rot, pin_rest)
        return out, 0.0, None
    if kind == "valve":
        if not run:
            return None, 0.0, None
        a = theta * float(m.get("speed", 0.5)) + math.radians(float(m.get("phase", 0.0)))
        lift = max(0.0, math.cos(a)) ** 3
        return _move(ax * float(m.get("amp", -0.01)) * lift), 0.0, None
    if kind == "swing":
        deg = float(m.get("deg", 18.0))
        if m.get("drive") == "lift":
            ang = deg * float(st.get("lift", 0.0))
        elif m.get("drive") == "open":
            ang = deg * _open(st, part)
        elif run:
            ang = deg * math.sin(theta * float(m.get("speed", 1.0)) + math.radians(float(m.get("phase", 0.0))))
        else:
            return None, 0.0, None
        return _about(rot_matrix(*(ax * ang)), pv), 0.0, None
    if kind == "pulse":
        if not run:
            return None, 0.0, None
        a = (math.degrees(theta) * float(m.get("speed", 0.5)) + float(m.get("phase", 0.0))) % 360.0
        glow = max(0.0, 1.0 - min(a, 360.0 - a) / 28.0)  # a short flash around the firing point
        return None, 1.6 * glow, ((1.0, 0.85, 0.45) if glow > 0.05 else None)
    if kind == "chamber":
        r, ln = float(m.get("r", 0.05)), float(m.get("len", 0.15))
        top = float(m.get("top", 1.0))
        lo, hi = part.geo.bounds()
        crown_top = float(lo[1])  # modelled at top dead centre: from the piston crown up to the head
        a = theta + math.radians(float(m.get("phase", 0.0))) if run else math.radians(float(m.get("phase", 0.0)))
        drop = crank_slider(a, r, ln)
        h0 = max(top - crown_top, 1e-4)
        k = (h0 + drop) / h0
        sm = np.eye(4, dtype=np.float32)
        sm[1, 1] = k
        sm[1, 3] = top * (1 - k)  # stretched down from the head
        if not run:
            return sm, 0.0, STROKE_COLORS[2]
        c = (math.degrees(theta) * 0.5 + float(m.get("cycle", 0.0))) % 360.0
        stroke = int(c // 90) % 4
        return sm, STROKE_GLOW[stroke], STROKE_COLORS[stroke]
    if kind == "open":
        u = _open(st, part)
        if u <= 1e-4:
            return None, 0.0, None
        if "deg" in m:
            return _about(rot_matrix(*(ax * float(m["deg"]) * u)), pv), 0.0, None
        return _move(ax * float(m.get("amp", 0.5)) * u), 0.0, None
    if kind == "lift":
        u = float(st.get("lift", 0.0))
        amp = float(m.get("amp", 1.0))
        sag = float(st.get("sag", 0.0)) if amp > 0 else 0.0  # a snapped rope: the car drops until the brakes hold
        return (_move(ax * (amp * u - sag)) if (u or sag) else None), 0.0, None
    if kind == "stretch":
        u = float(st.get("lift", 0.0))
        if not u:
            return None, 0.0, None
        lo, hi = part.geo.bounds()
        i = int(np.argmax(np.abs(ax)))
        length = max(float(hi[i] - lo[i]), 1e-4)
        k = max(0.02, (length - float(m.get("amp", 1.0)) * u) / length)
        sm = np.eye(4, dtype=np.float32)
        sm[i, i] = k
        sm[i, 3] = float(pv[i]) * (1 - k)  # the pivot end stays where it is
        return sm, 0.0, None
    if kind == "level":
        f = st.get("fills", {}).get(m.get("of", ""), st.get("fill", 1.0))
        return _move(ax * float(m.get("amp", 0.2)) * (float(f) - 1.0)), 0.0, None
    if kind == "flicker":
        lo, hi = part.geo.bounds()
        f = 1.0 + 0.14 * math.sin(T * 11.0 + float(m.get("phase", 0.0))) + 0.06 * math.sin(T * 23.0)
        sm = np.eye(4, dtype=np.float32)
        sm[1, 1] = f
        sm[1, 3] = float(lo[1]) * (1 - f)
        return sm, 0.0, None
    return None, 0.0, None


def _open(st: dict, part) -> float:
    return float(st.get("opens", {}).get(part.name, st.get("open", 0.0)))
