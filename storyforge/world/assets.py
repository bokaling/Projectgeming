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
    lo, hi = model.bounds()
    model.anchors.setdefault("top", (0.0, float(hi[1]), 0.0))
    model.anchors.setdefault("label", (0.0, float(hi[1]) + 0.35, 0.0))
    model.anchors.setdefault("center", tuple(float(x) for x in (lo + hi) / 2))
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


def catalog(compact: bool = True) -> str:
    """The list the AI sees: name(params): what it is."""
    lines = []
    for info in sorted(REGISTRY.values(), key=lambda i: i.name):
        ps = ", ".join(f"{k}={v!r}" for k, v in info.params.items() if k not in ("seed",))
        lines.append(f"- {info.name}({ps}): {info.about}" if not compact else f"- {info.name}: {info.about}"
                     + (f" [params: {ps}]" if ps else ""))
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
    body_c, spot_c = col(color, C["white"]), col(spots, C["black"])
    m = Model()
    body = M.xf(M.sphere(1.0, 1), (0, 1.25, 0), s=(1.15, 0.55, 0.5))
    m.add("body", body, body_c)
    m.add("head", M.xf(M.box(0.42, 0.42, 0.55), (1.25, 1.55, 0), (0, 90, -18)), body_c)
    m.add("muzzle", M.xf(M.box(0.36, 0.22, 0.25), (1.5, 1.42, 0), (0, 0, -18)), C["pink"])
    for z in (-0.18, 0.18):
        m.add("horn", M.xf(M.cone(0.05, 0.18, 6), (1.18, 1.8, z)), "#e8dcc0")
        m.add("ear", M.xf(M.box(0.08, 0.12, 0.22), (1.13, 1.68, z * 1.9)), body_c)
    for x in (-0.65, 0.65):
        for z in (-0.25, 0.25):
            m.add("leg", M.xf(M.box(0.16, 0.85, 0.16, base=True), (x, 0.0, z)), body_c)
            m.add("hoof", M.xf(M.box(0.18, 0.12, 0.18, base=True), (x, 0.0, z)), C["black"])
    m.add("udder", M.xf(M.sphere(0.2, 0), (-0.3, 0.8, 0)), C["pink"])
    m.add("tail", M.tube([(-1.12, 1.4, 0), (-1.22, 0.95, 0.05)], 0.04, 5), body_c)
    rng = np.random.default_rng(int(seed))
    for _ in range(4):  # spots
        x, z = rng.uniform(-0.6, 0.6), rng.choice([-1, 1]) * 0.47
        m.add("spot", M.xf(M.box(rng.uniform(0.3, 0.5), rng.uniform(0.25, 0.4), 0.06), (x, rng.uniform(1.1, 1.45), z)),
              spot_c)
    m.anchors["back"] = (-1.15, 1.0, 0.0)
    m.anchors["label"] = (0.0, 2.3, 0.0)
    return m


@asset("barn", "an open dairy barn (free-stall shed: roof on posts, low walls, cows can be inside)", ["farm", "building"],
       aliases=["shed", "stable", "farm_building", "free_stall"])
def barn(length=14.0, width=9.0, color="barn", roof="roof"):
    wall_c, roof_c = col(color, C["barn"]), col(roof, C["roof"])
    m = Model()
    h = 3.4
    for x in np.linspace(-length / 2, length / 2, 5):
        for z in (-width / 2, width / 2):
            m.add("post", M.xf(M.box(0.25, h, 0.25, base=True), (x, 0, z)), C["white"])
    m.add("wall", M.xf(M.box(length, 1.0, 0.18, base=True), (0, 0, -width / 2)), wall_c)
    m.add("wall", M.xf(M.box(0.18, h, width, base=True), (-length / 2, 0, 0)), wall_c)
    roof_g = M.xf(M.prism_roof(width + 1.2, length + 1.0, 1.8), (0, h, 0), (0, 90, 0))
    m.add("roof", roof_g, roof_c, shell=True)
    m.add("ridge", M.xf(M.box(length + 1.2, 0.18, 0.4), (0, h + 1.8, 0)), C["white"])
    m.add("floor", M.box(length, 0.08, width, base=True), "#5d6a6e")
    m.add("alley", M.xf(M.box(length, 0.1, 1.6, base=True), (0, 0, 0.9)), "#7d888c")
    m.anchors["label"] = (0.0, h + 2.4, 0.0)
    m.anchors["alley_start"] = (-length / 2, 0.1, 0.9)
    m.anchors["alley_end"] = (length / 2, 0.1, 0.9)
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
def scraper(width=1.6, color="yellow"):
    m = Model().add("blade", M.xf(M.box(0.18, 0.45, width, base=True), (0, 0, 0), (0, 0, -12)), col(color, C["yellow"]))
    m.add("frame", M.xf(M.box(0.9, 0.12, 0.2, base=True), (-0.45, 0.05, 0)), C["dark_steel"])
    m.add("chain", M.xf(M.box(3.0, 0.05, 0.05, base=True), (-1.9, 0.05, 0)), C["steel"])
    return m


