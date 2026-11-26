"""Machines with their REAL working parts, at real size (meters), for "how it works" videos.

Each machine has an outer shell (cut open in a cutaway, so the inside shows) and moving parts with a `motion`
(see motion.py): an engine's pistons, rods, crankshaft, valves and sparks follow one crank angle; an elevator's
car, counterweight, ropes and pulley follow one lift level. The planner AI sees them in the catalog like any asset.

Add a machine: build it from simple shapes (mesh.py), give moving parts a motion, outer walls shell=True,
named anchors (inlet, outlet, label, inside) and paths for flows. Keep sizes real.
"""

from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .assets import C, asset, col
from .mesh import Model

ALU = "#b4bcc4"  # aluminium
IRON = "#7d6a5c"  # hot cast iron (exhaust)
STEEL = "#8e979f"
DARK = "#4a5058"
RUBBER = "#26292d"


def _x_cyl(r, length, x0, y, z, seg=12):
    """A cylinder lying along x, from x0 to x0 + length."""
    return M.xf(M.cylinder(r, length, seg, base=False), (x0 + length / 2, y, z), (0, 0, 90))


# ---------------------------------------------------------------------------------------------------------------
# Car engine: inline 4-stroke, real size (about 0.6 m long)
# ---------------------------------------------------------------------------------------------------------------

@asset("car_engine", "a real car engine (inline 4-stroke), cut open: block, pistons, connecting rods, crankshaft, "
       "valves, camshafts, spark plugs; the gas in each cylinder changes colour with the stroke (blue air+fuel in, "
       "squeezed, orange explosion, grey exhaust out). spin = it runs. paths: intake, exhaust, fuel. ~0.6 m",
       ["machine", "vehicle", "engine", "cutaway"],
       aliases=["engine", "motor_engine", "combustion_engine", "petrol_engine", "gasoline_engine", "piston_engine",
                "four_stroke_engine", "v8", "car_motor", "cylinder", "pistons", "crankshaft", "spark_plug"])
