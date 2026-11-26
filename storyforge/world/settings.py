"""Settings: the place around a machine, per area (a fridge in a kitchen, a toilet in a bathroom, an engine in a
garage, an elevator building on a city street). Real scale, built around the area's main objects.

A setting is a small open "dollhouse" corner: a floor, two back walls (left and back) and the furniture that
belongs there, so the camera (in front) always sees the machine with its real surroundings behind it. Walls and
furniture that would hide the machine are left out automatically (scene.py). `studio` is the clean dark studio
(just the glowing grid and a low turntable under a single machine).

The plan's area can say "setting": "kitchen"; otherwise it is guessed from the area's objects and words.
"""

from __future__ import annotations

import math
import re
import zlib

import numpy as np

from . import mesh as M
from .assets import C, asset, col
from .mesh import Model

SETTINGS = {
    "studio": "the clean light studio (default for machines and diagrams)",
    "kitchen": "a home kitchen: tiled floor, walls, counter with sink and stove, cabinets, window",
    "bathroom": "a bathroom: tiles, sink with mirror, bathtub, towel",
    "laundry": "a laundry room: tiled floor, walls, a shelf with detergent, a laundry basket (washers, dryers)",
    "hangar": "an aircraft hangar: big light concrete floor with yellow lines, a tall back wall, tool carts (jet "
              "engines, planes, helicopters)",
    "garage": "a car workshop: concrete floor, tool wall, workbench, tires, shelves",
    "street": "a city street: road, sidewalk, buildings behind, lamp posts, trees",
    "living_room": "a living room: wooden floor, sofa, rug, lamp, window",
    "office": "an office: carpet, desk with a computer, chair, plant, window",
    "lab": "a science lab: white floor, lab bench with glassware, shelves",
    "factory": "a factory floor: concrete with yellow safety lines, steel columns, crates, barrels",
    "outdoors": "open grass with trees and rocks",
    "farm": "a farm yard (dirt, hay, fences)",
    "desk": "a desk top seen up close (for small things: phones, batteries, chips)",
    "table": "COMPARISON: a plain light table top in a clean light studio, nothing else (everyday things side by "
             "side to show a big or tiny number: a water bottle and a shot glass, a droplet next to a hair)",
    "site": "an industrial site: concrete pad, barrels, crates, a worker (big plants, tanks, power stations)",
    "town": "a small town: grass, houses, cars, people",
}
OLD_STYLE = {"farm", "site", "town"}  # dressed by decor.py (pads, props along the edges, people, fences, lamps)
ALIASES = {"home": "kitchen", "house": "living_room", "room": "living_room", "workshop": "garage",
           "repair_shop": "garage", "road": "street", "city": "street", "town": "street", "toilet": "bathroom",
           "restroom": "bathroom", "laboratory": "lab", "plant": "factory", "industry": "factory", "park": "outdoors",
           "field": "outdoors", "nature": "outdoors", "tabletop": "table", "comparison": "table", "compare": "table",
           "floor": "table", "none": "studio",
           "default": "studio", "dark": "studio"}
KEYWORDS = [  # (words, setting): the area's objects and its shots' words; most hits wins
    (r"fridge|refrigerator|freezer|oven|microwave|dishwasher|kettle|toaster|stove|kitchen|blender|coffee", "kitchen"),
    (r"toilet|flush|shower|bathtub|bath|sink|faucet|tap|bathroom|water heater", "bathroom"),
    (r"washing machine|washer|dryer|laundry|detergent", "laundry"),
    (r"jet engine|turbofan|turbine engine|aircraft|airplane|airliner|helicopter|hangar|jet", "hangar"),
    (r"engine|piston|car\b|cars\b|gearbox|transmission|brake|tire|tyre|garage|mechanic|exhaust|spark plug", "garage"),
    (r"elevator|lift|skyscraper|building|traffic|street|escalator|bus\b", "street"),
    (r"washing machine|vacuum|air condition|heater|tv\b|television|sofa|living room", "living_room"),
    (r"computer|printer|office|keyboard|monitor|laptop", "office"),
    (r"phone|smartphone|battery|chip|processor|watch|camera|headphone|calculator|remote", "desk"),
    (r"microscope|lab\b|laboratory|chemical|experiment", "lab"),
    (r"factory|assembly line|conveyor|robot arm|warehouse|steel mill", "factory"),
]