@asset("tractor", "a farm tractor (big rear wheels, cab, exhaust)", ["farm", "vehicle"],
       aliases=["farm_tractor", "loader"])
def tractor(color="green", cab="#d8e7ea"):
    body_c = col(color, C["green"])
    m = Model()
    m.add("body", M.xf(M.box(2.0, 0.9, 1.1, base=True), (0.4, 0.75, 0)), body_c)
    m.add("hood", M.xf(M.box(1.2, 0.7, 0.95, base=True), (1.35, 0.75, 0)), body_c)
    m.add("cab", M.xf(M.box(1.1, 1.2, 1.15, base=True), (-0.3, 1.65, 0)), col(cab, "#d8e7ea"), opacity=0.55)
    m.add("roof", M.xf(M.box(1.25, 0.12, 1.3, base=True), (-0.3, 2.85, 0)), body_c)
    m.add("exhaust", M.xf(M.cylinder(0.07, 1.1, 8), (1.5, 1.4, 0.3)), C["black"])
    for x, r, z in ((-0.55, 0.85, 0.75), (-0.55, 0.85, -0.75), (1.55, 0.45, 0.62), (1.55, 0.45, -0.62)):
        wheel = M.xf(M.torus(r * 0.72, r * 0.3, 14, 6), (0, 0, 0), (90, 0, 0))
        m.add("wheel", M.xf(wheel, (x, r, z)), C["black"], kind="wheel", pivot=(x, r, z), axis="z")
        m.add("hub", M.xf(M.cylinder(r * 0.42, 0.25, 10, base=False), (x, r, z * 1.05), (90, 0, 0)), C["yellow"],
              kind="wheel", pivot=(x, r, z), axis="z")
    m.anchors["exhaust"] = (1.5, 2.55, 0.3)
    m.anchors["label"] = (0.3, 3.4, 0.0)
    return m


@asset("tank", "an open round storage tank / lagoon (liquid inside; crust=True adds a floating crust)",
       ["farm", "industry", "container"], aliases=["storage_tank", "lagoon", "pit", "manure_storage", "pool", "basin"])
def tank(r=4.0, h=2.6, color="concrete", liquid="#6b4a2c", level=0.75, crust=False, seed=5):
    m = Model()
    wall = M.merge(M.cylinder(r, h, 28, caps=False), M.cylinder(r * 0.93, h, 28, caps=False))
    m.add("wall", wall, col(color, C["concrete"]), shell=True)
    m.add("rim", M.xf(M.torus(r * 0.965, 0.13, 28, 4), (0, h, 0)), "#d4dadd", shell=True)
    m.add("floor", M.cylinder(r * 0.95, 0.06, 28), "#6c7378")
    lv = max(0.05, min(1.0, float(level))) * h * 0.95
    m.add("liquid", M.cylinder(r * 0.92, lv, 28), col(liquid, C["manure"]), kind="liquid")
    if crust:
        rng = np.random.default_rng(int(seed))
        lumps = [M.xf(M.jitter(M.sphere(rng.uniform(0.35, 0.7), 0), 0.08, int(rng.integers(99))),
                      (rng.uniform(-0.62, 0.62) * r, lv + 0.05, rng.uniform(-0.62, 0.62) * r), s=(1.3, 0.32, 1.3))
                 for _ in range(22)]
        m.add("crust", M.merge(M.xf(M.cylinder(r * 0.9, 0.1, 24), (0, lv - 0.02, 0)), *lumps), C["crust"], kind="crust")
    m.anchors["label"] = (0.0, h + 0.9, 0.0)
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
def digester(r=4.5, h=4.0, color="#5e8c61", dome="#ece4cf", liquid="#5a3d24", level=0.72):
    m = Model()
    m.add("wall", M.cylinder(r, h, 32, caps=False), col(color, "#5e8c61"), shell=True)
    m.add("band", M.xf(M.torus(r * 1.01, 0.08, 32, 4), (0, h * 0.5, 0)), C["dark_steel"], shell=True)
    dome_g = M.lathe([(r, 0), (r * 0.95, r * 0.28), (r * 0.8, r * 0.5), (r * 0.55, r * 0.66), (r * 0.25, r * 0.74),
                      (0.0, r * 0.76)], 32, close_bottom=False)
    m.add("dome", M.xf(dome_g, (0, h, 0)), col(dome, "#ece4cf"), shell=True)
    m.add("floor", M.cylinder(r * 0.98, 0.08, 32), "#4b5257")
    lv = h * float(level)
    m.add("liquid", M.cylinder(r * 0.97, lv, 32), col(liquid, "#5a3d24"), kind="liquid")
    m.add("gas", M.xf(dome_g, (0, h, 0), s=(0.96, 0.92, 0.96)), C["gas"], opacity=0.25, kind="gas")
    m.add("pipe_out", M.tube([(0, h + r * 0.76, 0), (0, h + r * 0.76 + 0.6, 0), (r + 1.2, h + r * 0.76 + 0.6, 0)],
                             0.18, 8), C["yellow"])
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
       ["energy", "machine"], aliases=["genset", "engine_generator", "power_generator", "chp", "dynamo", "turbine", "power_plant"])