def car_engine(cylinders=4, color="#c0392b"):
    n = max(1, min(8, int(cylinders)))
    sp, rb = 0.095, 0.04  # cylinder spacing, bore radius
    yc, r, L = 0.20, 0.045, 0.145  # crank centre, crank radius (half the stroke), rod length
    pin_tdc = yc + r + L
    deck, roof = pin_tdc + 0.045, pin_tdc + 0.06  # top of the block, top of the combustion chamber
    half = n * sp / 2 + 0.05
    xs = [(k - (n - 1) / 2) * sp for k in range(n)]
    order = {1: [0], 2: [0, 360], 3: [0, 240, 480], 4: [0, 540, 180, 360], 5: [0, 432, 144, 576, 288],
             6: [0, 600, 240, 480, 120, 360], 8: [0, 630, 270, 180, 540, 450, 90, 360]}
    fire = order.get(n) or [k * 720 / n for k in range(n)]  # crank angle when each cylinder fires
    m = Model()
    # --- the outside (cut away in a cutaway: the inside shows)
    m.add("block", M.xf(M.box(2 * half, deck - 0.12, 0.22), (0, (deck + 0.12) / 2, 0)), ALU, shell=True,
          material="metal")
    m.add("head", M.xf(M.box(2 * half, 0.12, 0.2), (0, deck + 0.06, 0)), "#c3c9cf", shell=True, material="metal")
    m.add("cam_cover", M.xf(M.box(2 * half - 0.02, 0.06, 0.17), (0, deck + 0.15, 0)), col(color, "#c0392b"),
          shell=True, material="plastic")
    m.add("oil_pan", M.xf(M.box(2 * half - 0.04, 0.1, 0.2), (0, 0.07, 0)), "#3b4047", shell=True, material="metal")
    m.add("oil", M.xf(M.box(2 * half - 0.06, 0.03, 0.18), (0, 0.035, 0)), "#5a3a12", kind="liquid", opacity=0.9,
          material="water")
    for x in xs:
        m.add("liner", M.xf(M.cylinder(rb + 0.003, deck - (yc + 0.02), 14, caps=False), (x, yc + 0.02, 0)), "#9aa3ab",
              shell=True, material="metal")
    # --- moving parts (one crank angle drives them all)
    for k, x in enumerate(xs):
        ph = -fire[k] % 360 if n > 1 else 0.0  # piston phase: at the top when it fires (and 360 later)
        ph = (fire[k]) % 360
        piston_phase = -ph
        cyc = (-fire[k] * 0.5) % 360  # where this cylinder is in its 4-stroke cycle
        slide = {"type": "slide", "axis": "y", "amp": r, "len": L, "phase": piston_phase}
        m.add(f"piston{k + 1}", M.xf(M.cylinder(rb - 0.001, 0.06, 14), (x, pin_tdc - 0.02, 0)), "#d3d8dc",
              motion=slide, material="metal")
        m.add(f"rings{k + 1}", M.xf(M.cylinder(rb + 0.0005, 0.012, 14), (x, pin_tdc + 0.022, 0)), "#596068",
              motion=dict(slide), material="metal")
        m.add(f"rod{k + 1}", M.xf(M.box(0.018, L, 0.012), (x, yc + r + L / 2, 0)), "#8a9199",
              motion={"type": "rod", "axis": "x", "r": r, "len": L, "phase": piston_phase}, pivot=(x, yc, 0.0),
              material="metal")
        m.add(f"gas{k + 1}", M.xf(M.cylinder(rb - 0.003, roof - (pin_tdc + 0.04), 14), (x, pin_tdc + 0.04, 0)),
              "#4fb3ff", opacity=0.85,
              motion={"type": "chamber", "r": r, "len": L, "phase": piston_phase, "cycle": cyc, "top": roof})
        m.add(f"spark{k + 1}", M.xf(M.sphere(0.009, 1), (x, roof - 0.004, 0)), "#fff2b0", emissive=0.15,
              motion={"type": "pulse", "speed": 0.5, "phase": cyc})
        for side, z, base_ph in (("intake", -0.03, 135.0), ("exhaust", 0.03, 225.0)):
            stem = M.xf(M.cylinder(0.003, 0.09, 6), (x, roof + 0.0, z))
            head = M.xf(M.cylinder(0.014, 0.004, 10), (x, roof - 0.002, z))
            pair = [M.xf(g, (dx, 0, 0)) for g in (stem, head) for dx in (-0.017, 0.017)]
            m.add(f"{side}_valves{k + 1}", M.merge(*pair), "#b9c0c6" if side == "intake" else "#c49a6c",
                  motion={"type": "valve", "axis": "y", "amp": -0.009, "speed": 0.5, "phase": (base_ph + cyc) % 360},
                  material="metal")
    # crankshaft: journals, webs, pins (one per cylinder, at its own angle), pulley in front, flywheel behind
    crank = [_x_cyl(0.022, 2 * half + 0.02, -half - 0.01, yc, 0.0)]
    for k, x in enumerate(xs):
        a = math.radians(-(fire[k] % 360))
        py, pz = yc + r * math.cos(a), r * math.sin(a)
        crank.append(_x_cyl(0.018, 0.03, x - 0.015, py, pz))
        for dx in (-0.022, 0.022):
            web = M.box(0.012, r + 0.05, 0.05)
            web = M.xf(web, (0, (r + 0.05) / 2 - 0.03, 0))
            crank.append(M.xf(web, (x + dx, yc, 0.0), (math.degrees(a), 0, 0)))
    spin = {"type": "spin", "axis": "x", "speed": 1.0}
    m.add("crankshaft", M.merge(*crank), "#6c747c", motion=spin, pivot=(0.0, yc, 0.0), material="metal")
    m.add("pulley", _x_cyl(0.065, 0.03, -half - 0.05, yc, 0.0, 16), DARK, motion=dict(spin), pivot=(0.0, yc, 0.0),
          material="metal")
    fly = [_x_cyl(0.15, 0.025, half + 0.02, yc, 0.0, 20)]
    for t in range(24):
        aa = 2 * math.pi * t / 24
        fly.append(M.xf(M.box(0.022, 0.02, 0.02), (half + 0.032, yc + 0.152 * math.cos(aa), 0.152 * math.sin(aa)),
                        (math.degrees(aa), 0, 0)))
    m.add("flywheel", M.merge(*fly), "#5b636b", motion=dict(spin), pivot=(0.0, yc, 0.0), material="metal")
    # camshafts (half the crank speed): one lobe per valve pair, pointing down when that valve is open
    cam_y = roof + 0.105
    for side, z, base_ph in (("intake", -0.03, 135.0), ("exhaust", 0.03, 225.0)):
        parts = [_x_cyl(0.009, 2 * half - 0.04, -half + 0.02, cam_y, z, 8)]
        for k, x in enumerate(xs):
            lam = math.radians((base_ph + (-fire[k] * 0.5) % 360) % 360)
            for dx in (-0.017, 0.017):
                lobe = M.xf(M.box(0.012, 0.022, 0.016), (0, -0.01, 0))
                parts.append(M.xf(lobe, (x + dx, cam_y, z), (math.degrees(lam), 0, 0)))
        m.add(f"{side}_cam", M.merge(*parts), "#7a828a",
              motion={"type": "spin", "axis": "x", "speed": 0.5}, pivot=(0.0, cam_y, z), material="metal")
        m.add(f"{side}_cam_pulley", _x_cyl(0.045, 0.02, -half - 0.045, cam_y, z, 16), "#9aa2aa",
              motion={"type": "spin", "axis": "x", "speed": 0.5}, pivot=(0.0, cam_y, z), material="metal")
    # timing belt (front), spark plugs and coils on top, manifolds on the sides
    belt = [(-half - 0.035, yc - 0.068, 0.0), (-half - 0.035, cam_y - 0.02, -0.078), (-half - 0.035, cam_y + 0.047, -0.03),
            (-half - 0.035, cam_y + 0.047, 0.03), (-half - 0.035, cam_y - 0.02, 0.078), (-half - 0.035, yc - 0.068, 0.0)]
    m.add("timing_belt", M.tube(belt, 0.006, 6), RUBBER)
    for x in xs:
        m.add("plug", M.merge(M.xf(M.cylinder(0.007, 0.07, 8), (x, roof, 0)),
                              M.xf(M.cylinder(0.011, 0.03, 6), (x, roof + 0.07, 0))), "#f1efe8")
        m.add("coil", M.xf(M.box(0.03, 0.05, 0.03), (x, deck + 0.21, 0)), "#1f2226", material="plastic")
    plen_z, port_y = -0.22, roof + 0.02
    m.add("intake_plenum", M.xf(M.capsule(0.045, 2 * half - 0.1), (0, port_y + 0.03, plen_z)), "#2c3036",
          material="plastic")
    m.add("throttle", _x_cyl(0.04, 0.06, -half - 0.02, port_y + 0.03, plen_z, 14), "#9aa2aa", material="metal",
          shell=True)
    tc = (-half - 0.02 + 0.03, port_y + 0.03, plen_z)  # the throttle plate: the gas pedal opens it to let in AIR
    m.add("throttle_plate", _x_cyl(0.035, 0.004, tc[0] - 0.002, tc[1], tc[2], 14), "#e0b12a", material="metal",
          motion={"type": "open", "axis": "z", "deg": 70}, pivot=tc)
    runners = []
    for x in xs:
        runners.append(M.tube([(x, port_y + 0.03, plen_z + 0.04), (x, port_y + 0.04, -0.15), (x, port_y, -0.09)],
                              0.018, 8))
        runners.append(M.xf(M.cylinder(0.007, 0.05, 6), (x, port_y + 0.045, -0.13), (35, 0, 0)))  # injector
    m.add("intake_runners", M.merge(*runners), "#2c3036", material="plastic")
    m.add("fuel_rail", _x_cyl(0.008, 2 * half - 0.08, -half + 0.04, port_y + 0.075, -0.14, 8), "#c0392b",
          material="metal")
    exh = []
    for x in xs:
        exh.append(M.tube([(x, port_y - 0.01, 0.09), (x, port_y - 0.02, 0.16), (x * 0.5, 0.25, 0.2)], 0.017, 8))
    exh.append(M.tube([(0, 0.25, 0.2), (0, 0.12, 0.2), (half + 0.1, 0.06, 0.2)], 0.025, 8))
    m.add("exhaust_manifold", M.merge(*exh), IRON, shell=True, material="metal")
    m.add("mounts", M.merge(*[M.xf(M.box(0.06, 0.05, 0.05), (sx * (half - 0.05), 0.2, sz * 0.13))
                              for sx in (-1, 1) for sz in (-1, 1)]), RUBBER)
    x1 = xs[0]
    m.anchors.update({
        "intake": (-half - 0.05, port_y + 0.03, plen_z), "exhaust": (half + 0.1, 0.06, 0.2),
        "label": (0.0, deck + 0.3, 0.0), "inside": (x1, deck - 0.03, 0.0), "spark": (x1, roof, 0.0),
        "piston": (x1, pin_tdc, 0.0), "cylinder": (x1, deck - 0.05, 0.0), "crankshaft": (0.0, yc, 0.0),
        "inlet": (-half - 0.05, port_y + 0.03, plen_z), "outlet": (half + 0.1, 0.06, 0.2),
    })
    m.paths["intake"] = [(-half - 0.08, port_y + 0.03, plen_z), (x1, port_y + 0.03, plen_z), (x1, port_y + 0.04, -0.15),
                         (x1, port_y, -0.09), (x1, roof - 0.01, -0.03)]
    m.paths["exhaust"] = [(x1, roof - 0.01, 0.03), (x1, port_y - 0.01, 0.09), (x1, port_y - 0.02, 0.16),
                          (x1 * 0.5, 0.25, 0.2), (0, 0.12, 0.2), (half + 0.12, 0.06, 0.2)]
    m.paths["fuel"] = [(-half + 0.04, port_y + 0.075, -0.14), (x1, port_y + 0.075, -0.14), (x1, port_y + 0.045, -0.13),
                       (x1, roof - 0.005, -0.04)]
    m.paths["flow"] = m.paths["intake"]
    m.tour = [("piston", "Inside each cylinder, a metal piston slides up and down."),
              ("intake", "First, a valve opens and the piston sucks in air and fuel."),
              ("gas", "Then the piston squeezes that mix into a tiny space."),
              ("spark", "A spark plug sets it on fire, and the blast pushes the piston down."),
              ("exhaust", "Then another valve opens and the burnt gas is pushed out."),
              ("rod", "Rods connect every piston to the crankshaft,"),
              ("crankshaft", "and turn all that pushing into spinning."),
              ("flywheel", "A heavy flywheel keeps it spinning smoothly.")]
    return m