def resolve(name) -> str | None:
    n = re.sub(r"[^a-z_]+", "_", str(name or "").lower()).strip("_")
    if n in SETTINGS:
        return n
    return ALIASES.get(n)


def guess(words: list[str], names: list[str] = ()) -> str:
    """The setting with the most keyword hits: the objects' names count 6 times, the spoken words once."""
    text = " ".join(str(w) for w in words).lower().replace("_", " ")
    objs = " ".join(str(w) for w in names).lower().replace("_", " ")
    best, hits = "studio", 0
    for pattern, key in KEYWORDS:
        rx = r"\b(?:" + pattern + r")"
        n = len(re.findall(rx, text)) + 6 * len(re.findall(rx, objs))
        if n > hits:
            best, hits = key, n
    return best


def _rng(*parts):
    return np.random.default_rng(zlib.crc32("/".join(map(str, parts)).encode()))


# ---------------------------------------------------------------------------------------------------------------
# Set pieces (tag "set": the planner doesn't see them, the settings place them)
# ---------------------------------------------------------------------------------------------------------------

@asset("floor_tiles", "a tiled floor", ["set"])
def floor_tiles(w=4.0, d=4.0, tile=0.5, color="#e8e2d6", color2="#d3cbbd"):
    nx, nz = max(1, int(round(w / tile))), max(1, int(round(d / tile)))
    tw, td = w / nx, d / nz
    a, b = [], []
    for i in range(nx):
        for j in range(nz):
            g = M.xf(M.box(tw * 0.97, 0.02, td * 0.97), (-w / 2 + (i + 0.5) * tw, 0.012, -d / 2 + (j + 0.5) * td))
            (a if (i + j) % 2 == 0 else b).append(g)
    m = Model().add("grout", M.xf(M.box(w, 0.01, d), (0, 0.005, 0)), "#9c958a")
    m.add("tiles", M.merge(*a), color, material="ceramic")
    if b:
        m.add("tiles2", M.merge(*b), color2, material="ceramic")
    return m


@asset("planks", "a wooden plank floor", ["set"])
def planks(w=4.0, d=4.0, color="#a8774a"):
    n = max(2, int(d / 0.2))
    pl = []
    for j in range(n):
        off = (j % 3) * 0.6
        x = -w / 2 - off
        while x < w / 2:
            x1 = min(w / 2, x + 1.8)
            x0 = max(-w / 2, x)
            if x1 - x0 > 0.05:
                pl.append(M.xf(M.box(x1 - x0 - 0.01, 0.02, d / n * 0.95), ((x0 + x1) / 2, 0.012, -d / 2 + (j + 0.5) * d / n)))
            x = x1
    return Model().add("gap", M.xf(M.box(w, 0.01, d), (0, 0.005, 0)), "#5e4128").add("planks", M.merge(*pl), color)


@asset("slab", "a flat floor slab (concrete, asphalt, carpet, grass)", ["set"])
def slab(w=4.0, d=4.0, h=0.03, color="#8d9196"):
    return Model().add("slab", M.xf(M.box(w, h, d), (0, h / 2, 0)), color)


