"""Part 14 object designs, written the way the designer prompts ask (no Gemini key in that session):
1) a blueprint of how the real thing is built, 2) a recipe built from it with CAD parts, 3) the sense check and
3-view previews judge it. Run: python docs/test_loop/designs_part14.py [names] → storyforge/world/recipes/<name>.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

RECIPES = Path(__file__).resolve().parents[2] / "storyforge" / "world" / "recipes"
WHITE, STEEL, DARK, CHROME, RUBBER, GLASS = "#eef1f3", "#aeb6bd", "#3d434a", "#cfd6dc", "#26292d", "#bfe9ff"


def P(name, cad=None, **kw):
    d = {"name": name}
    if cad:
        d["cad"] = cad
    d.update(kw)
    return d


def ring_path(c1, r1, c2, r2, z, n=10):
    """A belt around two pulleys (circles in the x/y plane at depth z): points of their convex hull."""
    import numpy as np

    pts = []
    for c, r in ((c1, r1), (c2, r2)):
        for a in np.linspace(0, 2 * math.pi, 24, endpoint=False):
            pts.append((c[0] + (r + 0.004) * math.cos(a), c[1] + (r + 0.004) * math.sin(a)))
    pts = np.array(pts)
    from scipy.spatial import ConvexHull

    h = ConvexHull(pts)
    loop = [list(map(float, (pts[i][0], pts[i][1], z))) for i in h.vertices]
    return loop + [loop[0]]


# ---------------------------------------------------------------------------------------------------------------
def washing_machine():
    cy = 0.45  # drum axis height
    bp = {"what": "A front-loading washing machine: a steel drum full of holes spins inside a sealed plastic tub, turned "
                  "by a belt from a motor under the tub; springs hang the tub from the top, dampers hold it from below.",
          "size_m": [0.6, 0.85, 0.6], "sits_on": "floor", "front": "a round door with a glass window, a detergent "
          "drawer top left, a dial and a small display top right", "casing": "cabinet",
          "parts": [
              {"name": "cabinet", "shape": "white box with rounded edges and a round opening in front", "size_m": [0.6, 0.85, 0.6], "pos": [0, 0.425, 0], "moves": "still", "material": "paint", "importance": "key"},
              {"name": "door", "shape": "a round chrome ring with a domed glass window", "size_m": [0.38, 0.38, 0.06], "pos": [0, cy, 0.32], "faces": "front", "moves": "opens", "connects_to": ["cabinet"]},
              {"name": "tub", "shape": "a sealed plastic cylinder lying on its side", "size_m": [0.5, 0.5, 0.42], "pos": [0, cy, -0.02], "inside": "cabinet", "moves": "still", "connects_to": ["springs", "dampers"]},
              {"name": "drum", "shape": "a stainless steel cylinder full of small holes, open at the front", "size_m": [0.46, 0.46, 0.36], "pos": [0, cy, 0.0], "inside": "tub", "moves": "spins", "axis": "z"},
              {"name": "drum_bearing", "shape": "a ball bearing (6206) in the tub back that the drum shaft turns in", "size_m": [0.062, 0.062, 0.016], "pos": [0, cy, -0.25], "inside": "cabinet", "moves": "still", "connects_to": ["tub_back", "drum_shaft"]},
              {"name": "drum_pulley", "shape": "a big flat pulley on the drum's shaft at the back", "size_m": [0.3, 0.3, 0.025], "pos": [0, cy, -0.27], "inside": "cabinet", "moves": "spins", "axis": "z", "connects_to": ["drum"]},
              {"name": "motor", "shape": "a cylinder bolted under the tub", "size_m": [0.12, 0.12, 0.16], "pos": [0.13, 0.15, -0.19], "inside": "cabinet", "moves": "still", "connects_to": ["tub"]},
              {"name": "motor_pulley", "shape": "a small pulley on the motor's shaft", "size_m": [0.05, 0.05, 0.025], "inside": "cabinet", "moves": "spins", "axis": "z", "connects_to": ["motor"]},
              {"name": "belt", "shape": "a rubber belt from the motor pulley to the drum pulley", "size_m": [0.36, 0.42, 0.01], "inside": "cabinet", "moves": "still"},
              {"name": "springs", "shape": "two coil springs from the cabinet top down to the tub", "size_m": [0.05, 0.12, 0.05], "inside": "cabinet"},
              {"name": "dampers", "shape": "two shock absorbers from the base up to the tub", "size_m": [0.05, 0.2, 0.05], "inside": "cabinet"},
              {"name": "heater", "shape": "a U-shaped heating element in the bottom of the tub", "size_m": [0.08, 0.04, 0.3], "inside": "tub"},
              {"name": "drain_pump", "shape": "a small pump at the bottom front with a filter cap", "size_m": [0.1, 0.1, 0.12], "pos": [0.2, 0.08, 0.17], "inside": "cabinet"},
              {"name": "inlet_valve", "shape": "a plastic valve with two coils at the top back", "size_m": [0.08, 0.06, 0.06], "pos": [0.2, 0.77, -0.25], "inside": "cabinet"},
              {"name": "control_panel", "shape": "a strip with a dial, a display and buttons", "size_m": [0.56, 0.1, 0.02], "faces": "front"},
              {"name": "detergent_drawer", "shape": "a pull-out drawer top left", "size_m": [0.18, 0.07, 0.03], "faces": "front"}],
          "shared_axes": [["drum", "drum_shaft", "drum_pulley"]],
          "visible_details": ["round door with glass", "dial", "display", "detergent drawer", "feet"]}
    belt = ring_path((0.13, 0.15), 0.025, (0.0, cy), 0.15, -0.27)
    parts = [
        P("cabinet", "box", size=[0.6, 0.85, 0.6], pos=[0, 0.425, 0], fillet=0.02, hollow=0.012, color=WHITE,
          material="paint", shell=True, holes=[{"at": [0, cy - 0.425, 0.3], "r": 0.165, "axis": "z", "depth": 0.08}]),
        P("feet", shape="box", size=[0.04, 0.02, 0.04], pos=[0, 0.0, 0]),
        P("control_panel", "box", size=[0.56, 0.1, 0.02], pos=[0, 0.79, 0.305], fillet=0.006, color="#f6f7f8", material="plastic"),
        P("dial", "cylinder", size=[0.035, 0.025], axis="z", pos=[0.19, 0.79, 0.325], chamfer=0.006, color=CHROME, material="metal"),
        P("display", shape="box", size=[0.11, 0.035, 0.006], pos=[0.04, 0.79, 0.318], color="#18323a", emissive=0.4),
        P("buttons", shape="box", size=[0.025, 0.015, 0.008], pos=[-0.04, 0.79, 0.318], color="#c9cfd4"),
        P("detergent_drawer", "box", size=[0.18, 0.07, 0.04], pos=[-0.18, 0.79, 0.3], fillet=0.006, color="#f6f7f8", material="plastic"),
        P("drawer_handle", "box", size=[0.1, 0.012, 0.01], pos=[-0.18, 0.775, 0.322], fillet=0.004, color="#d5dade"),
        P("door", "cylinder", size=[0.19, 0.045], bore=0.135, axis="z", pos=[0, cy, 0.325], fillet=0.01, color=CHROME,
          material="metal", motion={"type": "open", "axis": "y", "deg": -100}, pivot=[-0.19, cy, 0.325]),
        P("door_glass", "revolve", profile=[[0.14, 0.0], [0.13, -0.04], [0.09, -0.08], [0.0, -0.09]], rot=[90, 0, 0],
          pos=[0, cy, 0.335], color=GLASS, opacity=0.35, material="glass", motion={"type": "open", "axis": "y", "deg": -100},
          pivot=[-0.19, cy, 0.325]),
        P("door_handle", "box", size=[0.03, 0.09, 0.025], pos=[0.17, cy, 0.345], fillet=0.008, color="#d5dade",
          motion={"type": "open", "axis": "y", "deg": -100}, pivot=[-0.19, cy, 0.325]),
        P("tub", "cylinder", size=[0.25, 0.42], bore=0.24, axis="z", pos=[0, cy, -0.02], color="#8f979e", material="plastic"),
        P("tub_back", "cylinder", size=[0.25, 0.012], axis="z", pos=[0, cy, -0.236], color="#8f979e", material="plastic"),
        P("bellow", "cylinder", size=[0.2, 0.08], bore=0.17, axis="z", pos=[0, cy, 0.23], color=RUBBER, material="rubber"),
        P("drum", "revolve", profile=[[0.0, -0.18], [0.23, -0.18], [0.23, 0.15], [0.2, 0.18]], hollow=0.004, open="top",
          rot=[90, 0, 0], pos=[0, cy, 0.0], color="#d7dde2", material="metal",
          holes=[{"at": [0, 0.0, 0.23], "r": 0.006, "axis": "z", "grid": [6, 5, 0.05]}],
          motion={"type": "spin", "axis": "z", "speed": 0.8}, pivot=[0, cy, 0]),
        *[P(f"drum_paddle{k + 1}", "box", size=[0.04, 0.04, 0.3], fillet=0.01, color="#c8cfd5", material="metal",
            pos=[0.2 * math.cos(math.radians(90 + 120 * k)), cy + 0.2 * math.sin(math.radians(90 + 120 * k)), 0.0],
            rot=[0, 0, 90 + 120 * k], motion={"type": "spin", "axis": "z", "speed": 0.8}, pivot=[0, cy, 0]) for k in range(3)],
        P("drum_shaft", "cylinder", size=[0.02, 0.1], axis="z", pos=[0, cy, -0.23], color=STEEL, material="metal",
          motion={"type": "spin", "axis": "z", "speed": 0.8}, pivot=[0, cy, 0]),
        P("drum_pulley", "revolve", profile=[[0.02, -0.0125], [0.15, -0.0125], [0.145, 0.0], [0.15, 0.0125], [0.02, 0.0125]],
          rot=[90, 0, 0], pos=[0, cy, -0.27], color="#7d868e", material="metal",
          holes=[{"at": [0, 0, 0.08], "r": 0.03, "axis": "z", "grid": [1, 1, 0]}],
          motion={"type": "spin", "axis": "z", "speed": 0.8}, pivot=[0, cy, -0.27]),
        P("motor", "cylinder", size=[0.06, 0.15], axis="z", pos=[0.13, 0.15, -0.19], fillet=0.01, color="#58606a",
          material="metal"),
        P("drum_bearing", "bearing", od=0.062, pos=[0, cy, -0.25], color=STEEL, material="metal"),  # 6206 in the tub back
        P("motor_bracket", "box", size=[0.05, 0.2, 0.03], pos=[0.13, 0.27, -0.19], fillet=0.004, color=DARK, material="metal"),
        *[P("bracket_bolts", "bolt", d=0.008, length=0.025, pos=[0.13, by, -0.175], rot=[90, 0, 0], color="#b4bcc4",
            material="metal") for by in (0.22, 0.32)],
        P("motor_pulley", "cylinder", size=[0.025, 0.025], axis="z", pos=[0.13, 0.15, -0.27], color=STEEL, material="metal",
          motion={"type": "spin", "axis": "z", "speed": 4.5}, pivot=[0.13, 0.15, -0.27]),
        P("motor_shaft", "cylinder", size=[0.01, 0.06], axis="z", pos=[0.13, 0.15, -0.255], color=STEEL, material="metal",
          motion={"type": "spin", "axis": "z", "speed": 4.5}, pivot=[0.13, 0.15, -0.27]),
        P("belt", shape="tube", points=belt, size=[0.006], color=RUBBER, material="rubber"),
        *[P("springs", shape="spring", size=[0.02, 0.13, 0.004], turns=7, pos=[sx * 0.16, 0.765, -0.02], color=STEEL,
            material="metal") for sx in (-1, 1)],
        *[P("dampers", "cylinder", size=[0.018, 0.22], pos=[sx * 0.16, 0.115, -0.02], color="#4b525a", material="metal")
          for sx in (-1, 1)],
        P("base_plate", "box", size=[0.56, 0.02, 0.56], pos=[0, 0.01, 0], color=DARK, material="metal"),
        P("heater", shape="tube", points=[[-0.04, 0.24, 0.15], [-0.04, 0.24, -0.15], [0.04, 0.24, -0.15], [0.04, 0.24, 0.15]],
          size=[0.007], color="#8c7f73", material="metal", kind="heater"),
        P("water", "cylinder", size=[0.235, 0.36], axis="z", pos=[0, cy, -0.02], color="#3aa6d9", opacity=0.55,
          material="water", kind="liquid"),
        P("drain_pump", "cylinder", size=[0.045, 0.1], axis="z", pos=[0.2, 0.07, 0.17], fillet=0.006, color="#3a4048",
          material="plastic"),
        P("pump_filter_cap", "cylinder", size=[0.03, 0.02], axis="z", pos=[0.2, 0.07, 0.23], color="#d9dde1"),
        P("sump_hose", shape="tube", points=[[0.0, 0.2, -0.02], [0.0, 0.1, 0.05], [0.15, 0.07, 0.1], [0.2, 0.07, 0.12]],
          size=[0.018], color=RUBBER, material="rubber"),
        P("drain_hose", shape="tube", points=[[0.2, 0.07, 0.12], [0.24, 0.07, -0.1], [0.24, 0.4, -0.24], [0.24, 0.55, -0.31]],
          size=[0.015], color="#606870", material="rubber"),
        P("inlet_valve", "box", size=[0.08, 0.05, 0.05], pos=[0.2, 0.77, -0.25], fillet=0.008, color="#2f3540", material="plastic"),
        *[P("inlet_valve_coil", "cylinder", size=[0.014, 0.03], pos=[0.2 + dx, 0.81, -0.25], color="#c27b33", material="metal")
          for dx in (-0.02, 0.02)],
        P("inlet_hose", shape="tube", points=[[0.2, 0.77, -0.25], [0.05, 0.8, -0.1], [-0.18, 0.8, 0.2]], size=[0.012],
          color="#6c757d", material="rubber"),
        P("drawer_chute", shape="tube", points=[[-0.18, 0.76, 0.24], [-0.15, 0.7, 0.2], [-0.05, 0.66, 0.16]], size=[0.02],
          color="#9aa2a9", material="plastic"),
    ]
    for sx in (-1, 1):
        for sz in (-1, 1):
            parts.append(P("feet", "cylinder", size=[0.022, 0.02], pos=[sx * 0.25, 0.01, sz * 0.25], color=RUBBER, material="rubber"))
    parts = [p for p in parts if not (p.get("shape") == "box" and p["name"] == "feet")]
    return {"name": "washing_machine", "about": "a front-loading washing machine (drum, tub, motor, belt, pump, valve)",
            "tags": ["machine", "home", "appliance", "laundry"], "aliases": ["washer", "washing_machines", "laundry_machine"],
            "key_part": "drum", "blueprint": bp, "parts": parts,
            "ports": {"inlet": [0.24, 0.77, -0.31], "outlet": [0.24, 0.55, -0.31], "power": [-0.2, 0.3, -0.31]},
            "paths": {"water": [[0.24, 0.77, -0.31], [0.2, 0.77, -0.25], [0.05, 0.8, -0.1], [-0.18, 0.8, 0.2], [-0.15, 0.7, 0.2],
                                [-0.05, 0.62, 0.14], [0.0, 0.45, 0.05]],
                      "drain": [[0.0, 0.22, 0.0], [0.0, 0.1, 0.05], [0.15, 0.07, 0.1], [0.2, 0.07, 0.15], [0.24, 0.07, -0.1],
                                [0.24, 0.4, -0.24], [0.24, 0.55, -0.31]]},
            "tour": [["inlet_valve", "A valve opens and lets water in through the soap drawer."],
                     ["drum", "The clothes tumble in a steel drum full of small holes."],
                     ["heater", "A heating element warms the water at the bottom of the tub."],
                     ["motor", "A motor under the tub turns the drum with a rubber belt."],
                     ["drain_pump", "A pump pushes the dirty water out through the drain hose."],
                     ["springs", "Springs and dampers hold the heavy tub so it can shake without breaking."]],
            "label": [0, 0.95, 0]}


# ---------------------------------------------------------------------------------------------------------------
def microwave():
    bp = {"what": "A microwave oven: a magnetron makes microwaves that travel down a metal waveguide into a metal box "
                  "(the cavity), where they shake the water in the food; a glass plate turns the food.",
          "size_m": [0.5, 0.3, 0.4], "sits_on": "counter", "front": "a dark door with a window on the left, a panel "
          "with a display and buttons on the right", "casing": "casing",
          "parts": [
              {"name": "casing", "shape": "box with rounded edges, vents on the side", "size_m": [0.5, 0.3, 0.4], "pos": [0, 0.15, 0], "moves": "still"},
              {"name": "cavity", "shape": "a metal box open at the front", "size_m": [0.32, 0.23, 0.34], "pos": [-0.07, 0.15, -0.01], "inside": "casing"},
              {"name": "door", "shape": "a dark panel with a window", "size_m": [0.36, 0.27, 0.03], "faces": "front", "moves": "opens"},
              {"name": "turntable", "shape": "a round glass plate", "size_m": [0.27, 0.01, 0.27], "inside": "cavity", "moves": "spins", "axis": "y"},
              {"name": "magnetron", "shape": "a box with cooling fins and an antenna", "size_m": [0.08, 0.09, 0.08], "pos": [0.18, 0.17, -0.06], "inside": "casing", "connects_to": ["waveguide"]},
              {"name": "waveguide", "shape": "a rectangular metal duct", "size_m": [0.08, 0.05, 0.1], "inside": "casing", "connects_to": ["magnetron", "cavity"]},
              {"name": "transformer", "shape": "a heavy block with copper windings", "size_m": [0.09, 0.08, 0.09], "pos": [0.19, 0.06, -0.12], "inside": "casing"},
              {"name": "cooling_fan", "shape": "a small fan at the back", "size_m": [0.08, 0.08, 0.02], "inside": "casing", "moves": "spins", "axis": "z"},
              {"name": "control_panel", "shape": "a dark strip with a display and buttons", "size_m": [0.12, 0.27, 0.02], "faces": "front"},
              {"name": "food", "shape": "a bowl of soup on the plate", "size_m": [0.12, 0.05, 0.12], "inside": "cavity", "moves": "spins", "axis": "y"}],
          "shared_axes": [["turntable", "turntable_coupler", "food"]],
          "visible_details": ["door window", "display", "buttons", "side vents", "glass plate"]}
    tx = -0.07
    parts = [
        P("chassis", "box", size=[0.48, 0.012, 0.38], pos=[0, 0.006, 0], color="#5b636b", material="metal"),
        P("casing", "box", size=[0.5, 0.3, 0.4], pos=[0, 0.15, 0], fillet=0.012, hollow=0.006, color="#e9ecef",
          material="paint", shell=True, holes=[{"at": [0.25, 0.03, -0.08], "r": 0.0035, "axis": "x", "grid": [6, 5, 0.018]}]),
        P("cavity", "box", size=[0.32, 0.23, 0.34], pos=[tx, 0.15, -0.01], hollow=0.004, open="front", color="#d4d9dd",
          material="metal"),
        P("cavity_rails", "box", size=[0.3, 0.023, 0.03], pos=[tx, 0.024, -0.01], color="#5b636b", material="metal"),
        P("door", "box", size=[0.36, 0.27, 0.03], pos=[-0.065, 0.15, 0.2], fillet=0.008, color="#2b3036", material="plastic",
          windows=[{"at": [0, 0, 0], "size": [0.27, 0.17, 0.1]}], motion={"type": "open", "axis": "y", "deg": -100},
          pivot=[-0.245, 0.15, 0.2]),
        P("door_window", shape="box", size=[0.27, 0.17, 0.004], pos=[-0.065, 0.15, 0.2], color="#1d2328", opacity=0.45,
          material="glass", motion={"type": "open", "axis": "y", "deg": -100}, pivot=[-0.245, 0.15, 0.2]),
        P("door_handle", "box", size=[0.018, 0.2, 0.02], pos=[0.095, 0.15, 0.222], fillet=0.006, color="#c3c9ce",
          material="metal", motion={"type": "open", "axis": "y", "deg": -100}, pivot=[-0.245, 0.15, 0.2]),
        P("control_panel", "box", size=[0.13, 0.27, 0.02], pos=[0.18, 0.15, 0.2], fillet=0.006, color="#33393f", material="plastic"),
        P("display", shape="box", size=[0.09, 0.03, 0.004], pos=[0.18, 0.245, 0.211], color="#1c3d24", emissive=0.6),
        *[P("buttons", "box", size=[0.025, 0.016, 0.006], pos=[0.15 + 0.03 * (k % 3), 0.2 - 0.024 * (k // 3), 0.212],
            fillet=0.003, color="#c9ced3", material="plastic") for k in range(9)],
        P("start_button", "box", size=[0.085, 0.022, 0.006], pos=[0.18, 0.06, 0.212], fillet=0.004, color="#3fae5d", material="plastic"),
        P("turntable", "cylinder", size=[0.135, 0.006], pos=[tx, 0.05, -0.01], chamfer=0.002, color="#cfe8f2", opacity=0.55,
          material="glass", motion={"type": "spin", "axis": "y", "speed": 0.25}, pivot=[tx, 0.05, -0.01]),
        P("roller_ring", shape="torus", size=[0.08, 0.006], pos=[tx, 0.042, -0.01], color="#5b636b", material="plastic",
          motion={"type": "spin", "axis": "y", "speed": 0.25}, pivot=[tx, 0.05, -0.01]),
        P("turntable_coupler", "cylinder", size=[0.012, 0.03], pos=[tx, 0.03, -0.01], color="#e2e2e2", material="plastic",
          motion={"type": "spin", "axis": "y", "speed": 0.25}, pivot=[tx, 0.05, -0.01]),
        P("turntable_motor", "cylinder", size=[0.025, 0.012], pos=[tx, 0.018, -0.01], color="#f1c40f", material="plastic"),
        P("food", "revolve", profile=[[0.0, 0.0], [0.04, 0.0], [0.06, 0.05], [0.055, 0.05], [0.0, 0.01]],
          pos=[tx, 0.053, -0.01], color="#f4f1ea", material="ceramic", motion={"type": "spin", "axis": "y", "speed": 0.25},
          pivot=[tx, 0.05, -0.01]),
        P("food_soup", "cylinder", size=[0.052, 0.006], pos=[tx, 0.095, -0.01], color="#d9822b", material="water",
          motion={"type": "spin", "axis": "y", "speed": 0.25}, pivot=[tx, 0.05, -0.01]),
        P("light", "cylinder", size=[0.015, 0.012], pos=[0.06, 0.268, 0.05], color="#fff2b0", kind="light", emissive=0.2),
        P("magnetron", "box", size=[0.075, 0.075, 0.075], pos=[0.18, 0.17, -0.06], fillet=0.004, color="#9aa2a9", material="metal"),
        *[P("magnetron_fins", shape="box", size=[0.085, 0.003, 0.085], pos=[0.18, 0.13 + 0.012 * k, -0.06], color="#c8cdd2",
            material="metal") for k in range(4)],
        P("magnetron_antenna", "cylinder", size=[0.012, 0.03], axis="x", pos=[0.13, 0.2, -0.06], color="#c8763c", material="metal"),
        P("waveguide", "box", size=[0.07, 0.05, 0.1], pos=[0.1, 0.2, -0.06], hollow=0.003, color="#b7bec4", material="metal"),
        P("magnetron_bracket", "box", size=[0.06, 0.135, 0.05], pos=[0.18, 0.0675, -0.06], fillet=0.003, color="#5b636b",
          material="metal"),
        P("transformer", "box", size=[0.09, 0.075, 0.09], pos=[0.19, 0.05, -0.13], fillet=0.004, color="#4b525a", material="metal"),
        P("transformer_coil", "cylinder", size=[0.032, 0.05], pos=[0.19, 0.105, -0.13], color="#c8763c", material="metal"),
        P("capacitor", "cylinder", size=[0.022, 0.09], axis="z", pos=[0.19, 0.035, 0.07], fillet=0.004, color="#c3c9ce", material="metal"),
        P("cooling_fan", shape="blades", size=[0.04, 0.02, 0.004], count=5, pos=[0.18, 0.17, -0.165], color="#2f3540",
          material="plastic", motion={"type": "spin", "axis": "z", "speed": 3}, pivot=[0.18, 0.17, -0.165]),
        P("fan_frame", "cylinder", size=[0.046, 0.02], bore=0.042, axis="z", pos=[0.18, 0.17, -0.168], color="#2f3540",
          material="plastic"),
        P("fan_bracket", "box", size=[0.012, 0.15, 0.01], pos=[0.18, 0.075, -0.168], color="#5b636b", material="metal"),
        *[P("feet", "cylinder", size=[0.015, 0.01], pos=[sx * 0.21, 0.005, sz * 0.16], color=RUBBER, material="rubber")
          for sx in (-1, 1) for sz in (-1, 1)],
    ]
    return {"name": "microwave", "about": "a microwave oven (magnetron, waveguide, cavity, turntable, transformer)",
            "tags": ["machine", "home", "appliance", "kitchen"], "aliases": ["microwave_oven", "microwaves"],
            "key_part": "magnetron", "blueprint": bp, "parts": parts,
            "ports": {"power": [0.2, 0.05, -0.2]},
            "paths": {"waves": [[0.18, 0.2, -0.06], [0.13, 0.2, -0.06], [0.08, 0.2, -0.06], [0.0, 0.17, -0.02],
                                [tx, 0.1, -0.01]],
                      "heat": [[tx, 0.1, -0.01], [tx, 0.18, -0.01], [tx + 0.03, 0.24, 0.0]]},
            "tour": [["magnetron", "A magnetron turns electricity into invisible microwaves."],
                     ["waveguide", "A metal tube guides the waves into the cooking box."],
                     ["cavity", "The metal walls bounce the waves around inside."],
                     ["food", "The waves shake the water in the food, and that makes heat."],
                     ["turntable", "A glass plate turns, so the food heats evenly."],
                     ["door_window", "A metal mesh in the door window keeps the waves inside."]],
            "label": [0, 0.4, 0]}


# ---------------------------------------------------------------------------------------------------------------
def jet_engine():
    cy = 1.25  # engine axis height on its stand; axis along z, the intake faces the front (+z)
    bp = {"what": "A turbofan jet engine: a big fan at the front pushes most air around the core; the rest is squeezed "
                  "by compressors, burned with fuel in a ring-shaped combustor, and spins turbines that turn the fan "
                  "and compressors through two shafts on one axis.",
          "size_m": [2.0, 2.3, 3.0], "sits_on": "floor", "front": "the round intake with the fan and its spinner",
          "casing": "nacelle",
          "parts": [
              {"name": "nacelle", "shape": "a smooth round cowling, open at both ends", "size_m": [2.0, 2.0, 2.6], "pos": [0, cy, 0.2]},
              {"name": "fan", "shape": "a ring of wide twisted blades", "size_m": [1.64, 1.64, 0.2], "pos": [0, cy, 1.15], "inside": "nacelle", "moves": "spins", "axis": "z", "faces": "front"},
              {"name": "spinner", "shape": "a pointed cone on the fan's hub", "size_m": [0.36, 0.36, 0.35], "pos": [0, cy, 1.35], "moves": "spins", "axis": "z", "faces": "front"},
              {"name": "compressor", "shape": "rows of small blades getting smaller", "size_m": [0.8, 0.8, 0.9], "inside": "core_casing", "moves": "spins", "axis": "z"},
              {"name": "combustor", "shape": "a ring-shaped chamber with fuel nozzles", "size_m": [0.76, 0.76, 0.3], "pos": [0, cy, -0.3], "inside": "core_casing"},
              {"name": "turbine", "shape": "rows of blades behind the combustor", "size_m": [1.0, 1.0, 0.5], "inside": "core_casing", "moves": "spins", "axis": "z"},
              {"name": "core_casing", "shape": "a smooth tube around the core, sticking out behind the fan cowling", "size_m": [1.0, 1.0, 2.3]},
              {"name": "lp_shaft", "shape": "a long thin shaft through the middle", "size_m": [0.1, 0.1, 2.4], "moves": "spins", "axis": "z"},
              {"name": "exhaust_cone", "shape": "a pointed plug at the back", "size_m": [0.5, 0.5, 0.6], "faces": "back"},
              {"name": "stand", "shape": "two cradles on a frame", "size_m": [1.6, 0.4, 2.2], "moves": "still"}],
          "shared_axes": [["fan", "spinner", "compressor", "turbine", "lp_shaft"]],
          "visible_details": ["fan blades", "spinner", "exhaust cone", "pylon", "stand"]}
    spin_lp = {"type": "spin", "axis": "z", "speed": 0.6}
    spin_hp = {"type": "spin", "axis": "z", "speed": 1.0}
    piv = [0, cy, 0]
    parts = [
        P("nacelle", "revolve", profile=[[0.86, 1.45], [0.98, 1.38], [1.0, 1.1], [0.98, 0.3], [0.9, -0.6], [0.86, -0.75],
                                         [0.82, -0.6], [0.84, 0.3], [0.86, 1.2], [0.83, 1.4]], rot=[90, 0, 0], ring=True,
          pos=[0, cy, 0], color="#e9edf0", material="paint", shell=True),
        P("pylon", "extrude", poly=[[-0.9, 0.0], [0.9, 0.0], [0.5, 0.5], [-0.7, 0.5]], size=[0.14], rot=[0, 90, 0],
          pos=[0, cy + 0.98, -0.2], fillet=0.02, color="#d5dbe0", material="paint"),
        P("core_casing", "revolve", profile=[[0.42, 1.0], [0.5, 0.7], [0.5, -0.6], [0.4, -1.1], [0.36, -1.1], [0.46, -0.6],
                                             [0.46, 0.7], [0.38, 1.0]], rot=[90, 0, 0], ring=True, pos=[0, cy, 0],
          color="#8f979e", material="metal", shell=True),
        *[P("struts", "box", size=[0.06, 0.38, 0.12], pos=[0, cy + 0.68, 0.55], rot=[0, 0, 90 * k], color="#9aa2a9",
            material="metal", pivot=piv) for k in range(1)],
        P("struts", "box", size=[0.06, 0.38, 0.12], pos=[0, cy - 0.68, 0.55], color="#9aa2a9", material="metal"),
        P("struts", "box", size=[0.38, 0.06, 0.12], pos=[0.68, cy, 0.55], color="#9aa2a9", material="metal"),
        P("struts", "box", size=[0.38, 0.06, 0.12], pos=[-0.68, cy, 0.55], color="#9aa2a9", material="metal"),
        P("fan", shape="blades", size=[0.82, 0.24, 0.025], count=22, pos=[0, cy, 1.15], color="#7d868e", material="metal",
          motion=spin_lp, pivot=piv),
        P("spinner", "revolve", profile=[[0.18, 0.0], [0.16, 0.12], [0.1, 0.25], [0.0, 0.34]], rot=[90, 0, 0],
          pos=[0, cy, 1.18], color="#dfe4e8", material="metal", motion=spin_lp, pivot=piv),
        *[P("compressor", shape="blades", size=[0.4, 0.1, 0.012], count=30, pos=[0, cy, 0.9 - 0.09 * k], color="#aeb6bd",
            material="metal", motion=spin_lp, pivot=piv) for k in range(3)],
        *[P("hp_compressor", shape="blades", size=[0.36 - 0.012 * k, 0.07, 0.01], count=36, pos=[0, cy, 0.6 - 0.09 * k],
            color="#c3c9ce", material="metal", motion=spin_hp, pivot=piv) for k in range(6)],
        P("combustor", "revolve", profile=[[0.2, 0.0], [0.47, 0.0], [0.47, 0.3], [0.2, 0.3]], ring=True, hollow=0.01, rot=[90, 0, 0],
          pos=[0, cy, -0.45], color="#c06a2b", material="metal"),
        *[P("fuel_nozzles", "cylinder", size=[0.018, 0.14], axis="z", pos=[0.33 * math.cos(a), cy + 0.33 * math.sin(a), -0.1],
            color="#d0b47a", material="metal") for a in [2 * math.pi * k / 10 for k in range(10)]],
        P("flame", "revolve", profile=[[0.23, 0.0], [0.35, 0.0], [0.33, 0.26], [0.25, 0.26]], ring=True, rot=[90, 0, 0],
          pos=[0, cy, -0.43], color="#ff8a2a", emissive=0.8, opacity=0.6, kind="flame"),
        P("hp_turbine", shape="blades", size=[0.37, 0.08, 0.015], count=40, pos=[0, cy, -0.55], color="#b88a52",
          material="metal", motion=spin_hp, pivot=piv),
        *[P("turbine", shape="blades", size=[0.42 + 0.02 * k, 0.07, 0.015], count=44, pos=[0, cy, -0.7 - 0.11 * k],
            color="#a78b6a", material="metal", motion=spin_lp, pivot=piv) for k in range(4)],
        P("lp_shaft", "cylinder", size=[0.05, 2.4], axis="z", pos=[0, cy, 0.05], color="#6c747c", material="metal",
          motion=spin_lp, pivot=piv),
        P("hp_shaft", "cylinder", size=[0.1, 1.2], bore=0.065, axis="z", pos=[0, cy, 0.05], color="#8e979f",
          material="metal", motion=spin_hp, pivot=piv),
        P("exhaust_cone", "revolve", profile=[[0.0, -1.55], [0.12, -1.4], [0.25, -1.15], [0.3, -1.0]], rot=[90, 0, 0],
          pos=[0, cy, 0], color="#7d6a5c", material="metal"),
        P("cone_struts", "box", size=[0.7, 0.03, 0.08], pos=[0, cy, -1.0], color="#7d6a5c", material="metal"),
        P("stand_frame", "box", size=[1.4, 0.1, 2.2], pos=[0, 0.05, 0], fillet=0.02, color="#2f6fb3", material="paint",
          windows=[{"at": [0, 0, 0], "size": [1.1, 0.2, 1.9]}]),
        *[P("stand", "extrude", poly=[[-0.7, 0.0], [0.7, 0.0], [0.7, 0.3], [0.5, 0.3], [0.0, 0.36], [-0.5, 0.3], [-0.7, 0.3]],
            size=[0.14], pos=[0, 0.1, z], color="#2f6fb3", material="paint") for z in (-0.7, 0.6)],
        *[P("stand", "box", size=[0.12, 0.42, 0.14], pos=[sx * 0.45, 0.53, z], color="#2f6fb3", material="paint")
          for sx in (-1, 1) for z in (-0.7, 0.6)],
        *[P("stand_wheels", "cylinder", size=[0.06, 0.05], axis="x", pos=[sx * 0.68, 0.06, sz * 1.0], color=RUBBER,
            material="rubber") for sx in (-1, 1) for sz in (-1, 1)],
    ]
    return {"name": "jet_engine", "about": "a turbofan jet engine on its stand (fan, compressors, combustor, turbines, "
                                           "shafts, nacelle)", "tags": ["machine", "vehicle", "engine", "cutaway"],
            "aliases": ["turbofan", "jet_engines", "aircraft_engine", "turbine_engine"], "key_part": "lp_shaft",
            "blueprint": bp, "parts": parts,
            "ports": {"intake": [0, cy, 1.5], "exhaust": [0, cy, -1.6], "fuel": [0.0, cy + 0.6, -0.1]},
            "paths": {"air": [[0, cy + 0.3, 1.6], [0, cy + 0.32, 1.1], [0, cy + 0.33, 0.6], [0, cy + 0.3, 0.0],
                              [0, cy + 0.29, -0.3], [0, cy + 0.33, -0.7], [0, cy + 0.36, -1.1], [0, cy + 0.2, -1.6]],
                      "bypass": [[0, cy + 0.7, 1.6], [0, cy + 0.68, 1.0], [0, cy + 0.68, 0.0], [0, cy + 0.7, -0.6],
                                 [0, cy + 0.72, -0.9]],
                      "fuel": [[0.0, cy + 0.9, -0.1], [0.0, cy + 0.6, -0.1], [0.0, cy + 0.29, -0.1]]},
            "tour": [["fan", "A giant fan sucks in air at the front."],
                     ["compressor", "Rows of small blades squeeze the air tighter and tighter."],
                     ["combustor", "In the combustor, fuel is sprayed in and burns."],
                     ["turbine", "The hot gas spins the turbine blades."],
                     ["lp_shaft", "A shaft lets the turbine turn the fan at the front."],
                     ["exhaust_cone", "The hot gas blasts out of the back, and pushes the plane forward."]],
            "label": [0, cy + 1.6, 0]}


# ---------------------------------------------------------------------------------------------------------------
def dishwasher():
    bp = {"what": "A dishwasher: water comes in through a valve and collects in a sump at the bottom; a pump pushes "
                  "it up to spinning spray arms that blast the dishes in two racks; a heater warms it; a drain pump "
                  "pumps the dirty water out.", "size_m": [0.6, 0.82, 0.58], "sits_on": "floor",
          "front": "a door that opens downwards with a handle and buttons on its top edge", "casing": "cabinet",
          "parts": [
              {"name": "cabinet", "shape": "a stainless steel box", "size_m": [0.6, 0.82, 0.58], "pos": [0, 0.41, 0]},
              {"name": "door", "shape": "a flat panel hinged at the bottom", "size_m": [0.6, 0.7, 0.05], "faces": "front", "moves": "opens", "axis": "x"},
              {"name": "lower_rack", "shape": "a wire basket with plates", "size_m": [0.5, 0.18, 0.48], "inside": "cabinet"},
              {"name": "upper_rack", "shape": "a wire basket with cups", "size_m": [0.5, 0.14, 0.48], "inside": "cabinet"},
              {"name": "lower_spray_arm", "shape": "a flat arm with nozzles", "size_m": [0.44, 0.03, 0.06], "inside": "cabinet", "moves": "spins", "axis": "y"},
              {"name": "upper_spray_arm", "shape": "a flat arm with nozzles", "size_m": [0.4, 0.03, 0.05], "inside": "cabinet", "moves": "spins", "axis": "y"},
              {"name": "sump", "shape": "a round cup at the bottom with a filter", "size_m": [0.16, 0.08, 0.16], "inside": "cabinet"},
              {"name": "wash_pump", "shape": "a pump with a motor under the sump", "size_m": [0.12, 0.12, 0.16], "inside": "cabinet"},
              {"name": "heater", "shape": "a U-shaped heating element on the floor", "size_m": [0.4, 0.02, 0.3], "inside": "cabinet"},
              {"name": "wash_tube", "shape": "a pipe up the back wall", "size_m": [0.04, 0.5, 0.04], "inside": "cabinet"}],
          "shared_axes": [["lower_spray_arm", "lower_arm_hub"]],
          "visible_details": ["door handle", "buttons", "plates", "cups", "spray arms"]}
    sx_arm = {"type": "spin", "axis": "y", "speed": 0.8}
    parts = [
        P("cabinet", "box", size=[0.6, 0.82, 0.58], pos=[0, 0.41, 0], fillet=0.008, hollow=0.01, open="front",
          color="#c9d0d6", material="metal", shell=True),
        P("door", "box", size=[0.6, 0.72, 0.05], pos=[0, 0.44, 0.315], fillet=0.01, color="#dfe4e8", material="metal",
          shell=True, motion={"type": "open", "axis": "x", "deg": 85}, pivot=[0, 0.08, 0.315]),
        P("control_strip", "box", size=[0.6, 0.07, 0.055], pos=[0, 0.765, 0.315], fillet=0.008, color="#3a4048",
          material="plastic", motion={"type": "open", "axis": "x", "deg": 85}, pivot=[0, 0.08, 0.315]),
        *[P("buttons", "box", size=[0.03, 0.012, 0.01], pos=[0.08 + 0.045 * k, 0.765, 0.345], fillet=0.003, color="#c9ced3",
            motion={"type": "open", "axis": "x", "deg": 85}, pivot=[0, 0.08, 0.315]) for k in range(4)],
        P("door_handle", "sweep", path=[[-0.18, 0.7, 0.34], [-0.18, 0.7, 0.37], [0.18, 0.7, 0.37], [0.18, 0.7, 0.34]],
          r=0.008, bend=0.02, color="#c3c9ce", material="metal", motion={"type": "open", "axis": "x", "deg": 85},
          pivot=[0, 0.08, 0.315]),
        P("detergent_dispenser", "box", size=[0.12, 0.08, 0.03], pos=[0.12, 0.48, 0.275], fillet=0.006, color="#e8ecef",
          material="plastic", motion={"type": "open", "axis": "x", "deg": 85}, pivot=[0, 0.08, 0.315]),
        P("toe_kick", "box", size=[0.6, 0.08, 0.03], pos=[0, 0.04, 0.29], color="#2b3036", material="plastic",
          shell=True),  # the front panel under the door: part of the casing (cut away with it)
        P("sump", "cylinder", size=[0.08, 0.08], pos=[0, 0.06, 0.0], bore=0.07, color="#6c757d", material="plastic"),
        P("filter", "cylinder", size=[0.05, 0.1], pos=[0, 0.07, 0.0], color="#d8dee3", opacity=0.6, material="plastic"),
        P("water", "cylinder", size=[0.07, 0.05], pos=[0, 0.045, 0.0], color="#3aa6d9", opacity=0.6, material="water",
          kind="liquid"),
        P("wash_pump", "cylinder", size=[0.05, 0.12], axis="z", pos=[0, 0.06, -0.14], fillet=0.006, color="#4b525a", material="metal"),
        P("pump_motor", "cylinder", size=[0.045, 0.08], axis="z", pos=[0, 0.06, -0.24], fillet=0.006, color="#58606a", material="metal"),
        P("wash_tube", shape="tube", points=[[0, 0.06, -0.09], [0, 0.06, -0.26], [0, 0.45, -0.26], [0, 0.45, -0.02]],
          size=[0.02], color="#aeb6bd", material="plastic"),
        P("lower_arm_hub", "cylinder", size=[0.025, 0.04], pos=[0, 0.12, 0.0], color="#aeb6bd", material="plastic",
          motion=sx_arm, pivot=[0, 0.12, 0]),
        P("lower_spray_arm", "box", size=[0.44, 0.022, 0.055], pos=[0, 0.145, 0], fillet=0.008, color="#9aa2a9",
          material="plastic", holes=[{"at": [0, 0.011, 0], "r": 0.003, "axis": "y", "grid": [9, 1, 0.045]}],
          motion=sx_arm, pivot=[0, 0.145, 0]),
        P("upper_spray_arm", "box", size=[0.38, 0.02, 0.05], pos=[0, 0.445, -0.02], fillet=0.007, color="#9aa2a9",
          material="plastic", holes=[{"at": [0, 0.01, 0], "r": 0.003, "axis": "y", "grid": [8, 1, 0.042]}],
          motion={"type": "spin", "axis": "y", "speed": 0.9}, pivot=[0, 0.445, -0.02]),
        P("heater", shape="tube", points=[[-0.2, 0.03, 0.15], [-0.2, 0.03, -0.12], [0.2, 0.03, -0.12], [0.2, 0.03, 0.15]],
          size=[0.006], color="#8c7f73", material="metal", kind="heater"),
        P("drain_pump", "cylinder", size=[0.03, 0.06], axis="x", pos=[0.12, 0.04, -0.12], color="#3a4048", material="plastic"),
        P("drain_hose", shape="tube", points=[[0.15, 0.04, -0.12], [0.24, 0.04, -0.2], [0.24, 0.3, -0.3]], size=[0.012],
          color="#606870", material="rubber"),
        P("inlet_valve", "box", size=[0.06, 0.05, 0.05], pos=[-0.22, 0.04, 0.12], fillet=0.006, color="#2f3540", material="plastic"),
        P("inlet_hose", shape="tube", points=[[-0.22, 0.04, 0.12], [-0.22, 0.04, -0.2], [-0.24, 0.2, -0.3]], size=[0.01],
          color="#6c757d", material="rubber"),
    ]
    for name, y, h in (("lower_rack", 0.2, 0.16), ("upper_rack", 0.5, 0.12)):  # wire baskets on rails
        w, d = 0.5, 0.48
        x0, x1, z0, z1 = -w / 2, w / 2, -d / 2, d / 2
        loop = [[x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1], [x0, y, z0]]
        top = [[x0, y + h, z0], [x1, y + h, z0], [x1, y + h, z1], [x0, y + h, z1], [x0, y + h, z0]]
        parts.append(P(name, shape="tube", points=loop, size=[0.004], color="#b9c1c7", material="metal"))
        parts.append(P(name, shape="tube", points=top, size=[0.004], color="#b9c1c7", material="metal"))
        for (xx, zz) in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
            parts.append(P(name, shape="tube", points=[[xx, y, zz], [xx, y + h, zz]], size=[0.004], color="#b9c1c7", material="metal"))
        for k in range(7):
            parts.append(P(name, shape="tube", points=[[x0 + w * (k + 1) / 8, y, z0], [x0 + w * (k + 1) / 8, y, z1]],
                           size=[0.003], color="#b9c1c7", material="metal"))
        parts.append(P(name + "_rails", "box", size=[0.02, 0.02, 0.5], pos=[x0 - 0.01, y, 0], color="#8e979f", material="metal"))
        parts.append(P(name + "_rails", "box", size=[0.02, 0.02, 0.5], pos=[x1 + 0.01, y, 0], color="#8e979f", material="metal"))
        parts.append(P(name + "_rails", "box", size=[0.02, 0.02, 0.5], pos=[x0 - 0.025, y, 0], color="#8e979f", material="metal"))
    for k in range(6):  # plates standing in the lower rack
        parts.append(P("plates", "cylinder", size=[0.11, 0.012], axis="z", pos=[0.0, 0.31, -0.18 + 0.07 * k], chamfer=0.004,
                       color="#f4f1ea", material="ceramic"))
    for k in range(4):  # cups upside down in the upper rack
        parts.append(P("cups", "revolve", profile=[[0.0, 0.0], [0.035, 0.0], [0.04, 0.09], [0.034, 0.09], [0.03, 0.005], [0.0, 0.005]],
                       pos=[-0.15 + 0.1 * k, 0.594, 0.05], rot=[180, 0, 0], color="#7fb7d6", material="ceramic"))
    parts.append(P("cabinet_rails", "box", size=[0.02, 0.02, 0.5], pos=[0.27, 0.2, 0], color="#8e979f", material="metal"))
    return {"name": "dishwasher", "about": "a dishwasher (racks, spray arms, sump, wash pump, heater, drain pump)",
            "tags": ["machine", "home", "appliance", "kitchen"], "aliases": ["dish_washer", "dishwashers"],
            "key_part": "sump", "blueprint": bp, "parts": parts,
            "ports": {"inlet": [-0.24, 0.2, -0.3], "outlet": [0.24, 0.3, -0.3], "power": [0.2, 0.1, -0.29]},
            "paths": {"water": [[-0.24, 0.2, -0.3], [-0.22, 0.04, -0.2], [-0.22, 0.04, 0.12], [-0.05, 0.06, 0.05], [0, 0.06, 0]],
                      "spray": [[0, 0.06, 0.0], [0, 0.06, -0.14], [0, 0.06, -0.26], [0, 0.45, -0.26], [0, 0.45, -0.02],
                                [0.15, 0.36, 0.05], [0.1, 0.2, 0.1], [0, 0.07, 0.02]],
                      "drain": [[0, 0.05, 0], [0.12, 0.04, -0.12], [0.24, 0.04, -0.2], [0.24, 0.3, -0.3]]},
            "tour": [["inlet_valve", "A valve lets clean water in, and it collects in a sump at the bottom."],
                     ["heater", "A heating element warms the water."],
                     ["wash_pump", "A pump pushes the water up into the spray arms."],
                     ["lower_spray_arm", "The water jets spin the arms, blasting every plate."],
                     ["filter", "A filter catches the food scraps."],
                     ["drain_pump", "A second pump pushes the dirty water out."]],
            "label": [0, 1.0, 0]}


# ---------------------------------------------------------------------------------------------------------------
# Part 14 test: 5 tricky objects the library didn't have (shape, orientation, assembly)
def bicycle():
    ra, fa, bb, z = (-0.5, 0.34), (0.52, 0.34), (-0.05, 0.28), 0.0
    bp = {"what": "A bicycle: a diamond frame of tubes, two wheels with spokes, pedals on cranks turn a chainring that "
                  "pulls a chain around a small cog on the rear wheel.", "size_m": [1.75, 1.0, 0.6], "sits_on": "floor",
          "front": "the side of the bike (it rolls to the right, +x)",
          "parts": [{"name": "frame", "shape": "tubes in a diamond", "size_m": [0.95, 0.55, 0.12]},
                    {"name": "front_wheel", "shape": "a thin tyre on a rim with spokes", "size_m": [0.68, 0.68, 0.05], "moves": "spins", "axis": "z", "faces": "right"},
                    {"name": "rear_wheel", "shape": "a thin tyre on a rim with spokes", "size_m": [0.68, 0.68, 0.05], "moves": "spins", "axis": "z", "faces": "left"},
                    {"name": "chainring", "shape": "a big toothed ring at the pedals", "size_m": [0.18, 0.18, 0.004], "moves": "spins", "axis": "z"},
                    {"name": "rear_cog", "shape": "a small toothed ring on the rear hub", "size_m": [0.075, 0.075, 0.004], "moves": "spins", "axis": "z"},
                    {"name": "chain", "shape": "a loop of links around the chainring and the cog", "size_m": [0.58, 0.19, 0.01]},
                    {"name": "cranks", "shape": "two arms, one on each side, to the pedals", "size_m": [0.03, 0.17, 0.012], "moves": "spins", "axis": "z"},
                    {"name": "handlebar", "shape": "a bar across the top front", "size_m": [0.06, 0.06, 0.46], "faces": "top"},
                    {"name": "saddle", "shape": "a narrow seat", "size_m": [0.27, 0.06, 0.15], "faces": "top"}],
          "shared_axes": [["front_wheel_hub", "front_wheel_rim"], ["rear_wheel_hub", "rear_wheel_rim", "rear_cog"],
                          ["chainring", "cranks"]],
          "visible_details": ["spokes", "chain", "pedals", "handlebar grips", "saddle"]}
    frame_c, metal = "#d64545", "#aeb6bd"

    def tube(name, a, b, r=0.016, col=frame_c, **kw):
        return P(name, shape="tube", points=[list(a), list(b)], size=[r], color=col, material="paint", **kw)

    st_top, ht_top, ht_bot = (-0.19, 0.76, 0), (0.4, 0.77, 0), (0.44, 0.62, 0)
    parts = [tube("frame", (bb[0], bb[1], 0), st_top), tube("frame", st_top, ht_top), tube("frame", (bb[0], bb[1], 0), ht_bot),
             tube("frame", ht_top, ht_bot, 0.02)]
    for sz in (-0.06, 0.06):
        parts += [tube("frame", (bb[0], bb[1], sz * 0.6), (ra[0], ra[1], sz * 1.1), 0.011),
                  tube("frame", (st_top[0], st_top[1] - 0.02, sz * 0.3), (ra[0], ra[1], sz * 1.1), 0.01),
                  tube("fork", (ht_bot[0], ht_bot[1], sz * 0.5), (fa[0], fa[1], sz * 1.0), 0.012, metal)]
    parts += [tube("seat_post", st_top, (-0.23, 0.9, 0), 0.012, metal), tube("stem", ht_top, (0.38, 0.92, 0), 0.014, metal),
              P("handlebar", "cylinder", size=[0.012, 0.46], axis="z", pos=[0.38, 0.93, 0], color=metal, material="metal"),
              *[P("grips", "cylinder", size=[0.017, 0.1], axis="z", pos=[0.38, 0.93, sz * 0.19], color=RUBBER, material="rubber")
                for sz in (-1, 1)],
              P("saddle", "loft", sections=[{"y": 0.0, "size": [0.26, 0.14], "round": 0.05}, {"y": 0.05, "size": [0.24, 0.1], "round": 0.04}],
                pos=[-0.24, 0.9, 0], color="#2b2f35", material="rubber"),
              P("bottom_bracket", "cylinder", size=[0.022, 0.08], axis="z", pos=[bb[0], bb[1], 0], color=metal, material="metal")]
    for wname, (cx, cy) in (("front_wheel", fa), ("rear_wheel", ra)):
        spin = {"type": "spin", "axis": "z", "speed": 0.7}
        parts += [P(f"{wname}_tire", shape="torus", size=[0.32, 0.02], rot=[90, 0, 0], pos=[cx, cy, z], color=RUBBER,
                    material="rubber", kind="wheel", axis="z", pivot=[cx, cy, z]),
                  P(f"{wname}_rim", shape="torus", size=[0.3, 0.012], rot=[90, 0, 0], pos=[cx, cy, z], color=metal,
                    material="metal", motion=spin, pivot=[cx, cy, z]),
                  P(f"{wname}_hub", "cylinder", size=[0.022, 0.12], axis="z", pos=[cx, cy, z], color=metal, material="metal",
                    motion=spin, pivot=[cx, cy, z])]
        for k in range(16):
            a = 2 * math.pi * k / 16
            side = 0.04 if k % 2 else -0.04
            parts.append(P(f"{wname}_spokes", shape="tube", points=[[cx, cy, side], [cx + 0.29 * math.cos(a), cy + 0.29 * math.sin(a), 0]],
                           size=[0.0016], color="#c8cdd2", material="metal", motion=spin, pivot=[cx, cy, z]))
    crank = {"type": "spin", "axis": "z", "speed": 0.4}
    parts += [P("chainring", "sprocket", teeth=44, pitch=0.0127, thickness=0.004, pos=[bb[0], bb[1], 0.07], color="#3d434a",
                material="metal", motion=crank, pivot=[bb[0], bb[1], 0.07]),
              P("rear_cog", "sprocket", teeth=18, pitch=0.0127, thickness=0.004, pos=[ra[0], ra[1], 0.07], color="#3d434a",
                material="metal", motion={"type": "spin", "axis": "z", "speed": 0.7}, pivot=[ra[0], ra[1], 0.07]),
              P("chain", shape="tube", points=ring_path(bb, 0.089, ra, 0.037, 0.07), size=[0.004], color="#5b636b", material="metal"),
              P("cranks", "box", size=[0.03, 0.17, 0.012], pos=[bb[0], bb[1] - 0.085, 0.09], fillet=0.005, color=metal,
                material="metal", motion=crank, pivot=[bb[0], bb[1], 0.09]),
              P("cranks", "box", size=[0.03, 0.17, 0.012], pos=[bb[0], bb[1] + 0.085, -0.09], fillet=0.005, color=metal,
                material="metal", motion=crank, pivot=[bb[0], bb[1], -0.09]),
              P("pedals", "box", size=[0.08, 0.02, 0.09], pos=[bb[0], bb[1] - 0.17, 0.14], fillet=0.005, color="#2b2f35",
                material="plastic", motion=crank, pivot=[bb[0], bb[1], 0.14]),
              P("pedals", "box", size=[0.08, 0.02, 0.09], pos=[bb[0], bb[1] + 0.17, -0.14], fillet=0.005, color="#2b2f35",
                material="plastic", motion=crank, pivot=[bb[0], bb[1], -0.14]),
              P("brakes", "box", size=[0.03, 0.06, 0.07], pos=[0.47, 0.67, 0], fillet=0.006, color="#2b2f35", material="metal"),
              P("brakes", "box", size=[0.03, 0.06, 0.07], pos=[-0.43, 0.63, 0], fillet=0.006, color="#2b2f35", material="metal")]
    return {"name": "bicycle", "about": "a bicycle (frame, wheels with spokes, chainring, chain, rear cog, cranks, pedals)",
            "tags": ["vehicle", "machine", "city", "transport"], "aliases": ["bike", "bicycles", "push_bike"],
            "key_part": "chainring", "blueprint": bp, "parts": parts,
            "paths": {"chain": ring_path(bb, 0.089, ra, 0.037, 0.075)},
            "tour": [["pedals", "Your feet push the pedals around."], ["chainring", "The cranks turn a big toothed ring."],
                     ["chain", "A chain carries that turn back to the rear wheel."],
                     ["rear_cog", "A small cog on the rear wheel turns faster than the big ring."],
                     ["rear_wheel", "So one turn of the pedals spins the wheel more than twice."]],
            "label": [0, 1.15, 0]}


def toaster():
    bp = {"what": "A pop-up toaster: bread drops into two slots between glowing heating wires; a lever pushes the "
                  "carriage down, a timer lets it spring back up.", "size_m": [0.28, 0.2, 0.16], "sits_on": "counter",
          "front": "its long side, with the slots on top", "casing": "body",
          "parts": [{"name": "body", "shape": "a shiny box with rounded edges and two slots on top", "size_m": [0.28, 0.19, 0.16]},
                    {"name": "bread", "shape": "two slices standing in the slots", "size_m": [0.12, 0.12, 0.015], "faces": "top", "moves": "slides"},
                    {"name": "heating_elements", "shape": "thin panels with wires along the slots", "size_m": [0.2, 0.1, 0.004], "inside": "body"},
                    {"name": "lever", "shape": "a small handle on the end that slides down", "size_m": [0.04, 0.02, 0.05], "faces": "right", "moves": "slides"},
                    {"name": "browning_knob", "shape": "a round knob on the end", "size_m": [0.03, 0.03, 0.02], "faces": "right"},
                    {"name": "crumb_tray", "shape": "a flat tray in the base", "size_m": [0.24, 0.01, 0.12]}],
          "visible_details": ["two slots", "lever", "knob", "shiny body", "feet"]}
    down = {"type": "open", "axis": "y", "amp": -0.05}
    parts = [P("base", "box", size=[0.29, 0.02, 0.17], pos=[0, 0.01, 0], fillet=0.006, color="#2b2f35", material="plastic"),
             P("body", "box", size=[0.28, 0.19, 0.16], pos=[0, 0.115, 0], fillet=0.03, hollow=0.003, color="#d9dee2",
               material="metal", shell=True,
               windows=[{"at": [0, 0.095, 0.034], "size": [0.2, 0.05, 0.024]}, {"at": [0, 0.095, -0.034], "size": [0.2, 0.05, 0.024]}]),
             P("crumb_tray", "box", size=[0.24, 0.008, 0.12], pos=[0, 0.024, 0], color="#8e979f", material="metal"),
             *[P("bread", "box", size=[0.12, 0.11, 0.014], pos=[0, 0.17, sz * 0.034], fillet=0.01, color="#d8a05a",
                 material="plastic", motion=down) for sz in (-1, 1)],
             *[P("heating_elements", shape="box", size=[0.2, 0.11, 0.003], pos=[0, 0.11, zz], color="#8a6a4a", kind="heater")
               for zz in (-0.058, 0.0, 0.058)],
             P("carriage", "box", size=[0.2, 0.01, 0.1], pos=[0, 0.11, 0], color="#8e979f", material="metal", motion=down),
             P("lever_slot", "box", size=[0.006, 0.12, 0.012], pos=[0.142, 0.12, 0], color="#2b2f35"),
             P("lever", "box", size=[0.035, 0.018, 0.045], pos=[0.155, 0.165, 0], fillet=0.006, color="#2b2f35",
               material="plastic", motion=down),
             P("browning_knob", "cylinder", size=[0.015, 0.016], axis="x", pos=[0.146, 0.07, 0.04], chamfer=0.003,
               color="#2b2f35", material="plastic"),
             P("cancel_button", "box", size=[0.01, 0.012, 0.02], pos=[0.144, 0.07, -0.04], fillet=0.003, color="#c0392b"),
             P("cord", shape="tube", points=[[-0.1, 0.03, -0.078], [-0.13, 0.01, -0.085], [-0.16, 0.006, -0.09]], size=[0.004],
               color="#2b2f35", material="rubber"),
             *[P("feet", "cylinder", size=[0.01, 0.006], pos=[sx * 0.12, 0.003, sz * 0.06], color=RUBBER, material="rubber")
               for sx in (-1, 1) for sz in (-1, 1)]]
    return {"name": "toaster", "about": "a pop-up toaster (two slots, heating elements, lever, carriage, knob)",
            "tags": ["home", "appliance", "kitchen", "machine"], "aliases": ["toasters", "bread_toaster"],
            "key_part": "heating_elements", "blueprint": bp, "parts": parts, "ports": {"power": [-0.16, 0.006, -0.09]},
            "paths": {"heat": [[0, 0.06, 0.0], [0, 0.12, 0.02], [0, 0.18, 0.034]]},
            "tour": [["lever", "Pushing the lever lowers the bread and switches the heat on."],
                     ["heating_elements", "Thin wires glow red hot on both sides of the bread."],
                     ["bread", "The heat browns the outside of the bread."],
                     ["browning_knob", "A timer, set by the knob, lets the bread spring back up."]],
            "label": [0, 0.35, 0]}


def ceiling_fan():
    bp = {"what": "A ceiling fan: it hangs from the ceiling on a short rod; an electric motor in a round housing spins "
                  "five tilted blades that push air down; a light sits under the motor.", "size_m": [1.36, 0.5, 1.36],
          "sits_on": "ceiling", "front": "seen from below and the side",
          "parts": [{"name": "canopy", "shape": "a small cup on the ceiling", "size_m": [0.14, 0.07, 0.14], "faces": "top"},
                    {"name": "downrod", "shape": "a short rod", "size_m": [0.03, 0.14, 0.03]},
                    {"name": "motor_housing", "shape": "a round housing", "size_m": [0.26, 0.11, 0.26]},
                    {"name": "blades", "shape": "five long flat tilted blades", "size_m": [1.36, 0.03, 1.36], "moves": "spins", "axis": "y"},
                    {"name": "light_kit", "shape": "a glass bowl under the motor", "size_m": [0.2, 0.12, 0.2], "faces": "bottom"}],
          "shared_axes": [["blades", "rotor", "motor_housing", "downrod", "light_kit"]],
          "visible_details": ["five blades", "glass light bowl", "pull chain", "canopy"]}
    spin = {"type": "spin", "axis": "y", "speed": 0.8}
    parts = [P("canopy", "revolve", profile=[[0.03, 0.0], [0.065, 0.02], [0.07, 0.07], [0.0, 0.07]], pos=[0, 0.43, 0],
               color="#f1efe8", material="paint"),
             P("downrod", "cylinder", size=[0.012, 0.15], pos=[0, 0.36, 0], color="#d6d1c4", material="metal"),
             P("motor_housing", "revolve", profile=[[0.06, 0.11], [0.12, 0.09], [0.13, 0.05], [0.12, 0.0], [0.05, 0.0]],
               pos=[0, 0.2, 0], color="#f1efe8", material="paint"),
             P("rotor", "cylinder", size=[0.12, 0.025], pos=[0, 0.195, 0], color="#d6d1c4", material="metal",
               motion=spin, pivot=[0, 0.2, 0])]
    for k in range(5):
        a = 2 * math.pi * k / 5
        c, s_ = math.cos(a), math.sin(a)
        parts.append(P("blade_irons", shape="tube", points=[[0.11 * c, 0.19, 0.11 * s_], [0.2 * c, 0.2, 0.2 * s_]],
                       size=[0.008], color="#d6d1c4", material="metal", motion=spin, pivot=[0, 0.2, 0]))
        parts.append(P("blades", "box", size=[0.5, 0.008, 0.13], fillet=0.003, pos=[0.43 * c, 0.2, 0.43 * s_],
                       rot=[12, -math.degrees(a), 0], color="#9b6b43", material="paint", motion=spin, pivot=[0, 0.2, 0]))
    parts += [P("switch_housing", "cylinder", size=[0.06, 0.06], pos=[0, 0.17, 0], fillet=0.01, color="#f1efe8", material="paint"),
              P("light_kit", "revolve", profile=[[0.0, 0.0], [0.07, 0.01], [0.1, 0.06], [0.09, 0.12], [0.0, 0.12]],
                pos=[0, 0.02, 0], color="#fff4d6", opacity=0.6, material="glass"),
              P("bulb", shape="sphere", size=[0.03], pos=[0, 0.08, 0], color="#fff2b0", kind="light", emissive=0.3),
              P("pull_chain", shape="tube", points=[[0.03, 0.14, 0.0], [0.03, 0.0, 0.0]], size=[0.0015], color="#c9a85a",
                material="metal"),
              P("pull_bead", shape="sphere", size=[0.006], pos=[0.03, 0.0, 0.0], color="#c9a85a", material="metal")]
    return {"name": "ceiling_fan", "about": "a ceiling fan (canopy, downrod, motor housing, five blades, light kit)",
            "tags": ["home", "appliance", "machine"], "aliases": ["ceiling_fans", "ceilingfan"], "key_part": "motor_housing",
            "blueprint": bp, "parts": parts, "paths": {"air": [[0.5, 0.25, 0], [0.5, 0.0, 0], [0.4, -0.5, 0], [0.2, -1.2, 0]]},
            "tour": [["motor_housing", "An electric motor hides in the round housing."],
                     ["blades", "It spins five tilted blades."],
                     ["blades", "The tilt pushes air down and cools you by moving air over your skin."]],
            "label": [0, 0.7, 0]}


def cordless_drill():
    ay, az = 0.22, 0.0  # the drill's axis: along +x (the chuck works to the right)
    bp = {"what": "A cordless drill: a battery at the bottom powers a motor in the barrel; a planetary gearbox slows it "
                  "and makes it stronger; a clutch collar and a chuck hold the drill bit, all on one axis.",
          "size_m": [0.3, 0.26, 0.09], "sits_on": "table", "front": "the side: the bit points right (+x)",
          "casing": "barrel",
          "parts": [{"name": "battery", "shape": "a rounded block at the bottom", "size_m": [0.11, 0.07, 0.08], "faces": "bottom"},
                    {"name": "handle", "shape": "a grip leaning slightly back", "size_m": [0.05, 0.13, 0.05]},
                    {"name": "barrel", "shape": "a rounded tube on top", "size_m": [0.15, 0.07, 0.07], "faces": "top"},
                    {"name": "motor", "shape": "a small electric motor", "size_m": [0.06, 0.05, 0.05], "inside": "barrel", "moves": "spins", "axis": "x"},
                    {"name": "gearbox", "shape": "small gears in a ring", "size_m": [0.04, 0.05, 0.05], "inside": "barrel", "moves": "spins", "axis": "x"},
                    {"name": "chuck", "shape": "a rounded cone with jaws", "size_m": [0.055, 0.045, 0.045], "faces": "right", "moves": "spins", "axis": "x"},
                    {"name": "bit", "shape": "a long thin steel rod", "size_m": [0.09, 0.008, 0.008], "faces": "right", "moves": "spins", "axis": "x"},
                    {"name": "trigger", "shape": "a small button under the barrel", "size_m": [0.02, 0.03, 0.015]}],
          "shared_axes": [["motor", "gearbox", "chuck", "bit"]],
          "visible_details": ["trigger", "battery", "chuck", "clutch numbers", "vents"]}
    spin = {"type": "spin", "axis": "x", "speed": 3}
    piv = [0, ay, az]
    parts = [P("battery", "box", size=[0.11, 0.07, 0.085], pos=[0.0, 0.035, 0], fillet=0.012, color="#2b2f35", material="plastic"),
             P("battery_latch", "box", size=[0.03, 0.012, 0.05], pos=[0.05, 0.072, 0], fillet=0.004, color="#e8731c"),
             P("handle", "box", size=[0.045, 0.13, 0.05], pos=[0.005, 0.135, 0], rot=[0, 0, -8], fillet=0.015,
               color="#e8731c", material="plastic"),
             P("barrel", "cylinder", size=[0.036, 0.15], axis="x", pos=[0.0, ay, az], fillet=0.012, color="#e8731c",
               material="plastic", shell=True, holes=[{"at": [-0.055, 0.0, 0.03], "r": 0.003, "axis": "z", "grid": [4, 2, 0.01]}]),
             P("motor", "cylinder", size=[0.024, 0.06], axis="x", pos=[-0.035, ay, az], color="#8e979f", material="metal",
               motion=spin, pivot=piv),
             P("motor_shaft", "cylinder", size=[0.004, 0.05], axis="x", pos=[0.01, ay, az], color=STEEL, material="metal",
               motion=spin, pivot=piv),
             *[P("gearbox", "gear", module=0.0012, teeth=24, thickness=0.008, rot=[0, 90, 0], pos=[0.03 + 0.012 * k, ay, az],
                 color="#c3c9ce", material="metal", motion={"type": "spin", "axis": "x", "speed": 1.0}, pivot=piv) for k in range(2)],
             P("clutch_collar", "cylinder", size=[0.038, 0.02], axis="x", pos=[0.085, ay, az], chamfer=0.003, color="#2b2f35",
               material="plastic"),
             P("chuck", "revolve", profile=[[0.0, 0.0], [0.023, 0.0], [0.023, 0.035], [0.013, 0.055], [0.0, 0.055]],
               rot=[0, 0, -90], pos=[0.095, ay, az], color="#3d434a", material="metal",
               motion={"type": "spin", "axis": "x", "speed": 1.0}, pivot=piv),
             P("bit", "cylinder", size=[0.004, 0.09], axis="x", pos=[0.195, ay, az], color="#c8cdd2", material="metal",
               motion={"type": "spin", "axis": "x", "speed": 1.0}, pivot=piv),
             P("trigger", "box", size=[0.016, 0.03, 0.014], pos=[0.035, 0.17, 0], fillet=0.004, color="#2b2f35", material="plastic"),
             P("direction_switch", "cylinder", size=[0.006, 0.06], axis="z", pos=[0.02, 0.19, 0], color="#2b2f35"),
             P("led_light", "box", size=[0.008, 0.008, 0.01], pos=[0.05, 0.08, 0], color="#fff2b0", kind="light", emissive=0.3)]
    return {"name": "cordless_drill", "about": "a cordless power drill (battery, motor, planetary gearbox, clutch, chuck, bit)",
            "tags": ["tool", "machine", "home"], "aliases": ["power_drill", "electric_drill", "drill_driver"],
            "key_part": "gearbox", "blueprint": bp, "parts": parts,
            "paths": {"power": [[0.0, 0.04, 0], [0.0, 0.12, 0], [-0.035, ay, 0]]},
            "tour": [["battery", "A battery in the handle powers a small motor."],
                     ["motor", "The motor spins very fast, but it is weak."],
                     ["gearbox", "Tiny gears slow it down and make it much stronger."],
                     ["chuck", "The chuck grips the bit and spins it into the wall."]],
            "label": [0, 0.35, 0]}


def desk_lamp():
    bp = {"what": "A balanced-arm desk lamp: a heavy base, two arms joined by hinges, springs that hold the arms in "
                  "any position, and a shade with a bulb that points down at the desk.", "size_m": [0.55, 0.52, 0.2],
          "sits_on": "table", "front": "the side: the head reaches out to the right",
          "parts": [{"name": "base", "shape": "a heavy round disc", "size_m": [0.2, 0.03, 0.2], "faces": "bottom"},
                    {"name": "lower_arm", "shape": "two parallel rods", "size_m": [0.12, 0.36, 0.04]},
                    {"name": "upper_arm", "shape": "two parallel rods", "size_m": [0.29, 0.06, 0.04]},
                    {"name": "springs", "shape": "coil springs along the lower arm", "size_m": [0.02, 0.18, 0.02]},
                    {"name": "shade", "shape": "a cone open at the bottom", "size_m": [0.18, 0.12, 0.18], "faces": "right"},
                    {"name": "bulb", "shape": "a bulb inside the shade", "size_m": [0.05, 0.05, 0.05], "inside": "shade"}],
          "visible_details": ["hinges", "springs", "shade", "base"]}
    blk = "#2f3540"
    base_p, elbow, head = (0.0, 0.06, 0.0), (0.12, 0.4, 0.0), (0.38, 0.44, 0.0)
    parts = [P("base", "cylinder", size=[0.1, 0.03], pos=[0, 0.015, 0], fillet=0.008, color=blk, material="metal"),
             P("base_pivot", "box", size=[0.04, 0.04, 0.05], pos=[0, 0.05, 0], fillet=0.006, color=blk, material="metal"),
             *[P("lower_arm", shape="tube", points=[[base_p[0], base_p[1], sz], [elbow[0], elbow[1], sz]], size=[0.006],
                 color="#d9dee2", material="metal") for sz in (-0.018, 0.018)],
             P("elbow_joint", "cylinder", size=[0.012, 0.05], axis="z", pos=list(elbow), color=blk, material="metal"),
             *[P("upper_arm", shape="tube", points=[[elbow[0], elbow[1], sz], [head[0], head[1], sz]], size=[0.005],
                 color="#d9dee2", material="metal") for sz in (-0.018, 0.018)],
             P("head_joint", "cylinder", size=[0.01, 0.045], axis="z", pos=list(head), color=blk, material="metal"),
             P("springs", shape="spring", size=[0.008, 0.18, 0.0015], turns=14, pos=[0.04, 0.17, 0.03], rot=[0, 0, -19],
               color="#b9c1c7", material="metal"),
             P("shade", "revolve", profile=[[0.02, 0.12], [0.035, 0.1], [0.09, 0.0]], hollow=0.003, open="bottom",
               rot=[0, 0, -25], pos=[0.329, 0.331, 0], color="#c0392b", material="paint"),  # hangs from the head joint
             P("bulb_socket", "cylinder", size=[0.014, 0.05], pos=[0.36, 0.39, 0], rot=[0, 0, -25], color=blk, material="metal"),
             P("bulb", shape="sphere", size=[0.025], pos=[0.352, 0.372, 0], color="#fff2b0", kind="light", emissive=0.3)]
    return {"name": "desk_lamp", "about": "a balanced-arm desk lamp (base, arms, hinges, springs, shade, bulb)",
            "tags": ["home", "office", "light"], "aliases": ["anglepoise", "desk_lamps", "study_lamp"],
            "key_part": "springs", "blueprint": bp, "parts": parts,
            "tour": [["springs", "Springs pull against the weight of the arms."],
                     ["elbow_joint", "So the arms stay wherever you leave them."],
                     ["shade", "The shade points the light down at the desk."]],
            "label": [0, 0.7, 0]}


DESIGNS = {"washing_machine": washing_machine, "microwave": microwave, "jet_engine": jet_engine,
           "dishwasher": dishwasher, "bicycle": bicycle, "toaster": toaster, "ceiling_fan": ceiling_fan,
           "cordless_drill": cordless_drill, "desk_lamp": desk_lamp}

if __name__ == "__main__":
    sys.path.insert(0, str(RECIPES.parents[2]))
    from storyforge.world import builder, sense

    names = sys.argv[1:] or list(DESIGNS)
    for n in names:
        r = DESIGNS[n]()
        problems = sense.check(builder.model_from_recipe(r), r.get("blueprint"))  # step 2: does it hold together?
        r["sense"] = problems
        r["checked"] = "failed" if problems else "checked"
        r["check_note"] = ("sense check: " + "; ".join(problems)) if problems else \
            "Part 14: sense check passed; 3-view check judged by eye (no Gemini key in that session)"
        (RECIPES / f"{n}.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        print("wrote", n, len(r["parts"]), "parts", "OK" if not problems else problems)