# ---------------------------------------------------------------------------------------------------------------
# A real car (4.5 m), with an engine bay at the front: mount a car_engine at "car1.engine_bay"
# ---------------------------------------------------------------------------------------------------------------

@asset("car", "a real car (4.5 m sedan): body, glass, wheels that roll when it moves, lights; the hood and body are "
       "shells (cut open to see the engine). Put a car_engine inside with \"mount\": \"car1.engine_bay\"",
       ["vehicle", "city"], aliases=["sedan", "automobile", "vehicle", "auto", "hatchback"])
def car(color="#d9534f", length=4.5):
    s = float(length) / 4.5
    c = col(color, C["red"])
    m = Model()
    m.add("floor", M.xf(M.box(4.3, 0.12, 1.66), (0, 0.3, 0)), "#30343a", material="metal")
    for name, x0, x1 in (("front", 0.95, 2.25), ("doors", -1.0, 0.95), ("rear", -2.25, -1.0)):
        w = x1 - x0
        for z in (-0.86, 0.86):
            m.add(f"{name}_side", M.xf(M.box(w, 0.55, 0.06), ((x0 + x1) / 2, 0.62, z)), c, shell=True, material="paint")
    m.add("hood", M.xf(M.box(1.3, 0.06, 1.7), (1.6, 0.92, 0)), c, shell=True, material="paint",
          motion={"type": "open", "axis": "z", "deg": 55}, pivot=(0.95, 0.92, 0.0))
    m.add("bumper_front", M.xf(M.box(0.12, 0.3, 1.72), (2.25, 0.5, 0)), "#2b2f35", shell=True)
    m.add("grille", M.xf(M.box(0.05, 0.16, 1.0), (2.29, 0.7, 0)), "#1d2024", shell=True)
    m.add("trunk", M.xf(M.box(0.9, 0.06, 1.7), (-1.8, 0.92, 0)), c, shell=True, material="paint")
    m.add("bumper_rear", M.xf(M.box(0.12, 0.3, 1.72), (-2.25, 0.5, 0)), "#2b2f35", shell=True)
    cabin = M.extrude([(-1.35, 0.0), (0.95, 0.0), (0.35, 0.5), (-0.95, 0.52)], 1.56)
    m.add("cabin_glass", M.xf(cabin, (0, 0.95, 0)), "#9fd3ea", opacity=0.35, shell=True, material="glass")
    m.add("roof", M.xf(M.box(1.25, 0.05, 1.5), (-0.3, 1.47, 0)), c, shell=True, material="paint")
    for x in (-0.95, 0.95, 0.35):
        for z in (-0.78, 0.78):
            m.add("pillar", M.xf(M.box(0.07, 0.5, 0.06), (x * 0.92 if x != 0.35 else -0.35, 1.2, z)), c, shell=True)
    m.add("seats", M.merge(*[M.xf(M.box(0.5, 0.5, 0.5), (x, 0.6, z)) for x in (-0.1, -1.0) for z in (-0.4, 0.4)]),
          "#3a3f47")
    m.add("dash", M.xf(M.box(0.3, 0.3, 1.5), (0.75, 0.85, 0)), "#25282d")
    m.add("wheel_well", M.xf(M.box(4.0, 0.2, 1.55), (0, 0.3, 0)), "#1b1d21")
    for x in (-1.4, 1.4):
        for z in (-0.78, 0.78):
            m.add("tire", M.xf(M.cylinder(0.33, 0.22, 16, base=False), (x, 0.33, z), (90, 0, 0)), RUBBER, kind="wheel",
                  axis="z", pivot=(x, 0.33, z))
            m.add("rim", M.xf(M.cylinder(0.2, 0.235, 10, base=False), (x, 0.33, z), (90, 0, 0)), "#c7cdd3",
                  kind="wheel", axis="z", pivot=(x, 0.33, z), material="metal")
    m.add("headlights", M.merge(*[M.xf(M.box(0.06, 0.1, 0.32), (2.27, 0.78, z)) for z in (-0.62, 0.62)]), "#fff6d8",
          kind="light", emissive=0.3)
    m.add("taillights", M.merge(*[M.xf(M.box(0.06, 0.1, 0.32), (-2.27, 0.8, z)) for z in (-0.62, 0.62)]), "#d0242b",
          emissive=0.4)
    if s != 1.0:
        for p in m.parts:
            p.geo = M.xf(p.geo, s=s)
            p.pivot = tuple(np.asarray(p.pivot) * s)
    m.anchors.update({"engine_bay": (1.6 * s, 0.36 * s, 0.0), "exhaust": (-2.3 * s, 0.25 * s, 0.5 * s),
                      "label": (0.0, 1.9 * s, 0.0), "inside": (0.0, 0.9 * s, 0.0)})
    return m