@asset("wall", "a wall (optional window, tiles up to a height)", ["set"])
def wall(length=4.0, h=2.7, color="#efe9de", tiles="", tile_h=1.2, window=0.0, window_x=0.0):
    t = 0.12
    parts = []
    if window > 0:  # a hole for the window: 4 pieces around it
        wx, ww, wy0, wy1 = float(window_x), float(window), 0.95, min(h - 0.35, 0.95 + window * 0.9)
        parts += [M.xf(M.box(max(0.01, wx - ww / 2 + length / 2), h, t), ((-length / 2 + wx - ww / 2) / 2, h / 2, 0)),
                  M.xf(M.box(max(0.01, length / 2 - wx - ww / 2), h, t), ((length / 2 + wx + ww / 2) / 2, h / 2, 0)),
                  M.xf(M.box(ww, wy0, t), (wx, wy0 / 2, 0)), M.xf(M.box(ww, h - wy1, t), (wx, (h + wy1) / 2, 0))]
    else:
        parts.append(M.xf(M.box(length, h, t), (0, h / 2, 0)))
    m = Model().add("wall", M.merge(*parts), color, shell=True)
    if tiles:
        rows = []
        for j in range(int(tile_h / 0.15)):
            for i in range(int(length / 0.15)):
                x = -length / 2 + (i + 0.5) * 0.15
                if window > 0 and abs(x - float(window_x)) < float(window) / 2 + 0.05 and 0.12 + j * 0.15 > 0.9:
                    continue
                rows.append(M.xf(M.box(0.14, 0.14, 0.01), (x, 0.075 + j * 0.15, t / 2 + 0.006)))
        if rows:
            m.add("wall_tiles", M.merge(*rows), tiles, material="ceramic", shell=True)
    if window > 0:
        wx, ww, wy0, wy1 = float(window_x), float(window), 0.95, min(h - 0.35, 0.95 + float(window) * 0.9)
        m.add("window_glass", M.xf(M.box(ww, wy1 - wy0, 0.02), (wx, (wy0 + wy1) / 2, 0)), "#bfe6ff", emissive=0.35,
              opacity=0.55, material="glass", shell=True)
        frame = [M.xf(M.box(ww + 0.08, 0.06, t + 0.04), (wx, y, 0)) for y in (wy0, wy1, (wy0 + wy1) / 2)]
        frame += [M.xf(M.box(0.06, wy1 - wy0, t + 0.04), (x, (wy0 + wy1) / 2, 0)) for x in (wx - ww / 2, wx, wx + ww / 2)]
        m.add("window_frame", M.merge(*frame), "#f7f5f0", shell=True)
    return m


@asset("kitchen_counter", "kitchen counter: cabinets, worktop, sink, stove", ["set"])
def kitchen_counter(length=2.4, color="#f2efe8", top="#5a5f66", sink=True, stove=True):
    L = float(length)
    m = Model().add("cabinets", M.xf(M.box(L, 0.86, 0.6), (0, 0.45, 0)), col(color, "#f2efe8"))
    m.add("plinth", M.xf(M.box(L, 0.08, 0.55), (0, 0.04, 0.0)), "#3a3d42")
    m.add("worktop", M.xf(M.box(L + 0.04, 0.04, 0.64), (0, 0.9, 0.0)), top, material="ceramic")
    doors = []
    n = max(1, int(L / 0.6))
    for k in range(n):
        x = -L / 2 + (k + 0.5) * L / n
        doors.append(M.xf(M.box(L / n - 0.03, 0.7, 0.02), (x, 0.47, 0.31)))
        doors.append(M.xf(M.box(0.12, 0.02, 0.02), (x, 0.74, 0.33)))
    m.add("doors", M.merge(*doors), "#e4e0d6")
    if sink:
        m.add("sink", M.xf(M.box(0.5, 0.03, 0.4), (-L / 4, 0.915, 0.0)), "#c9ced3", material="metal")
        m.add("faucet", M.tube([(-L / 4, 0.92, -0.24), (-L / 4, 1.15, -0.24), (-L / 4, 1.15, -0.1)], 0.015, 6), "#d7dce0",
              material="metal")
    if stove:
        rings = [M.xf(M.cylinder(0.09, 0.012, 12), (L / 4 + dx, 0.92, dz)) for dx in (-0.13, 0.13) for dz in (-0.12, 0.12)]
        m.add("hob", M.merge(M.xf(M.box(0.6, 0.012, 0.52), (L / 4, 0.92, 0)), *rings), "#1d1f22", material="glass")
    return m