def generator(color="#f2b134", length=3.6):
    body_c = col(color, "#f2b134")
    m = Model()
    m.add("skid", M.box(length + 0.4, 0.25, 1.7, base=True), C["dark_steel"])
    m.add("body", M.xf(M.box(length, 1.6, 1.5, base=True), (0, 0.25, 0)), body_c)
    for k in range(7):
        m.add("grille", M.xf(M.box(0.06, 1.1, 1.52), (length * 0.18 + k * 0.17, 1.05, 0)), "#b67f1d")
    m.add("fan", M.xf(M.merge(*[M.xf(M.box(0.05, 0.9, 0.18), (0, 0, 0), (a, 0, 0)) for a in (0, 60, 120)]),
                      (length / 2 + 0.05, 1.05, 0)), C["dark_steel"], kind="blade", axis="x",
          pivot=(length / 2 + 0.05, 1.05, 0))
    m.add("exhaust", M.xf(M.cylinder(0.12, 1.2, 8), (-length * 0.3, 1.85, 0.3)), C["black"])
    m.add("panel", M.xf(M.box(0.7, 0.9, 0.12, base=True), (-length * 0.25, 0.6, 0.8)), "#3a4450")
    m.add("screen", M.xf(M.box(0.45, 0.3, 0.04), (-length * 0.25, 1.15, 0.87)), "#7df0ff", kind="light")
    m.anchors["exhaust"] = (-length * 0.3, 3.1, 0.3)
    m.anchors["inlet"] = (-length / 2, 1.0, 0.0)
    m.anchors["outlet"] = (length / 2, 1.2, 0.0)
    m.anchors["label"] = (0.0, 2.8, 0.0)
    return m


@asset("power_pole", "a wooden power pole with a cross arm and insulators (wires go between poles)",
       ["energy", "city"], aliases=["utility_pole", "pole", "power_line", "electric_pole"])
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
def house(w=3.2, d=3.0, h=2.4, color="#f3e3c3", roof="#b5523b", seed=1):
    m = Model()
    m.add("walls", M.box(w, h, d, base=True), col(color, "#f3e3c3"), shell=True)
    m.add("roof", M.xf(M.prism_roof(w + 0.5, d + 0.4, 1.4), (0, h, 0)), col(roof, "#b5523b"), shell=True)
    m.add("chimney", M.xf(M.box(0.35, 0.9, 0.35, base=True), (w * 0.25, h + 0.6, -d * 0.2)), "#8b5a4a")
    m.add("door", M.xf(M.box(0.6, 1.2, 0.06, base=True), (0, 0, d / 2 + 0.02)), "#6b4a3a")
    wins = [M.xf(M.box(0.55, 0.55, 0.06), (x, h * 0.62, d / 2 + 0.02)) for x in (-w * 0.3, w * 0.3)]
    wins += [M.xf(M.box(0.06, 0.55, 0.55), (w / 2 + 0.02, h * 0.62, 0))]
    m.add("windows", M.merge(*wins), "#2b3a4a", kind="light")
    m.anchors["label"] = (0.0, h + 2.0, 0.0)
    m.anchors["wire"] = (-w / 2, h * 0.8, 0.0)
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
def person(shirt="#3d8fd6", pants="#2f3b4c", skin="skin", hat="", height=1.8):
    s = height / 1.8
    m = Model()
    for z in (-0.12, 0.12):
        m.add("leg", M.xf(M.box(0.16, 0.85 * s, 0.18, base=True), (0, 0, z)), col(pants, "#2f3b4c"))
    m.add("torso", M.xf(M.box(0.32, 0.65 * s, 0.5, base=True), (0, 0.85 * s, 0)), col(shirt, C["blue"]))
    for z in (-0.32, 0.32):
        m.add("arm", M.xf(M.box(0.13, 0.6 * s, 0.13, base=True), (0, 0.88 * s, z)), col(shirt, C["blue"]))
    m.add("head", M.xf(M.sphere(0.17 * s, 1), (0, 1.66 * s, 0)), col(skin, C["skin"]))
    if hat:
        m.add("hat", M.xf(M.cylinder(0.2 * s, 0.12 * s, 10), (0, 1.8 * s, 0)), col(hat, C["yellow"]))
    m.anchors["label"] = (0.0, 2.3 * s, 0.0)
    return m


def names() -> list[str]:
    return sorted(REGISTRY)