# ---------------------------------------------------------------------------------------------------------------
# Elevator: a building cut open, the shaft, the car, counterweight, steel ropes over a traction sheave, motor
# ---------------------------------------------------------------------------------------------------------------

@asset("elevator", "a real elevator in a 4-floor building, cut open: the shaft, the car (cabin) with doors, steel "
       "ropes over a traction sheave driven by a motor in the machine room on top, a counterweight going the other "
       "way, guide rails, safety brakes and buffers. lift (0 = ground floor, 1 = top floor) moves the car; open = "
       "doors open. ~17 m tall", ["machine", "building", "cutaway"],
       aliases=["lift", "elevator_shaft", "elevator_car", "elevator_cabin", "counterweight", "sheave",
                "traction_sheave", "hoist", "skyscraper_elevator"])
def elevator(floors=4, color="#e9eef1"):
    nf = max(2, min(8, int(floors)))
    fh, ground = 3.2, 1.2  # floor height; the lobby floor sits 1.2 m up (the pit is below it)
    top = ground + fh * (nf - 1)  # floor of the top landing
    travel = top - ground
    mr = top + fh + 0.4  # machine room floor
    sheave_y, R, cz = mr + 0.7, 0.475, -0.475
    m = Model()
    # building: back wall, floor slabs with a hole for the shaft, side walls and the front glass (shells)
    W, D = 8.0, 5.6
    m.add("back_wall", M.xf(M.box(W, mr + 2.6, 0.25), (0, (mr + 2.6) / 2, -D / 2)), "#e7e2d8")
    slabs = []
    for k in range(nf + 1):
        y = ground + fh * k if k < nf else mr
        slabs += [M.xf(M.box(W, 0.22, D / 2 - 1.3), (0, y - 0.11, -D / 2 + (D / 2 - 1.3) / 2)),
                  M.xf(M.box(W, 0.22, D / 2 - 1.3), (0, y - 0.11, D / 2 - (D / 2 - 1.3) / 2)),
                  M.xf(M.box(W / 2 - 1.3, 0.22, 2.6), (-W / 4 - 0.65, y - 0.11, 0)),
                  M.xf(M.box(W / 2 - 1.3, 0.22, 2.6), (W / 4 + 0.65, y - 0.11, 0))]
    m.add("floors", M.merge(*slabs), "#cfc8bc", shell=True)
    m.add("roof", M.xf(M.box(W, 0.25, D), (0, mr + 2.6, 0)), "#b9b2a6", shell=True)
    for x in (-W / 2, W / 2):
        m.add("side_wall", M.xf(M.box(0.25, mr + 2.6, D), (x, (mr + 2.6) / 2, 0)), "#ddd6ca", shell=True)
    for k in range(nf):
        y = ground + fh * k
        m.add("front_glass", M.xf(M.box(W, fh - 0.3, 0.06), (0, y + fh / 2, D / 2)), "#a7d8ee", opacity=0.3,
              shell=True, material="glass")
    m.add("pit", M.xf(M.box(2.6, 0.2, 2.6), (0, 0.1, 0)), "#8c8f93")
    # the shaft: concrete walls left, right and back (cut away in front), landing doors on every floor
    m.add("shaft_back", M.xf(M.box(2.6, mr, 0.2), (0, mr / 2, -1.3)), "#c4c8cc")
    for x in (-1.3, 1.3):
        m.add("shaft_side", M.xf(M.box(0.2, mr, 2.6), (x, mr / 2, 0)), "#b3b7bb", shell=True)
    for k in range(nf):
        y = ground + fh * k
        m.add("landing_wall", M.merge(M.xf(M.box(0.75, fh, 0.2), (-0.95, y + fh / 2, 1.3)),
                                       M.xf(M.box(0.75, fh, 0.2), (0.95, y + fh / 2, 1.3)),
                                       M.xf(M.box(1.2, fh - 2.3, 0.2), (0, y + 2.3 + (fh - 2.3) / 2, 1.3))),
              "#b3b7bb", shell=True)
        for side in (-1, 1):
            door = M.xf(M.box(0.6, 2.25, 0.04), (side * 0.3, y + 1.125, 1.42))
            if k == 0:
                m.add("lobby_door", door, "#c7ccd1", material="metal", shell=True,
                      motion={"type": "open", "axis": "x", "amp": side * 0.58})
            else:
                m.add("landing_door", door, "#c7ccd1", material="metal", shell=True)
        m.add("floor_light", M.xf(M.box(0.3, 0.12, 0.05), (0, y + 2.5, 1.43)), "#ffb347", kind="light", emissive=0.4)
    # guide rails for the car and the counterweight
    rails = [M.xf(M.box(0.08, mr - 0.2, 0.12), (x, mr / 2, 0.0)) for x in (-1.05, 1.05)]
    rails += [M.xf(M.box(0.06, mr - 0.2, 0.08), (x, mr / 2, -0.95)) for x in (-0.55, 0.55)]
    m.add("guide_rails", M.merge(*rails), "#6d757d", material="metal")
    m.add("buffers", M.merge(*[M.xf(M.cylinder(0.12, 0.7, 10), (x, 0.2, 0.0)) for x in (-0.4, 0.4)]), "#e0b12a")
    # the car (it rides the lift level up to the top floor)
    lift = {"type": "lift", "axis": "y", "amp": travel}
    car_parts = [
        ("car_floor", M.xf(M.box(1.7, 0.12, 1.5), (0, ground + 0.06, 0)), "#5b636b", "metal"),
        ("car_back", M.xf(M.box(1.7, 2.3, 0.06), (0, ground + 1.27, -0.72)), "#d8b27a", "paint"),
        ("car_walls", M.merge(M.xf(M.box(0.06, 2.3, 1.5), (-0.82, ground + 1.27, 0)),
                              M.xf(M.box(0.06, 2.3, 1.5), (0.82, ground + 1.27, 0))), col(color, "#e9eef1"), "metal"),
        ("car_ceiling", M.xf(M.box(1.7, 0.1, 1.5), (0, ground + 2.47, 0)), "#9aa2aa", "metal"),
        ("car_frame", M.merge(M.xf(M.box(0.1, 3.0, 0.1), (-0.95, ground + 1.4, 0)),
                              M.xf(M.box(0.1, 3.0, 0.1), (0.95, ground + 1.4, 0)),
                              M.xf(M.box(2.0, 0.16, 0.16), (0, ground + 2.85, 0)),
                              M.xf(M.box(2.0, 0.16, 0.16), (0, ground - 0.05, 0))), "#3e454d", "metal"),
        ("safety_brakes", M.merge(*[M.xf(M.box(0.14, 0.22, 0.2), (x, ground + 0.1, 0)) for x in (-1.0, 1.0)]),
         "#e0b12a", "metal"),
        ("handrail", M.xf(M.box(1.5, 0.05, 0.05), (0, ground + 1.0, -0.66)), "#d7dce0", "metal"),
        ("car_panel", M.xf(M.box(0.18, 0.4, 0.03), (0.6, ground + 1.3, 0.7)), "#2b2f35", "metal"),
    ]
    for name, g, c, mat in car_parts:
        m.add(name, g, c, motion=dict(lift), material=mat)
    m.add("car_light", M.xf(M.box(1.2, 0.04, 1.0), (0, ground + 2.41, 0)), "#fff4d6", kind="light", emissive=1.0,
          motion=dict(lift))
    for side in (-1, 1):
        m.add("car_door", M.xf(M.box(0.6, 2.25, 0.04), (side * 0.3, ground + 1.13, 0.74)), "#d3d8dc", material="metal",
              motion=[dict(lift), {"type": "open", "axis": "x", "amp": side * 0.56}])
    m.add("car_buttons", M.merge(*[M.xf(M.box(0.05, 0.05, 0.02), (0.6 + dx, ground + 1.18 + 0.09 * r, 0.72))
                                   for r in range(4) for dx in (-0.04, 0.04)]), "#ffd76b", emissive=0.6,
          motion=dict(lift))
    from .assets import build  # noqa: PLC0415  (a passenger rides inside the car, facing the doors)

    rider = build("person", shirt="#3d8fd6", pants="#3e454d", height=1.75, seed=3)
    s = 1.75 / max(1e-3, float(rider.bounds()[1][1]))
    for p in rider.parts:  # every piece is "passenger_…", so "lift1.passenger" frames the whole person, head included
        g = M.xf(M.Geo(p.geo.pos * s), (-0.35, ground + 0.12, -0.15), (0, -70, 0))  # facing the doors
        m.add(f"passenger_{p.name}", g, p.color, emissive=p.emissive, motion=dict(lift))
    # counterweight: near the top when the car is at the bottom; goes down as the car goes up
    cw_top = sheave_y - 1.0
    cw = [M.xf(M.box(1.0, 0.16, 0.24), (0, cw_top - 0.2 - k * 0.19, -0.95)) for k in range(10)]
    cw += [M.xf(M.box(0.08, 2.2, 0.28), (x, cw_top - 1.1, -0.95)) for x in (-0.52, 0.52)]
    m.add("counterweight", M.merge(*cw), "#e07b39", motion={"type": "lift", "axis": "y", "amp": -travel},
          material="metal")
    # steel ropes: over the sheave, down to the car (shorter as it rises) and to the counterweight (longer)
    car_top = ground + 2.93
    ropes = [M.xf(M.cylinder(0.014, sheave_y - car_top, 6), (dx, car_top, cz + R)) for dx in (-0.12, -0.04, 0.04, 0.12)]
    m.add("ropes", M.merge(*ropes), "#2e3338", motion={"type": "stretch", "axis": "y", "amp": travel},
          pivot=(0.0, sheave_y, 0.0), material="metal")
    ropes = [M.xf(M.cylinder(0.014, sheave_y - cw_top, 6), (dx, cw_top, cz - R)) for dx in (-0.12, -0.04, 0.04, 0.12)]
    m.add("cw_ropes", M.merge(*ropes), "#2e3338", motion={"type": "stretch", "axis": "y", "amp": -travel},
          pivot=(0.0, sheave_y, 0.0), material="metal")
    # machine room: traction sheave (grooved), gearbox, motor, brake; a governor for the safety brakes
    sheave = [_x_cyl(R, 0.36, -0.18, sheave_y, cz, 20)]
    for k in range(5):
        sheave.append(M.xf(M.box(0.38, 0.05, 0.05), (0, sheave_y + (R + 0.01) * math.cos(k * 1.2566),
                                                     cz + (R + 0.01) * math.sin(k * 1.2566)), (k * 72.0, 0, 0)))
    m.add("sheave", M.merge(*sheave), "#8e979f", motion={"type": "spin", "axis": "x", "drive": "lift",
                                                         "ratio": -travel / (2 * math.pi * R)},
          pivot=(0.0, sheave_y, cz), material="metal")
    m.add("motor", _x_cyl(0.42, 1.0, 0.3, sheave_y, cz, 18), "#2f6fb5", material="metal")
    m.add("motor_shaft", _x_cyl(0.06, 1.6, -0.3, sheave_y, cz, 8), "#c7cdd3",
          motion={"type": "spin", "axis": "x", "drive": "lift", "ratio": -12.0}, pivot=(0.0, sheave_y, cz),
          material="metal")
    m.add("brake", _x_cyl(0.3, 0.16, -0.45, sheave_y, cz, 14), "#e0b12a", material="metal")
    m.add("bedplate", M.xf(M.box(2.4, 0.2, 1.2), (0.1, mr + 0.1, cz)), "#4a5058", material="metal")
    m.add("governor", _x_cyl(0.18, 0.06, 1.0, mr + 0.5, 0.35, 14), "#e0b12a",
          motion={"type": "spin", "axis": "x", "drive": "lift", "ratio": -travel / (2 * math.pi * 0.18)},
          pivot=(0.0, mr + 0.5, 0.35), material="metal")
    m.add("governor_rope", M.xf(M.cylinder(0.006, mr + 0.5, 4), (1.03, 0.0, 0.53)), "#2e3338")
    m.add("controller", M.xf(M.box(0.5, 1.4, 0.35), (-1.6, mr + 0.7, -0.7)), "#3b4a5a", material="metal")
    m.add("controller_lights", M.xf(M.box(0.3, 0.2, 0.02), (-1.6, mr + 1.1, -0.52)), "#5dff9a", kind="light",
          emissive=0.8)
    m.anchors.update({"label": (0.0, mr + 3.2, 0.0), "inside": (0.0, ground + 1.3, 0.0), "car": (0.0, ground + 1.3, 0.0),
                      "sheave": (0.0, sheave_y, cz), "motor": (0.8, sheave_y, cz), "counterweight": (0.0, cw_top - 1.0, -0.95),
                      "power": (-1.6, mr + 1.4, -0.7), "top": (0.0, mr + 2.6, 0.0)})
    m.paths["power"] = [(-1.6, mr + 1.4, -0.7), (-1.6, mr + 1.6, cz), (0.3, sheave_y + 0.45, cz), (0.8, sheave_y, cz)]
    m.tour = [("ropes", "The car hangs from strong steel ropes."),
              ("sheave", "On the roof, the ropes run over a grooved wheel called the sheave."),
              ("counterweight", "On the other side hangs a heavy counterweight."),
              ("motor", "A motor turns the sheave,"),
              ("car", "and the car rides up the shaft while the counterweight goes down."),
              ("safety_brakes", "Safety brakes wait right beside the rails."),
              ("governor", "If the car ever goes too fast, the governor trips the brakes."),
              ("car_door", "At the floor, the doors slide open.")]
    return m