@asset("upper_cabinets", "wall cabinets", ["set"])
def upper_cabinets(length=2.4, color="#f2efe8"):
    L = float(length)
    m = Model().add("box", M.xf(M.box(L, 0.7, 0.35), (0, 1.85, 0)), col(color, "#f2efe8"))
    n = max(1, int(L / 0.6))
    m.add("handles", M.merge(*[M.xf(M.box(0.12, 0.02, 0.02), (-L / 2 + (k + 0.5) * L / n, 1.58, 0.19)) for k in range(n)]),
          "#9aa2aa", material="metal")
    m.add("light_strip", M.xf(M.box(L * 0.9, 0.02, 0.05), (0, 1.49, 0.1)), "#fff1cf", emissive=0.9)
    return m


@asset("vanity", "bathroom sink cabinet with a mirror", ["set"])
def vanity(color="#f4f2ee"):
    m = Model().add("cabinet", M.xf(M.box(0.8, 0.8, 0.45), (0, 0.4, 0)), color)
    m.add("basin", M.xf(M.cylinder(0.24, 0.12, 14, r_top=0.28), (0, 0.8, 0.02)), "#ffffff", material="ceramic")
    m.add("tap", M.tube([(0, 0.85, -0.18), (0, 1.02, -0.18), (0, 1.02, -0.06)], 0.014, 6), "#d7dce0", material="metal")
    m.add("mirror", M.xf(M.box(0.7, 0.8, 0.03), (0, 1.55, -0.2)), "#cfe8f2", emissive=0.15, material="glass")
    return m


@asset("bathtub", "a bathtub", ["set"])
def bathtub(length=1.6):
    L = float(length)
    m = Model().add("tub", M.xf(M.box(L, 0.55, 0.75), (0, 0.275, 0)), "#fbfbf8", material="ceramic")
    m.add("water", M.xf(M.box(L - 0.12, 0.02, 0.62), (0, 0.5, 0)), "#7fd0f0", opacity=0.75, material="water")
    return m


@asset("towel_rail", "a towel on a rail", ["set"])
def towel_rail(color="#5fb3c9"):
    m = Model().add("rail", M.xf(M.box(0.6, 0.02, 0.02), (0, 1.3, 0)), "#d7dce0", material="metal")
    return m.add("towel", M.xf(M.box(0.45, 0.55, 0.04), (0, 1.05, 0.02)), col(color, "#5fb3c9"))


@asset("workbench", "a workbench with tools", ["set"])
def workbench(length=1.8):
    L = float(length)
    m = Model().add("top", M.xf(M.box(L, 0.06, 0.7), (0, 0.9, 0)), "#9a6b3f")
    m.add("legs", M.merge(*[M.xf(M.box(0.06, 0.88, 0.06), (x, 0.44, z)) for x in (-L / 2 + 0.06, L / 2 - 0.06)
                            for z in (-0.3, 0.3)]), "#3a4048", material="metal")
    m.add("vise", M.xf(M.box(0.2, 0.12, 0.15), (L / 2 - 0.25, 0.99, 0.2)), "#2f6fb5", material="metal")
    m.add("toolbox", M.xf(M.box(0.45, 0.22, 0.25), (-L / 4, 1.04, 0)), "#c0392b", material="metal")
    return m


@asset("tool_wall", "a pegboard with tools", ["set"])
def tool_wall(length=2.0, y=1.6):
    L, y = float(length), float(y)
    m = Model().add("board", M.xf(M.box(L, 1.0, 0.03), (0, y, 0)), "#c9a878", shell=True)
    tools = []
    for k in range(int(L / 0.25)):
        x = -L / 2 + 0.15 + k * 0.25
        tools.append(M.xf(M.box(0.04, 0.3 + 0.1 * (k % 3), 0.02), (x, y, 0.03)))
    m.add("tools", M.merge(*tools), "#59616a", material="metal", shell=True)
    return m


@asset("tire_stack", "a stack of tires", ["set"])
def tire_stack(n=3):
    return Model().add("tires", M.merge(*[M.xf(M.cylinder(0.33, 0.22, 14), (0, k * 0.22, 0)) for k in range(int(n))]),
                       "#23262a")


