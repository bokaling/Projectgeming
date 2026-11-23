"""The asset library: low poly objects built from simple shapes, all made in code (no downloads, no licenses).

Every asset is a function that returns a Model (named parts + anchor points). Parameters change the
look (size, color, count of windows…), so the AI can compose new scenes from them. Parts have a
`kind` so animations can find them: "liquid" (fill), "blade" (spin), "light" (turns on), "wheel",
"shell" (cut open / x-ray), "screen".

Add a new asset: write a function `def my_thing(color="#hex", size=1.0, **_) -> Model`, decorate it with
@asset("my_thing", "what it is", tags=[...]). It shows up in the AI's catalog automatically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import mesh as M
from .mesh import Model


@dataclass
class AssetInfo:
    name: str
    fn: Callable
    about: str
    tags: list = field(default_factory=list)
    params: dict = field(default_factory=dict)  # name -> default


REGISTRY: dict[str, AssetInfo] = {}
ALIASES: dict[str, str] = {}


def asset(name: str, about: str, tags=(), aliases=()):
    def wrap(fn):
        import inspect  # noqa: PLC0415

        params = {k: v.default for k, v in inspect.signature(fn).parameters.items()
                  if v.default is not inspect.Parameter.empty and k != "_"}
        REGISTRY[name] = AssetInfo(name, fn, about, list(tags), params)
        for a in aliases:
            ALIASES[a] = name
        return fn
    return wrap


def build(name: str, **params) -> Model:
    info = REGISTRY[resolve(name)]
    ok = {k: v for k, v in params.items() if k in info.params}
    model = info.fn(**ok)
    for p in model.parts:  # the old library's steel, gold and copper parts look like metal
        if not p.material and str(p.color).lower() in METALS:
            p.material = "metal"
    model = _merge_static(model)
    lo, hi = model.bounds()
    model.anchors.setdefault("top", (0.0, float(hi[1]), 0.0))
    model.anchors.setdefault("label", (0.0, float(hi[1]) + 0.35, 0.0))
    model.anchors.setdefault("center", tuple(float(x) for x in (lo + hi) / 2))
    return model


def _merge_static(model: Model) -> Model:
    """Plain parts (no animation, not a shell) with the same look become one mesh: far fewer draws, same picture."""
    keep, groups = [], {}
    for p in model.parts:
        if p.kind or p.shell or p.motion:  # moving parts and shells (walls: hidden one by one when they block) stay apart
            keep.append(p)
            continue
        key = (str(p.color).lower(), round(float(p.opacity), 3), round(float(p.emissive), 3), p.material)
        groups.setdefault(key, []).append(p)
    merged = []
    for parts in groups.values():
        first = parts[0]
        if len(parts) > 1:
            boxes = [b for p in parts for b in (p.boxes or [p.geo.bounds()])]
            first = M.Part(first.name, M.merge(*[p.geo for p in parts]), first.color, first.emissive, first.opacity,
                           first.shell, boxes=boxes, material=first.material)
        merged.append(first)
    model.parts = merged + keep
    return model


def resolve(name: str) -> str:
    """Asset name, alias, plural or the closest match ('cows' → cow, 'biogas tank' → digester)."""
    n = str(name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if n in REGISTRY:
        return n
    if n in ALIASES:
        return ALIASES[n]
    for cand in (n.rstrip("s"), n[:-2] if n.endswith("es") else "", n[:-3] + "y" if n.endswith("ies") else ""):
        if cand in REGISTRY:
            return cand
        if cand in ALIASES:
            return ALIASES[cand]
    words = [w for w in n.split("_") if w]
    for w in reversed(words):  # "big_water_tank" → tank
        for cand in (w, w.rstrip("s")):
            if cand in REGISTRY:
                return cand
            if cand in ALIASES:
                return ALIASES[cand]
    import difflib  # noqa: PLC0415

    close = difflib.get_close_matches(n, list(REGISTRY) + list(ALIASES), n=1, cutoff=0.6)
    if close:
        return ALIASES.get(close[0], close[0])
    return "crate"


_FOCUS: dict = {}


def focus_points(name: str) -> list[str]:
    """The parts of a machine the camera can aim at ("eng1.piston"): its part names and anchor points."""
    if name not in _FOCUS:
        import re  # noqa: PLC0415

        try:
            m = build(name)
            stems = [re.sub(r"\d+$", "", p.name) for p in m.parts if p.motion or p.kind]  # the works first
            stems += [a for a in m.anchors if a not in ("label", "top", "center", "inside")]
            stems += [re.sub(r"\d+$", "", p.name) for p in m.parts if p.shell]
            stems = list(dict.fromkeys(s for s in stems if s))
            heads = [s.split("_")[0] for s in stems if "_" in s]
            for h in {h for h in heads if heads.count(h) >= 3}:  # car_floor, car_back, car_door… → "car"
                k = next(i for i, s in enumerate(stems) if s.startswith(h + "_"))
                stems = stems[:k] + [h] + [s for s in stems[k:] if not s.startswith(h + "_")]
            _FOCUS[name] = list(dict.fromkeys(stems))[:14]
        except Exception:  # noqa: BLE001
            _FOCUS[name] = []
    return _FOCUS[name]


def catalog(compact: bool = True) -> str:
    """The list the AI sees: name: what it is [real size] [params] [focus: parts the camera can aim at]."""
    lines = []
    for info in sorted(REGISTRY.values(), key=lambda i: i.name):
        if "set" in info.tags:  # walls, counters, tiles: the settings place them
            continue
        ps = ", ".join(f"{k}={v!r}" for k, v in info.params.items() if k not in ("seed",))
        line = f"- {info.name}({ps}): {info.about}" if not compact else f"- {info.name}: {info.about}" + (
            f" [params: {ps}]" if ps else "")
        if info.name in REAL_SIZE:
            line += f" [real size {REAL_SIZE[info.name]} m]"
        if {"machine", "cutaway"} & set(info.tags):
            pts = focus_points(info.name)
            if pts:
                line += " [focus: " + ", ".join(pts) + "]"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Palette (friendly, saturated, flat)
# ---------------------------------------------------------------------------

C = {
    "red": "#d9534f", "barn": "#c0443e", "roof": "#4b3b47", "white": "#f4f1ea", "black": "#2a2a2e",
    "pink": "#f2a7b5", "manure": "#6e4a2c", "dark_brown": "#4a3220", "crust": "#a9895c", "concrete": "#b8c1c6",
    "steel": "#8f9ba8", "dark_steel": "#5b6672", "yellow": "#f4c430", "green": "#4aa564", "dark_green": "#2f6e45",
    "tree": "#53b257", "trunk": "#7a5232", "wood": "#a0703f", "orange": "#f28c28", "blue": "#3d8fd6",
    "sky_blue": "#7cc6ea", "water": "#3aa6d9", "glass": "#bfe9ff", "lamp": "#ffd76b", "gas": "#9fe870",
    "purple": "#9a6ad6", "teal": "#2cc7b8", "gray": "#9aa3ab", "skin": "#f1c7a0", "sand": "#e2c98f",
    "grass": "#6cbf4f", "fire": "#ff7a1a", "smoke": "#b9c2c9", "gold": "#f6c445", "copper": "#c8763c",
}


METALS = {C["steel"], C["dark_steel"], C["gold"], C["copper"]}


def col(c, default):
    return C.get(str(c), c) if c else default


# ---------------------------------------------------------------------------
# Generic shapes the AI can use for anything
# ---------------------------------------------------------------------------


@asset("crate", "a box / crate / block (use for anything boxy)", ["generic"], aliases=["box", "block", "cube"])
def crate(w=1.0, h=1.0, d=1.0, color="#c69c6d"):
    m = Model().add("body", M.box(w, h, d, base=True), col(color, "#c69c6d"))
    m.add("trim", M.box(w * 1.02, h * 0.08, d * 1.02, base=True), "#8a6a45")
    return m


@asset("cylinder_block", "a plain upright cylinder (pillars, silos, cans)", ["generic"], aliases=["pillar", "column"])
def cylinder_block(r=0.5, h=1.5, color="#9aa3ab"):
    return Model().add("body", M.cylinder(r, h, 14), col(color, C["gray"]))


@asset("ball", "a low poly sphere (balls, planets, drops, blobs)", ["generic"], aliases=["sphere", "orb"])
def ball(r=0.5, color="#3aa6d9", glow=0.0):
    return Model().add("body", M.xf(M.sphere(r, 1), (0, r, 0)), col(color, C["blue"]), emissive=float(glow))


@asset("platform", "a low round stage that groups the objects of one area", ["generic", "terrain"],
       aliases=["stage", "base"])
def platform(r=6.0, color="#16444b"):
    m = Model().add("slab", M.cylinder(r, 0.12, 40), col(color, "#16444b"))
    m.add("rim", M.xf(M.torus(r, 0.05, 40, 4), (0, 0.12, 0)), "#2ee6d6", emissive=0.6)
    return m


@asset("ground", "a flat patch of ground (grass, dirt, sand, concrete)", ["terrain"],
       aliases=["field", "grass", "lawn", "soil", "dirt"])
def ground(w=10.0, d=10.0, color="grass"):
    return Model().add("top", M.box(w, 0.1, d, base=True), col(color, C["grass"]))


@asset("arrow", "a glowing 3D arrow (direction, flow, 'this goes there')", ["symbol"], aliases=["pointer"])
def arrow(length=2.0, color="#2ee6d6", glow=0.8):
    m = Model().add("shaft", M.xf(M.cylinder(0.12, length * 0.7, 8), r=(0, 0, -90)), col(color, C["teal"]),
                    emissive=float(glow))
    m.add("head", M.xf(M.cone(0.3, length * 0.3, 10), (length * 0.7, 0, 0), (0, 0, -90)), col(color, C["teal"]),
          emissive=float(glow))
    return Model(parts=[_lift(p, 0.4) for p in m.parts])


def _lift(part, dy):
    part.geo = M.xf(part.geo, (0, dy, 0))
    return part


@asset("sign_number", "a big glowing ring used to show a number or a key point (the number goes in a label)",
       ["symbol"], aliases=["badge", "marker"])
def sign_number(r=1.0, color="#f4c430"):
    m = Model().add("ring", M.xf(M.torus(r, 0.12, 24, 6), (0, r + 0.3, 0), (90, 0, 0)), col(color, C["yellow"]),
                    emissive=0.7)
    m.add("post", M.cylinder(0.06, 0.4, 6), C["steel"])
    return m


@asset("bolt", "a lightning bolt (electricity, power, energy)", ["energy", "symbol"],
       aliases=["lightning", "electricity", "power_symbol", "spark"])
def bolt(h=2.0, color="#ffd76b"):
    return Model().add("bolt", M.xf(M.bolt(h, h * 0.45, 0.25), (0, h * 0.55, 0)), col(color, C["lamp"]),
                       emissive=1.0, kind="light")


# ---------------------------------------------------------------------------
# Farm
# ---------------------------------------------------------------------------


@asset("cow", "a dairy cow (white with black spots)", ["animal", "farm"], aliases=["cattle", "bull", "calf", "cows"])
def cow(color="white", spots="black", seed=1):
    """A blocky dairy cow (head toward +x): white with black patches, ears, pink muzzle and udder, tail."""
    white, black, pink = col(color, "#f2f1ec"), col(spots, "#26262b"), "#f0a0ac"
    rng = np.random.default_rng(int(seed))
    m = Model()
    for x in (-0.62, 0.62):
        for z in (-0.27, 0.27):
            m.add("leg", M.xf(M.box(0.2, 0.72, 0.2, base=True), (x, 0.08, z)), white)
            m.add("hoof", M.xf(M.box(0.22, 0.1, 0.22, base=True), (x, 0, z)), black)
    m.add("body", M.xf(M.box(1.9, 0.86, 0.9, base=True), (0, 0.78, 0)), white)
    for k in range(3):  # black patches on both sides and on the back
        w, h = rng.uniform(0.35, 0.6), rng.uniform(0.28, 0.45)
        x, y = rng.uniform(-0.6, 0.55), rng.uniform(1.0, 1.45)
        for z in (-0.457, 0.457):
            m.add("patch", M.xf(M.box(w, h, 0.02), (x, y, z)), black)
    m.add("patch", M.xf(M.box(0.6, 0.02, 0.5), (rng.uniform(-0.4, 0.3), 1.645, rng.uniform(-0.12, 0.12))), black)
    m.add("neck", M.xf(M.box(0.4, 0.45, 0.5, base=True), (0.95, 1.15, 0)), white)
    m.add("head", M.xf(M.box(0.55, 0.52, 0.5, base=True), (1.22, 1.2, 0)), white)
    m.add("head_patch", M.xf(M.box(0.3, 0.3, 0.52, base=True), (1.12, 1.42, 0)), black)
    m.add("muzzle", M.xf(M.box(0.18, 0.28, 0.44, base=True), (1.56, 1.2, 0)), pink)
    m.add("nostril", M.xf(M.box(0.02, 0.06, 0.06), (1.655, 1.36, -0.1)), "#b5606e")
    m.add("nostril", M.xf(M.box(0.02, 0.06, 0.06), (1.655, 1.36, 0.1)), "#b5606e")
    for z in (-0.18, 0.18):
        m.add("eye", M.xf(M.box(0.03, 0.09, 0.07), (1.5, 1.56, z)), "#15151a")
    for z in (-0.34, 0.34):
        m.add("ear", M.xf(M.box(0.14, 0.1, 0.24), (1.14, 1.62, z)), white)
        m.add("ear_in", M.xf(M.box(0.1, 0.02, 0.16), (1.14, 1.56, z * 1.05)), pink)
    m.add("udder", M.xf(M.box(0.42, 0.2, 0.38, base=True), (-0.42, 0.6, 0)), pink)
    for x in (-0.55, -0.3):
        for z in (-0.1, 0.1):
            m.add("teat", M.xf(M.box(0.05, 0.1, 0.05, base=True), (x, 0.5, z)), "#e3889a")
    m.add("tail", M.xf(M.box(0.06, 0.72, 0.06, base=True), (-0.98, 0.95, 0), (0, 0, -8)), white)
    m.add("tail_tip", M.xf(M.box(0.12, 0.18, 0.12, base=True), (-0.96, 0.84, 0)), black)
    m.anchors["rear"] = (-1.05, 0.95, 0.0)
    m.anchors["label"] = (0.0, 2.15, 0.0)
    return m


@asset("barn", "an open dairy barn (free-stall shed: roof on posts, low walls, cows can be inside)", ["farm", "building"],
       aliases=["shed", "stable", "farm_building", "free_stall"])
def barn(length=18.0, width=11.0, color="#c9ced3", roof="roof", h=3.6):
    """An open dairy barn: concrete floor, steel posts and roof trusses, feed rail, stall rails, manure alley,
    hanging lamps (warm light). Cows go in a row along x at z ≈ -1.6, facing the feed rail (rot 90)."""
    steel, L, W = col(color, "#c9ced3"), float(length), float(width)
    m = Model()
    m.add("slab", M.box(L + 1.2, 0.12, W + 1.2, base=True), "#9aa1a6")
    m.add("feed_alley", M.xf(M.box(L, 0.03, 2.6, base=True), (0, 0.12, -W / 2 + 1.4)), "#b7ab84")
    m.add("feed", M.xf(M.box(L - 0.6, 0.14, 0.5, base=True), (0, 0.12, -W / 2 + 2.3)), "#c8b45a")
    m.add("alley", M.xf(M.box(L, 0.03, 2.4, base=True), (0, 0.12, 0.6)), "#6b5236")
    m.add("kerb", M.xf(M.box(L, 0.25, 0.25, base=True), (0, 0.12, -0.6)), "#8a9196")
    rail_z = -W / 2 + 2.75
    for y in (0.75, 1.15):
        m.add("feed_rail", M.xf(M.box(L, 0.07, 0.07), (0, y, rail_z)), steel)
    n_bars = int(L / 0.75)
    m.add("bars", M.merge(*[M.xf(M.box(0.05, 1.15, 0.05, base=True), (-L / 2 + 0.3 + k * (L - 0.6) / n_bars, 0.12, rail_z))
                           for k in range(n_bars + 1)]), steel)
    stalls = int(L / 1.6)
    for k in range(stalls + 1):  # stall dividers (curved rails seen from the side)
        x = -L / 2 + 0.4 + k * (L - 0.8) / stalls
        m.add("stall", M.tube([(x, 0.15, rail_z + 0.2), (x, 1.05, rail_z + 0.4), (x, 1.05, rail_z + 1.6),
                               (x, 0.6, rail_z + 2.2)], 0.035, 5, joints=False), steel)
    posts = max(3, int(L / 3.6) + 1)
    xs = [-L / 2 + k * L / (posts - 1) for k in range(posts)]
    rise = W * 0.22
    for x in xs:
        for z in (-W / 2, W / 2):
            m.add("post", M.xf(M.box(0.18, h, 0.18, base=True), (x, 0.12, z)), steel, shell=True)
        top = 0.12 + h
        rafters = [((x, top, -W / 2), (x, top + rise, 0)), ((x, top, W / 2), (x, top + rise, 0)),
                   ((x, top, -W / 2), (x, top, W / 2)), ((x, top, 0), (x, top + rise, 0)),
                   ((x, top, -W / 4), (x, top + rise / 2, -W / 4)), ((x, top, W / 4), (x, top + rise / 2, W / 4)),
                   ((x, top, -W / 4), (x, top + rise, 0)), ((x, top, W / 4), (x, top + rise, 0))]
        m.add("truss", M.merge(*[M.tube([a, b], 0.06, 4, joints=False) for a, b in rafters]), steel, shell=True)
    for z, y in ((-W / 2, h + 0.12), (W / 2, h + 0.12), (0, h + 0.12 + rise), (-W / 4, h + 0.12 + rise / 2),
                 (W / 4, h + 0.12 + rise / 2)):
        m.add("purlin", M.xf(M.box(L + 0.4, 0.1, 0.1), (0, y, z)), steel, shell=True)
    m.add("roof", M.merge(M.xf(M.box(L + 0.6, 0.05, W / 2 * 1.05), (0, h + 0.12 + rise / 2 + 0.08, -W / 4), (math.degrees(
        math.atan2(rise, W / 2)), 0, 0)), M.xf(M.box(L + 0.6, 0.05, W / 2 * 1.05), (0, h + 0.12 + rise / 2 + 0.08, W / 4),
                                               (-math.degrees(math.atan2(rise, W / 2)), 0, 0))),
          col(roof, "#4b3b47"), opacity=0.22, shell=True)
    for x in xs[1:-1] if len(xs) > 2 else xs:
        m.add("lamp_cord", M.xf(M.box(0.03, 0.8, 0.03, base=True), (x, h + rise - 0.6, 0)), "#3a3f45")
        m.add("lamp", M.xf(M.cone(0.32, 0.25, 10), (x, h + rise - 0.72, 0)), "#ffd98a", emissive=0.9, kind="lamp")
    m.anchors["label"] = (0.0, h + rise + 1.0, 0.0)
    m.anchors["inside"] = (0.0, 1.2, 0.0)
    return m


@asset("manure", "a pile of cow manure (lumpy brown blobs; use 'grow' to make it pile up)", ["farm", "waste"],
       aliases=["poop", "dung", "manure_pile", "waste_pile", "slurry_pile"])
def manure(size=1.0, color="manure", seed=3):
    rng = np.random.default_rng(int(seed))
    parts = []
    for _ in range(7):
        r = rng.uniform(0.25, 0.45) * size
        x, z = rng.uniform(-0.55, 0.55) * size, rng.uniform(-0.45, 0.45) * size
        parts.append(M.xf(M.jitter(M.sphere(r, 1), r * 0.12, int(rng.integers(999))), (x, r * 0.55, z), s=(1, 0.7, 1)))
    m = Model().add("pile", M.merge(*parts), col(color, C["manure"]))
    m.add("dark", M.xf(M.sphere(0.3 * size, 0), (0.1, 0.45 * size, 0.05), s=(1.2, 0.6, 1)), C["dark_brown"])
    return m


@asset("scraper", "a manure scraper blade that slides along the barn alley", ["farm", "machine"],
       aliases=["alley_scraper", "blade"])
def scraper(width=2.2, color="yellow"):
    """The moving blade of an alley scraper (it pushes manure along +x). Its rail, chain and motor are added by
    the world (logic.assemblies) along the path it travels."""
    m = Model().add("blade", M.xf(M.box(0.18, 0.55, width, base=True), (0, 0, 0), (0, 0, -12)), col(color, C["yellow"]))
    m.add("frame", M.merge(M.xf(M.box(0.9, 0.14, 0.24, base=True), (-0.45, 0.05, 0)),
                           M.xf(M.box(0.14, 0.4, width * 0.8, base=True), (-0.6, 0.05, 0))), C["dark_steel"])
    m.add("shoe", M.xf(M.box(0.5, 0.08, 0.34, base=True), (-0.45, 0, 0)), "#3a3f45")
    m.anchors["blade"] = (0.25, 0.3, 0.0)
    m.anchors["blade_half"] = (width / 2, 0.0, 0.0)
    m.anchors["label"] = (0.0, 1.3, 0.0)
    return m


@asset("tractor", "a farm tractor (big rear wheels, cab, exhaust)", ["farm", "vehicle"],
       aliases=["farm_tractor", "loader"])
def tractor(color="green", cab="#8ecfe8"):
    """A farm tractor (front toward +x): big rear wheels, glass cab, exhaust."""
    body = col(color, "#3fae3a")
    m = Model()
    m.add("chassis", M.xf(M.box(3.0, 0.35, 0.9, base=True), (0.3, 0.55, 0)), "#2e3238")
    m.add("hood", M.xf(M.box(1.8, 0.85, 1.0, base=True), (1.0, 0.85, 0)), body)
    m.add("grille", M.xf(M.box(0.06, 0.6, 0.8, base=True), (1.92, 0.95, 0)), "#2e3238")
    m.add("light", M.xf(M.box(0.05, 0.14, 0.14), (1.94, 1.55, -0.35)), "#ffe9a8", emissive=0.3, kind="light")
    m.add("light", M.xf(M.box(0.05, 0.14, 0.14), (1.94, 1.55, 0.35)), "#ffe9a8", emissive=0.3, kind="light")
    m.add("cab_base", M.xf(M.box(1.4, 0.55, 1.5, base=True), (-0.75, 0.85, 0)), body)
    m.add("glass", M.xf(M.box(1.3, 1.15, 1.4, base=True), (-0.75, 1.4, 0)), col(cab, "#8ecfe8"), opacity=0.75)
    for x in (-1.38, -0.12):
        for z in (-0.68, 0.68):
            m.add("pillar", M.xf(M.box(0.08, 1.15, 0.08, base=True), (x, 1.4, z)), body)
    m.add("cab_roof", M.xf(M.box(1.55, 0.14, 1.6, base=True), (-0.75, 2.55, 0)), body)
    m.add("exhaust", M.xf(M.cylinder(0.07, 1.0, 8), (1.35, 1.65, 0.3)), "#2a2a2e")
    # front loader: arms + bucket (it scoops and carries; "load" is shown with show_part while it carries)
    for z in (-0.62, 0.62):
        m.add("arm", M.tube([(0.2, 1.6, z), (2.3, 0.75, z), (2.55, 0.45, z)], 0.07, 5, joints=False), "#d9b43a")
    m.add("bucket", M.merge(M.xf(M.box(0.7, 0.08, 1.7, base=True), (2.75, 0.12, 0)),
                            M.xf(M.box(0.08, 0.7, 1.7, base=True), (2.42, 0.12, 0)),
                            M.xf(M.box(0.7, 0.55, 0.08, base=True), (2.75, 0.12, 0.85)),
                            M.xf(M.box(0.7, 0.55, 0.08, base=True), (2.75, 0.12, -0.85))), "#d9b43a")
    m.add("load", M.merge(*[M.xf(M.sphere(0.32, 0), (2.7 + dx, 0.45, dz), s=(1, 0.6, 1)) for dx, dz in
                            ((0, -0.45), (0.1, 0.05), (-0.05, 0.5), (0.12, 0.3))]), C["manure"], kind="load")
    m.anchors["blade"] = (3.1, 0.3, 0.0)
    m.anchors["blade_half"] = (0.85, 0.0, 0.0)
    for x, z, r, w in ((-0.95, 0.95, 0.88, 0.5), (-0.95, -0.95, 0.88, 0.5), (1.35, 0.78, 0.5, 0.32),
                       (1.35, -0.78, 0.5, 0.32)):
        c = (x, r, z)
        m.add("wheel", M.xf(M.cylinder(r, w, 16, base=False), c, (90, 0, 0)), "#2a2a2e", kind="wheel", axis="z", pivot=c)
        m.add("hub", M.xf(M.cylinder(r * 0.45, w + 0.04, 12, base=False), c, (90, 0, 0)), "#e7e3d6", kind="wheel",
              axis="z", pivot=c)
    m.anchors["label"] = (0.0, 3.2, 0.0)
    m.anchors["exhaust"] = (1.35, 2.7, 0.3)
    return m


@asset("tank", "an open round storage tank / lagoon (liquid inside; crust=True adds a floating crust)",
       ["farm", "industry", "container"], aliases=["storage_tank", "lagoon", "pit", "manure_storage", "pool", "basin"])
def tank(r=4.0, h=3.0, color="#e6e9eb", liquid="#6b4a2c", level=0.75, crust=False, seed=5):
    """A round open slurry/storage tank: white banded wall, walkway bridge with railings."""
    wall_c = col(color, "#e6e9eb")
    m = Model()
    wall = M.merge(M.cylinder(r, h, 32, caps=False), M.cylinder(r * 0.95, h, 32, caps=False))
    m.add("wall", wall, wall_c, shell=True)
    for y in np.arange(0.75, h, 0.9):
        m.add("band", M.xf(M.torus(r * 1.005, 0.045, 32, 4), (0, float(y), 0)), "#aeb6bd", shell=True)
    m.add("rim", M.xf(M.torus(r * 0.975, 0.11, 32, 4), (0, h, 0)), "#f4f6f7", shell=True)
    m.add("floor", M.cylinder(r * 0.96, 0.06, 32), "#6c7378")
    lv = max(0.05, min(1.0, float(level))) * h * 0.95
    m.add("liquid", M.cylinder(r * 0.94, lv, 32), col(liquid, C["manure"]), kind="liquid")
    if crust:
        rng = np.random.default_rng(int(seed))
        lumps = [M.xf(M.jitter(M.sphere(rng.uniform(0.35, 0.7), 0), 0.08, int(rng.integers(99))),
                      (rng.uniform(-0.62, 0.62) * r, lv + 0.05, rng.uniform(-0.62, 0.62) * r), s=(1.3, 0.32, 1.3))
                 for _ in range(22)]
        m.add("crust", M.merge(M.xf(M.cylinder(r * 0.92, 0.1, 24), (0, lv - 0.02, 0)), *lumps), C["crust"], kind="crust")
    m.add("bridge", M.xf(M.box(r * 1.25, 0.1, 0.8), (-r * 0.4, h + 0.15, 0)), "#9aa3ab")
    for z in (-0.4, 0.4):
        m.add("railing", M.xf(M.box(r * 1.25, 0.05, 0.05), (-r * 0.4, h + 1.0, z)), "#c9ced3")
        m.add("posts", M.merge(*[M.xf(M.box(0.05, 0.85, 0.05, base=True), (-r * 1.0 + k * r * 0.3, h + 0.15, z))
                                  for k in range(5)]), "#c9ced3")
    m.add("ladder", M.merge(M.xf(M.box(0.05, h + 1.0, 0.05, base=True), (-r - 0.15, 0, -0.25)),
                            M.xf(M.box(0.05, h + 1.0, 0.05, base=True), (-r - 0.15, 0, 0.25)),
                            *[M.xf(M.box(0.05, 0.04, 0.5), (-r - 0.15, 0.3 * k, 0)) for k in range(1, int(h / 0.3) + 3)]),
          "#9aa3ab")
    m.anchors["label"] = (0.0, h + 1.6, 0.0)
    m.anchors["inlet"] = (-r, h * 0.9, 0.0)
    m.anchors["outlet"] = (r, h * 0.4, 0.0)
    m.anchors["surface"] = (0.0, lv, 0.0)
    return m


@asset("agitator", "a mixer: motor on top, shaft and propeller blades that spin (mixing liquid)",
       ["farm", "machine", "industry"], aliases=["mixer", "stirrer", "propeller", "impeller"])
def agitator(h=3.0, color="orange"):
    m = Model()
    m.add("motor", M.xf(M.cylinder(0.35, 0.6, 10), (0, h, 0)), col(color, C["orange"]))
    m.add("shaft", M.cylinder(0.07, h, 8), C["steel"], kind="blade", axis="y")
    blades = M.merge(*[M.xf(M.box(0.9, 0.05, 0.28), (0.5, 0.6, 0), (25, a, 0)) for a in (0, 120, 240)])
    m.add("blades", blades, C["yellow"], kind="blade", axis="y")
    m.anchors["label"] = (0.0, h + 1.0, 0.0)
    return m


@asset("digester", "a biogas digester: big closed tank with a gas dome on top (cutaway shows liquid, bacteria, gas)",
       ["energy", "industry", "farm"], aliases=["biodigester", "anaerobic_digester", "biogas_plant", "reactor"])
def digester(r=4.5, h=4.0, color="#e9ecee", dome="#f4f1e8", liquid="#5a3d24", level=0.72):
    """A biogas digester: white banded tank with a gas dome (cutaway shows liquid, bacteria, gas)."""
    m = Model()
    m.add("wall", M.cylinder(r, h, 32, caps=False), col(color, "#e9ecee"), shell=True)
    for y in np.arange(0.8, h, 1.0):
        m.add("band", M.xf(M.torus(r * 1.006, 0.05, 32, 4), (0, float(y), 0)), "#aeb6bd", shell=True)
    m.add("ring", M.xf(M.torus(r * 1.01, 0.12, 32, 4), (0, h, 0)), "#8f9ba8", shell=True)
    dome_g = M.lathe([(r, 0), (r * 0.95, r * 0.28), (r * 0.8, r * 0.5), (r * 0.55, r * 0.66), (r * 0.25, r * 0.74),
                      (0.0, r * 0.76)], 32, close_bottom=False)
    m.add("dome", M.xf(dome_g, (0, h, 0)), col(dome, "#f4f1e8"), shell=True)
    m.add("floor", M.cylinder(r * 0.98, 0.08, 32), "#4b5257")
    lv = h * float(level)
    m.add("liquid", M.cylinder(r * 0.97, lv, 32), col(liquid, "#5a3d24"), kind="liquid")
    m.add("gas", M.xf(dome_g, (0, h, 0), s=(0.96, 0.92, 0.96)), C["gas"], opacity=0.25, kind="gas")
    m.add("pipe_out", M.tube([(0, h + r * 0.76, 0), (0, h + r * 0.76 + 0.6, 0), (r + 1.2, h + r * 0.76 + 0.6, 0)],
                             0.18, 8), C["yellow"])
    m.add("hatch", M.xf(M.box(0.9, 1.4, 0.1, base=True), (0, 0.1, r + 0.02)), "#8f9ba8")
    m.anchors["label"] = (0.0, h + r * 0.76 + 1.4, 0.0)
    m.anchors["gas_out"] = (r + 1.2, h + r * 0.76 + 0.6, 0.0)
    m.anchors["inlet"] = (-r, h * 0.6, 0.0)
    m.anchors["inside"] = (0.0, lv * 0.5, 0.0)
    return m


@asset("bacteria", "microbes: rod-shaped bacteria with tails (zoomed in, inside liquid)",
       ["micro", "biology"], aliases=["bacterium", "microbe", "microbes", "germ", "germs", "archaea", "bug"])
def bacteria(color="#7bdc66", length=1.6, seed=2):
    m = Model()
    m.add("body", M.xf(M.capsule(0.32, length, 10), (0, 0.6, 0)), col(color, "#7bdc66"), emissive=0.15)
    rng = np.random.default_rng(int(seed))
    for k in range(3):
        y, z = 0.6 + rng.uniform(-0.15, 0.15), rng.uniform(-0.2, 0.2)
        pts = [(-length / 2 - 0.25, y, z)] + [(-length / 2 - 0.35 - 0.3 * i, y + 0.18 * math.sin(i * 1.7 + k), z)
                                              for i in range(1, 4)]
        m.add("tail", M.tube(pts, 0.035, 4, joints=False), "#d9f7c9", kind="blade", axis="x")
    m.add("dots", M.merge(*[M.xf(M.sphere(0.07, 0), (rng.uniform(-0.5, 0.5) * length, 0.6 + rng.uniform(-0.12, 0.2),
                                                       0.27)) for _ in range(4)]), "#2f7d33")
    return m


@asset("methane", "a methane molecule CH4 (1 carbon, 4 hydrogen) = biogas / natural gas",
       ["micro", "chemistry", "energy"], aliases=["ch4", "biogas_molecule", "gas_molecule", "natural_gas"])
def methane(scale=1.0):
    m = Model()
    c = (0, 0.9 * scale, 0)
    m.add("carbon", M.xf(M.sphere(0.32 * scale, 1), c), "#3b3f46")
    dirs = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], np.float32) / math.sqrt(3)
    for d in dirs:
        p = np.asarray(c) + d * 0.62 * scale
        m.add("hydrogen", M.xf(M.sphere(0.2 * scale, 1), tuple(p)), C["white"])
        m.add("bond", M.tube([c, tuple(np.asarray(c) + d * 0.45 * scale)], 0.06 * scale, 6, joints=False), "#cfd6dc")
    return m


@asset("pipe", "a pipe between two points (length along +X, can bend up); flow particles travel inside",
       ["industry", "connection"], aliases=["gas_pipe", "tube", "pipeline", "hose", "duct"])
def pipe(length=6.0, rise=0.0, r=0.22, color="yellow", height=0.6):
    pts = [(0, height, 0), (length * 0.5, height, 0), (length * 0.5, height + rise, 0), (length, height + rise, 0)] \
        if rise else [(0, height, 0), (length, height, 0)]
    m = Model().add("pipe", M.tube(pts, r, 10), col(color, C["yellow"]), shell=True)
    for p in pts[:1] + pts[-1:]:
        m.add("flange", M.xf(M.cylinder(r * 1.5, 0.12, 10, base=False), p, (0, 0, 90)), C["dark_steel"])
    m.paths["flow"] = [tuple(map(float, p)) for p in pts]
    m.anchors["start"] = tuple(map(float, pts[0]))
    m.anchors["end"] = tuple(map(float, pts[-1]))
    m.anchors["label"] = (length / 2, height + rise + 0.9, 0.0)
    return m


@asset("generator", "an engine-generator set (burns gas, makes electricity): engine block, fan grille, exhaust, panel",
       ["energy", "machine"], aliases=["genset", "engine_generator", "power_generator", "chp", "dynamo"])
def generator(color="#2f6fd6", length=3.6):
    """An engine-generator set (burns gas, makes electricity): engine, fan, exhaust, control panel, on a skid."""
    body_c = col(color, "#2f6fd6")
    m = Model()
    m.add("skid", M.box(length + 0.6, 0.3, 1.9, base=True), "#8f9ba8")
    m.add("body", M.xf(M.box(length * 0.55, 1.5, 1.4, base=True), (-length * 0.2, 0.3, 0)), body_c)
    m.add("alternator", M.xf(M.cylinder(0.7, length * 0.4, 18, base=False), (length * 0.27, 1.05, 0), (0, 0, 90)),
          "#d9dde0")
    for k in range(6):
        m.add("grille", M.xf(M.box(0.05, 1.0, 1.42), (-length * 0.42 + k * 0.16, 1.05, 0)), "#24539f")
    m.add("fan", M.xf(M.merge(*[M.xf(M.box(0.05, 0.9, 0.18), (0, 0, 0), (a, 0, 0)) for a in (0, 60, 120)]),
                      (length / 2 + 0.05, 1.05, 0)), C["dark_steel"], kind="blade", axis="x",
          pivot=(length / 2 + 0.05, 1.05, 0))
    m.add("exhaust", M.xf(M.cylinder(0.12, 1.2, 8), (-length * 0.3, 1.8, 0.3)), C["black"])
    m.add("panel", M.xf(M.box(0.7, 0.9, 0.12, base=True), (-length * 0.25, 0.6, 0.8)), "#3a4450")
    m.add("screen", M.xf(M.box(0.45, 0.3, 0.04), (-length * 0.25, 1.15, 0.87)), "#7df0ff", kind="light")
    m.anchors["exhaust"] = (-length * 0.3, 3.0, 0.3)
    m.anchors["inlet"] = (-length / 2, 1.0, 0.0)
    m.anchors["outlet"] = (length / 2, 1.2, 0.0)
    m.anchors["label"] = (0.0, 2.8, 0.0)
    return m


@asset("power_pole", "a wooden power pole with a cross arm and insulators (wires go between poles)",
       ["energy", "city"], aliases=["utility_pole", "pole", "electric_pole"])
def power_pole(h=6.0):
    m = Model().add("pole", M.cylinder(0.14, h, 8), C["wood"])
    m.add("arm", M.xf(M.box(0.18, 0.18, 2.2), (0, h - 0.4, 0)), C["wood"])
    for z in (-0.9, 0, 0.9):
        m.add("insulator", M.xf(M.cylinder(0.08, 0.25, 6), (0, h - 0.3, z)), "#8fd3e8")
    m.anchors["wire"] = (0.0, h - 0.05, 0.0)
    m.anchors["label"] = (0.0, h + 0.6, 0.0)
    return m


@asset("wire", "a power cable that sags between two heights (length along +X); sparks travel along it",
       ["energy", "connection"], aliases=["cable", "power_cable", "line", "electric_wire"])
def wire(length=6.0, h1=6.0, h2=6.0, sag=0.5, color="#1f2428"):
    pts = []
    for k in range(9):
        u = k / 8
        pts.append((length * u, h1 + (h2 - h1) * u - sag * 4 * u * (1 - u), 0.0))
    m = Model().add("cable", M.tube(pts, 0.04, 5, joints=False), col(color, "#1f2428"))
    m.paths["flow"] = pts
    m.anchors["start"], m.anchors["end"] = pts[0], pts[-1]
    m.anchors["label"] = (length / 2, max(h1, h2) + 0.6, 0.0)
    return m


@asset("house", "a small house (windows light up with 'light_on')", ["city", "building"],
       aliases=["home", "homes", "cottage", "building_small", "houses", "town", "village", "city", "neighborhood"])
def house(w=5.0, d=4.4, h=3.0, color="#f3e3c3", roof="#b5523b", seed=1):
    rng = np.random.default_rng(int(seed))
    m = Model()
    m.add("walls", M.box(w, h, d, base=True), col(color, "#f3e3c3"), shell=True)
    m.add("roof", M.xf(M.prism_roof(w + 0.5, d + 0.5, h * 0.55), (0, h, 0)), col(roof, "#b5523b"), shell=True)
    m.add("chimney", M.xf(M.box(0.45, 1.2, 0.45, base=True), (w * 0.25, h + 0.4, -d * 0.15)), "#8c4a3a")
    m.add("door", M.xf(M.box(0.8, 1.6, 0.06, base=True), (rng.uniform(-0.6, 0.6), 0, d / 2 + 0.03)), "#6b4a2c")
    for x in (-w * 0.3, w * 0.3):
        m.add("window", M.xf(M.box(0.75, 0.75, 0.06), (x, h * 0.55, d / 2 + 0.03)), "#2b3a4a", kind="light")
    for z in (-d * 0.2, d * 0.2):
        m.add("window", M.xf(M.box(0.06, 0.7, 0.7), (w / 2 + 0.03, h * 0.55, z)), "#2b3a4a", kind="light")
    m.anchors["label"] = (0.0, h * 1.55 + 0.6, 0.0)
    m.anchors["power"] = (-w / 2, h * 0.92, 0.0)
    return m


@asset("tree", "a low poly tree (round or pine)", ["nature"], aliases=["trees", "pine", "bush", "forest"])
def tree(h=3.0, kind="round", color="tree", seed=1):
    m = Model().add("trunk", M.cylinder(0.14 * h / 3, h * 0.45, 6), C["trunk"])
    if kind == "pine":
        for k in range(3):
            m.add("leaves", M.xf(M.cone(h * (0.32 - 0.07 * k), h * 0.4, 8), (0, h * (0.3 + 0.2 * k), 0)),
                  col(color, "#2f8f4e"))
    else:
        m.add("leaves", M.xf(M.jitter(M.sphere(h * 0.3, 1), h * 0.03, int(seed)), (0, h * 0.7, 0)), col(color, C["tree"]))
    return m


@asset("lightbulb", "a light bulb (glows with 'light_on')", ["energy", "symbol"], aliases=["bulb", "lamp", "light"])
def lightbulb(size=1.0):
    m = Model().add("glass", M.xf(M.sphere(0.45 * size, 1), (0, 1.0 * size, 0)), "#fff3c4", kind="light", opacity=0.9)
    m.add("base", M.xf(M.cylinder(0.22 * size, 0.35 * size, 10), (0, 0.35 * size, 0)), C["steel"])
    m.add("stand", M.cylinder(0.05 * size, 0.4 * size, 6), C["dark_steel"])
    return m


@asset("fence", "a short wooden fence section", ["farm"], aliases=["railing"])
def fence(length=6.0, color="wood"):
    m = Model()
    for x in np.linspace(-length / 2, length / 2, max(2, int(length / 1.2) + 1)):
        m.add("post", M.xf(M.box(0.12, 1.0, 0.12, base=True), (x, 0, 0)), col(color, C["wood"]))
    for y in (0.45, 0.85):
        m.add("rail", M.xf(M.box(length, 0.1, 0.06), (0, y, 0)), col(color, C["wood"]))
    return m


@asset("truck", "a truck / tanker truck (cab + tank or box)", ["vehicle", "city"], aliases=["lorry", "tanker", "spreader"])
def truck(color="#3d8fd6", cargo="tank"):
    c = col(color, C["blue"])
    m = Model()
    m.add("cab", M.xf(M.box(1.4, 1.6, 1.8, base=True), (1.9, 0.55, 0)), c)
    m.add("window", M.xf(M.box(0.06, 0.6, 1.5), (2.62, 1.75, 0)), "#bfe9ff", opacity=0.7)
    m.add("chassis", M.xf(M.box(5.0, 0.3, 1.6, base=True), (0, 0.45, 0)), C["dark_steel"])
    if cargo == "tank":
        m.add("cargo", M.xf(M.cylinder(0.85, 3.2, 14, base=False), (-0.6, 1.6, 0), (0, 0, 90)), C["steel"])
    else:
        m.add("cargo", M.xf(M.box(3.3, 1.8, 1.8, base=True), (-0.6, 0.75, 0)), "#e9edf0")
    for x in (-1.8, -0.9, 1.9):
        for z in (-0.8, 0.8):
            m.add("wheel", M.xf(M.cylinder(0.42, 0.3, 12, base=False), (x, 0.42, z), (90, 0, 0)), C["black"],
                  kind="wheel", pivot=(x, 0.42, z), axis="z")
    m.anchors["label"] = (0.0, 3.2, 0.0)
    return m


@asset("person", "a simple low poly person (worker, farmer, scientist)", ["people"],
       aliases=["man", "woman", "worker", "farmer", "human", "people", "scientist", "engineer"])
def person(shirt="#d9534f", pants="#2f5fa8", skin="skin", hat="", hair="#5a3a22", height=1.8, overalls=False,
           stripes=False, seed=1, mood="neutral"):
    """A simple blocky person (face toward +x): big square head with eyes and mouth, hair, shirt, pants."""
    s = height / 1.8
    sk, sh, pa = col(skin, C["skin"]), col(shirt, C["red"]), col(pants, "#2f5fa8")
    m = Model()
    for z in (-0.13, 0.13):
        m.add("leg", M.xf(M.box(0.22, 0.72 * s, 0.24, base=True), (0, 0.08 * s, z)), pa)
        m.add("shoe", M.xf(M.box(0.32, 0.1 * s, 0.26, base=True), (0.04, 0, z)), "#2a2a2e")
    m.add("torso", M.xf(M.box(0.34, 0.62 * s, 0.58, base=True), (0, 0.8 * s, 0)), sh)
    if stripes:
        for k in range(3):
            m.add("stripe", M.xf(M.box(0.35, 0.06 * s, 0.59), (0, (0.95 + 0.17 * k) * s, 0)), "#8c2f2a")
    if overalls:
        m.add("bib", M.xf(M.box(0.02, 0.36 * s, 0.38, base=True), (0.18, 0.86 * s, 0)), pa)
    for z in (-0.38, 0.38):
        m.add("arm", M.xf(M.box(0.18, 0.58 * s, 0.18, base=True), (0, 0.84 * s, z)), sh)
        m.add("hand", M.xf(M.box(0.16, 0.14 * s, 0.16, base=True), (0, 0.7 * s, z)), sk)
    m.add("head", M.xf(M.box(0.5, 0.48 * s, 0.5, base=True), (0, 1.43 * s, 0)), sk)
    big = mood in ("surprised", "scared")
    for z in (-0.11, 0.11):  # eyes, eyebrows and mouth show the feeling (story characters)
        m.add("eye", M.xf(M.box(0.02, (0.11 if big else 0.08) * s, 0.07 if big else 0.06), (0.255, 1.7 * s, z)),
              "#1c1c22")
        tilt = {"angry": 22, "sad": -18, "scared": -12}.get(mood, 0) * (1 if z > 0 else -1)
        lift = {"surprised": 0.05, "scared": 0.04}.get(mood, 0.0)
        m.add("brow", M.xf(M.box(0.02, 0.025 * s, 0.11), (0.257, (1.79 + lift) * s, z), (tilt, 0, 0)), "#2a1d14")
    mouth = "#7a3b32"
    if mood in ("surprised", "scared"):
        m.add("mouth", M.xf(M.box(0.02, 0.07 * s, 0.07), (0.255, 1.555 * s, 0)), "#4a1f1a")
    elif mood in ("happy", "sad"):
        up = 1 if mood == "happy" else -1
        m.add("mouth", M.xf(M.box(0.02, 0.03 * s, 0.12), (0.255, 1.555 * s, 0)), mouth)
        for z in (-0.075, 0.075):
            m.add("mouth", M.xf(M.box(0.02, 0.03 * s, 0.04), (0.255, (1.555 + 0.025 * up) * s, z)), mouth)
    else:
        m.add("mouth", M.xf(M.box(0.02, 0.03 * s, 0.14 if mood != "angry" else 0.1), (0.255, 1.56 * s, 0)), mouth)
    if hat:
        m.add("hat", M.xf(M.box(0.56, 0.12 * s, 0.56, base=True), (0, 1.9 * s, 0)), col(hat, C["yellow"]))
        m.add("brim", M.xf(M.box(0.3, 0.04 * s, 0.56, base=True), (0.36, 1.9 * s, 0)), col(hat, C["yellow"]))
    else:
        m.add("hair", M.merge(M.xf(M.box(0.54, 0.13 * s, 0.54, base=True), (-0.01, 1.89 * s, 0)),
                              M.xf(M.box(0.12, 0.3 * s, 0.54, base=True), (-0.22, 1.62 * s, 0))), col(hair, "#5a3a22"))
    m.anchors["label"] = (0.0, 2.35 * s, 0.0)
    return m


# Real sizes (largest side, meters) of objects whose library model is drawn bigger or smaller than life. The plan
# checker scales them to real size, so a bottle is never bigger than the person holding it.
REAL_SIZE = {
    "bottle": 0.3, "phone": 0.15, "laptop": 0.35, "coin": 0.025, "coin_stack": 0.04, "cash": 0.16, "hammer": 0.33,
    "wrench": 0.25, "lightbulb": 0.12, "beaker": 0.22, "sugar_cube": 0.016, "money_bag": 0.5, "gold_bar": 0.25,
    "chicken": 0.45, "dog": 0.9, "bird": 0.3, "fish": 0.4, "bus": 12.0, "truck": 9.0, "airplane": 37.0,
    "helicopter": 13.0, "fan": 0.6, "electric_motor": 0.6, "valve": 0.4, "battery": 0.3, "thermometer": 0.35,
}  # (close-to-life models like people, cows, trees and tractors are left as they are)


def real_scale(name: str, params: dict | None = None) -> float | None:
    """The scale that makes this object its real size (None = the model is already real, or it is a symbol)."""
    name = resolve(name)
    if name not in REAL_SIZE:
        return None
    lo, hi = build(name, **(params or {})).bounds()
    size = float(max(hi - lo))
    return REAL_SIZE[name] / size if size > 1e-6 else None


def names() -> list[str]:
    """The objects the planner can use (set pieces like walls and counters are placed by the settings)."""
    return sorted(n for n, i in REGISTRY.items() if "set" not in i.tags)


from . import assets_more  # noqa: E402,F401  (registers the rest of the library)
from . import machines  # noqa: E402,F401  (machines with real working parts: engine, elevator, car…)
from . import settings as _settings  # noqa: E402,F401  (set pieces: walls, counters, tiles… not in the catalog)

REGISTRY.pop("engine", None)  # the old toy engine: "engine" now means the real car_engine (alias)
from . import builder as _builder  # noqa: E402  (built-in recipes: objects made of basic parts)

_builder.load_dir(_builder.RECIPES_DIR)