# ---------------------------------------------------------------------------------------------------------------
# Numbers as things you can see
# ---------------------------------------------------------------------------------------------------------------

@asset("counter", "a big glowing number display: a label on it with \"from\"/\"to\" counts up (\"{n} kg\", \"{n} times "
       "a day\")", ["symbol", "data"], aliases=["number_display", "scoreboard", "display", "odometer", "meter_display"])
def counter(w=1.6, color="#2ee6d6"):
    w = float(w)
    m = Model().add("stand", M.xf(M.box(0.12, 0.7, 0.12), (0, 0.35, 0)), "#3a4048", material="metal")
    m.add("panel", M.xf(M.box(w, w * 0.45, 0.12), (0, 0.7 + w * 0.225, 0)), "#14202a", material="plastic")
    m.add("screen", M.xf(M.box(w * 0.9, w * 0.36, 0.02), (0, 0.7 + w * 0.225, 0.065)), "#0a3a40", emissive=0.4)
    m.add("frame", M.merge(*[M.xf(M.box(w + 0.04, 0.03, 0.14), (0, y, 0)) for y in (0.7, 0.7 + w * 0.45)]),
          col(color, "#2ee6d6"), emissive=0.9)
    m.anchors["label"] = (0.0, 0.7 + w * 0.225 + 0.08, 0.1)
    return m


@asset("balance_scale", "a balance scale: two pans on a beam; open = it tips to the heavier side (compare two "
       "weights or amounts)", ["symbol", "data"], aliases=["scale", "balance", "weighing_scale", "scales"])
def balance_scale(color="#c9a227"):
    c = col(color, "#c9a227")
    m = Model().add("base", M.cylinder(0.35, 0.08, 16), "#3a4048", material="metal")
    m.add("post", M.xf(M.cylinder(0.04, 1.3, 8), (0, 0.08, 0)), c, material="metal")
    beam = [M.xf(M.box(1.6, 0.05, 0.06), (0, 1.38, 0))]
    for x in (-0.75, 0.75):
        beam += [M.xf(M.cylinder(0.006, 0.45, 4), (x, 0.93, 0)), M.xf(M.cylinder(0.3, 0.04, 16, r_top=0.33), (x, 0.9, 0))]
    m.add("beam", M.merge(*beam), c, material="metal", pivot=(0.0, 1.38, 0.0),
          motion={"type": "swing", "axis": "z", "deg": -14, "drive": "open"})
    m.anchors.update({"left": (-0.75, 1.0, 0.0), "right": (0.75, 1.0, 0.0), "label": (0.0, 1.7, 0.0)})
    return m