@asset("shelf", "a steel shelf with boxes", ["set"])
def shelf(length=1.6, seed=1):
    L = float(length)
    rng = _rng("shelf", seed)
    m = Model().add("frame", M.merge(*[M.xf(M.box(0.04, 1.9, 0.04), (x, 0.95, z)) for x in (-L / 2, L / 2)
                                       for z in (-0.2, 0.2)],
                                     *[M.xf(M.box(L, 0.03, 0.42), (0, y, 0)) for y in (0.1, 0.7, 1.3, 1.85)]),
                    "#69727b", material="metal")
    boxes = []
    for y in (0.12, 0.72, 1.32):
        x = -L / 2 + 0.1
        while x < L / 2 - 0.3:
            bw = float(rng.uniform(0.2, 0.4))
            bh = float(rng.uniform(0.15, 0.4))
            boxes.append(M.xf(M.box(bw, bh, 0.3), (x + bw / 2, y + bh / 2 + 0.015, 0)))
            x += bw + 0.05
    m.add("boxes", M.merge(*boxes), "#c8a06a")
    return m


@asset("sofa", "a sofa", ["set"])
def sofa(color="#4f6d8f"):
    c = col(color, "#4f6d8f")
    m = Model().add("seat", M.xf(M.box(2.0, 0.42, 0.85), (0, 0.21, 0)), c)
    m.add("back", M.xf(M.box(2.0, 0.5, 0.2), (0, 0.65, -0.33)), c)
    m.add("arms", M.merge(M.xf(M.box(0.2, 0.25, 0.85), (-1.0, 0.55, 0)), M.xf(M.box(0.2, 0.25, 0.85), (1.0, 0.55, 0))), c)
    return m


@asset("desk_table", "a desk", ["set"])
def desk_table(length=1.4):
    L = float(length)
    m = Model().add("top", M.xf(M.box(L, 0.04, 0.7), (0, 0.74, 0)), "#e9e4da")
    m.add("legs", M.merge(*[M.xf(M.box(0.04, 0.72, 0.04), (x, 0.36, z)) for x in (-L / 2 + 0.05, L / 2 - 0.05)
                            for z in (-0.3, 0.3)]), "#3a4048", material="metal")
    m.add("monitor", M.merge(M.xf(M.box(0.6, 0.36, 0.03), (0, 1.05, -0.2)), M.xf(M.box(0.05, 0.25, 0.05), (0, 0.86, -0.22))),
          "#1d1f22")
    m.add("screen", M.xf(M.box(0.56, 0.32, 0.01), (0, 1.05, -0.183)), "#6fc3ff", emissive=0.6)
    return m


@asset("potted_plant", "a plant in a pot", ["set"])
def potted_plant(h=1.0):
    h = float(h)
    m = Model().add("pot", M.cylinder(0.16 * h, 0.3 * h, 10, r_top=0.2 * h), "#c56a3a")
    leaves = [M.xf(M.sphere(0.22 * h, 0), (0.1 * h * math.cos(a), 0.55 * h + 0.12 * h * (k % 2), 0.1 * h * math.sin(a)))
              for k, a in enumerate(np.linspace(0, 2 * math.pi, 5, endpoint=False))]
    return m.add("leaves", M.merge(*leaves), "#3f9b4f")


@asset("city_block", "a simple building seen behind a street", ["set"])
def city_block(w=6.0, h=12.0, color="#9fa8b3", seed=1):
    rng = _rng("block", seed)
    m = Model().add("body", M.xf(M.box(w, h, 5.0), (0, h / 2, 0)), col(color, "#9fa8b3"))
    win = []
    lit = []
    for fy in range(1, int(h / 3)):
        for k in range(int(w / 1.5)):
            g = M.xf(M.box(0.8, 1.2, 0.05), (-w / 2 + 0.75 + k * 1.5, fy * 3.0 - 0.6, 2.51))
            (lit if rng.random() < 0.35 else win).append(g)
    if win:
        m.add("windows", M.merge(*win), "#2c3e50", material="glass")
    if lit:
        m.add("lit_windows", M.merge(*lit), "#ffd27a", emissive=0.7)
    return m


@asset("street_road", "a road with a sidewalk", ["set"])
def street_road(length=30.0):
    L = float(length)
    m = Model().add("asphalt", M.xf(M.box(L, 0.03, 7.0), (0, 0.015, 0)), "#3a3d42")
    m.add("sidewalk", M.xf(M.box(L, 0.15, 3.0), (0, 0.075, -5.0)), "#b9b5ac")
    m.add("curb", M.xf(M.box(L, 0.16, 0.2), (0, 0.08, -3.45)), "#d6d2c9")
    m.add("lines", M.merge(*[M.xf(M.box(1.8, 0.035, 0.15), (-L / 2 + 1.5 + k * 4.0, 0.02, 0)) for k in range(int(L / 4))]),
          "#f4f1ea")
    return m


@asset("turntable", "a low round stage under a machine (studio)", ["set"])
def turntable(r=1.0):
    r = float(r)
    m = Model().add("disc", M.cylinder(r, 0.04 * max(0.3, r), 32), "#1f3a40", material="paint")
    return m.add("rim", M.xf(M.torus(r, 0.012 * max(0.4, r), 40, 4), (0, 0.04 * max(0.3, r), 0)), "#2ee6d6",
                 emissive=0.9)


# ---------------------------------------------------------------------------------------------------------------
# Dressing an area
# ---------------------------------------------------------------------------------------------------------------

def dress(world, area: dict, setting: str, insts: list) -> list[dict]:
    """The setting's pieces around the area's main objects (world coordinates in 'at')."""
    from . import assets as assets_mod  # noqa: PLC0415
    from .decor import inst_box  # noqa: PLC0415

    aid = area["id"]
    boxes = [inst_box(i) for i in insts]
    lo, hi = np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)
    cx, cz = float(lo[0] + hi[0]) / 2, float(lo[2] + hi[2]) / 2
    size = float(max(hi[0] - lo[0], hi[2] - lo[2]))
    out: list[dict] = []

    def put(a, x, z, elev=0.0, rot=0.0, **params):
        out.append({"asset": a, "area": aid, "at": (float(x), float(elev), float(z)), "rot": float(rot), "params": params})

    if any("cross_section" in getattr(assets_mod.REGISTRY.get(i.asset), "tags", []) for i in insts):
        return out  # a mountain cut open IS the place (no grass or props in front of the underground)
    if setting == "studio":
        if len(insts) <= 2 and size < 8:
            put("turntable", cx, cz, r=round(max(0.4, size * 0.6), 2))
        return out
    if setting in ("kitchen", "bathroom", "garage", "living_room", "office", "lab", "laundry"):
        # a room corner: back wall behind the objects, a side wall on the left, the floor between
        room_w = max(4.2, (hi[0] - lo[0]) + 3.6)
        room_d = max(3.4, (hi[2] - lo[2]) + 2.6)
        bz = float(lo[2]) - max(0.12, min(0.25, size * 0.2))  # back wall face: close behind small things
        x0 = float(lo[0]) - 1.3
        x1 = x0 + room_w
        fz = bz + room_d
        h = 2.7 if setting != "garage" else 3.4
        floor = {"kitchen": ("floor_tiles", {"color": "#e9e3d6", "color2": "#cfc6b6", "tile": 0.5}),
                 "bathroom": ("floor_tiles", {"color": "#f2f4f5", "color2": "#c9d6dc", "tile": 0.3}),
                 "garage": ("slab", {"color": "#8f9397"}), "living_room": ("planks", {}),
                 "office": ("slab", {"color": "#5d6670"}), "lab": ("floor_tiles", {"color": "#f4f6f7", "color2": "#e3e9ec",
                                                                                   "tile": 0.6}),
                 "laundry": ("floor_tiles", {"color": "#eef1f3", "color2": "#d5dde2", "tile": 0.4})}[setting]
        back = 1.4  # the floor goes on behind the back wall: a shot of the machine's back doesn't fall off the room
        put(floor[0], (x0 + x1) / 2, (bz - back + fz) / 2, w=round(room_w, 2), d=round(room_d + back, 2), **floor[1])
        wall_col = {"kitchen": "#f1e9da", "bathroom": "#eef5f7", "garage": "#c3c7c9", "living_room": "#e9dfd0",
                    "office": "#e6e9ec", "lab": "#f3f6f8", "laundry": "#e8f1f4"}[setting]
        tiles = {"kitchen": "#9fc7c4", "bathroom": "#a9d4e2", "laundry": "#bcdbe6"}.get(setting, "")
        put("wall", (x0 + x1) / 2, bz - 0.06, length=round(room_w, 2), h=h, color=wall_col, tiles=tiles,
            tile_h=1.6 if setting == "bathroom" else 0.6)
        put("wall", x0 - 0.06, (bz + fz) / 2, rot=-90.0, length=round(room_d, 2), h=h, color=wall_col,
            window=1.1 if setting != "garage" else 0.0, window_x=0.0, tiles=tiles if setting == "bathroom" else "")
        right = float(hi[0]) + 0.35  # free wall space to the right of the main objects
        left = float(lo[0]) - 0.3
        if setting == "kitchen":
            L = max(1.2, min(2.6, x1 - right - 0.3))
            put("kitchen_counter", right + L / 2, bz + 0.32, length=round(L, 2))
            put("upper_cabinets", right + L / 2, bz + 0.18, length=round(L, 2))
            if left - x0 > 0.9:
                put("potted_plant", x0 + 0.45, bz + 0.4, h=0.9)
        elif setting == "bathroom":
            if x1 - right > 1.0:
                put("vanity", right + 0.55, bz + 0.25)
                put("towel_rail", min(x1 - 0.4, right + 1.4), bz + 0.06)
            if left - x0 > 1.0:
                put("bathtub", x0 + 0.4, (bz + fz) / 2 - 0.2, rot=90.0, length=1.6)
        elif setting == "garage":
            L = max(1.2, min(2.2, x1 - right - 0.3))
            put("workbench", right + L / 2, bz + 0.4, length=round(L, 2))
            put("tool_wall", right + L / 2, bz + 0.02, length=round(L, 2))
            if size < 1.5:  # a small machine: the tools hang right behind it, in the picture
                put("tool_wall", cx, bz + 0.02, length=round(max(1.2, size * 2.2), 2), y=round(0.55 + size * 0.6, 2))
            put("tire_stack", x0 + 0.5, bz + 0.5, n=4)
            put("shelf", x0 + 0.25, bz + 1.6, rot=90.0, length=1.4)
        elif setting == "living_room":
            put("sofa", right + 1.1, bz + 0.5, color="#4f6d8f")
            put("potted_plant", x0 + 0.4, bz + 0.4, h=1.1)
        elif setting == "office":
            put("desk_table", right + 0.8, bz + 0.45)
            put("potted_plant", x0 + 0.4, bz + 0.4, h=1.0)
        elif setting == "laundry":
            put("shelf", right + 0.7, bz + 0.2, length=1.2)
            put("bucket", right + 0.5, bz + 0.8)
            put("potted_plant", x0 + 0.4, bz + 0.4, h=0.8)
        elif setting == "lab":
            put("kitchen_counter", right + 0.9, bz + 0.32, length=1.8, sink=True, stove=False, color="#e9eef1", top="#2f3438")
            put("shelf", x0 + 0.25, bz + 1.4, rot=90.0, length=1.2)
        return out
    if setting == "table":  # a comparison: a plain light table top, nothing else
        w, d = max(1.4, size * 3.2), max(1.0, size * 2.2)
        put("slab", cx, cz - d * 0.1, w=round(w, 2), d=round(d, 2), h=0.04, color="#eef1f3")
        return out
    if setting == "desk":  # the floor IS the desk top: wood, with a few desk things far behind
        w, d = max(1.2, size * 6), max(0.9, size * 4.5)
        put("planks", cx, cz - d * 0.15, w=round(w, 2), d=round(d, 2), color="#b78350")
        return out
    if setting == "street":
        L = max(16.0, min(size * 2 + 14, 2 * float(world.area_r.get(aid, size)) + 12))  # stays in its own area
        put("street_road", cx, float(hi[2]) + 4.6, length=round(L, 1))
        for k, dx in enumerate((-1, 1)):
            put("city_block", cx + dx * (size / 2 + 5.5), float(lo[2]) + 1.0, w=7.0, h=10.0 + 4 * k, seed=k + 1,
                color=["#9fa8b3", "#c2a98f"][k])
        for dx in (-1, 1):
            put("lamp_post", cx + dx * (size / 2 + 1.6), float(hi[2]) + 1.0, rot=-90.0)
            put("tree", cx + dx * (size / 2 + 3.4), float(hi[2]) + 1.0)
            put("person", cx + dx * (size / 2 + 2.4), float(hi[2]) + 2.2, rot=dx * 30.0)  # people for scale
        return out
    if setting == "hangar":  # a big, bright hangar: light concrete, yellow safety lines, a tall wall behind
        w, d = max(14.0, size * 3.2), max(10.0, size * 2.6)
        put("slab", cx, cz, w=round(w, 2), d=round(d, 2), color="#c9cdd1")
        put("pad", cx, cz, w=round(size + 2.0, 2), d=round(float(hi[2] - lo[2]) + 2.0, 2), color="#f4c430")
        put("slab", cx, cz, w=round(size + 1.7, 2), d=round(float(hi[2] - lo[2]) + 1.7, 2), h=0.035, color="#c9cdd1")
        put("wall", cx, cz - d / 2, length=round(w, 2), h=round(max(6.0, float(hi[1]) * 1.8), 2), color="#dfe4e8",
            window=0.0, window_x=0.0)
        for dx in (-1, 1):
            put("crate", cx + dx * (w / 2 - 1.2), cz - d / 2 + 1.0)
            put("barrel", cx + dx * (w / 2 - 2.2), cz - d / 2 + 0.9)
        put("person", cx + size / 2 + 1.6, cz + float(hi[2] - lo[2]) / 2 + 0.6, rot=-30.0)  # a person for scale
        return out
    if setting == "factory":
        w, d = max(8.0, size + 6), max(6.0, size + 5)
        put("slab", cx, cz, w=round(w, 2), d=round(d, 2), color="#7c8187")
        put("pad", cx, cz, w=round(size + 1.6, 2), d=round(float(hi[2] - lo[2]) + 1.6, 2), color="#f4c430")
        put("slab", cx, cz, w=round(size + 1.3, 2), d=round(float(hi[2] - lo[2]) + 1.3, 2), h=0.035, color="#7c8187")
        for dx in (-1, 1):
            put("barrel", cx + dx * (w / 2 - 0.8), cz - d / 2 + 0.8)
            put("crate", cx + dx * (w / 2 - 1.8), cz - d / 2 + 0.7)
        return out
    if setting == "outdoors":
        put("slab", cx, cz, w=round(max(12.0, size * 3), 1), d=round(max(10.0, size * 2.5), 1), color="#6cae4f")
        rng = _rng(aid, "outdoors")
        for k in range(6):
            a = rng.uniform(math.pi * 0.9, math.pi * 2.1)
            rr = size / 2 + rng.uniform(2.0, 5.0)
            put("tree" if k % 2 == 0 else "rock", cx + rr * math.cos(a), cz + rr * math.sin(a) - 1.0,
                rot=float(rng.uniform(0, 360)))
        for k in range(2):  # tiny people for scale
            put("person", cx + (k * 2 - 1) * (size / 2 + 1.2), cz + size * 0.3 + 0.8, rot=float(rng.uniform(-40, 40)))
        return out
    return out
