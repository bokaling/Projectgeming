"""Object builder: objects the library doesn't have are designed as low poly RECIPES (basic parts with sizes,
colours, positions, ports and moving parts), checked, turned into models and saved for reuse.

* Built-in recipes live in storyforge/world/recipes/*.json; ones the AI designs are saved to Drive in
  StoryForge/library/objects/<name>.json and loaded again next time.
* With a free Gemini key, `ensure_objects` asks the AI to design every unknown object in a plan. Without a key
  (or if the design fails the checks) the closest existing object is used, as before.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np

from . import mesh as M
from . import motion as motion_mod
from .mesh import Model

SHAPES = {"box", "cylinder", "cone", "sphere", "capsule", "torus", "tube", "wedge", "extrude", "lathe", "dome",
          "gear", "spring", "blades", "taper"}
KINDS = {"", "blade", "wheel", "piston", "rocker", "flame", "liquid", "light", "lamp", "load", "heater"}
MATERIALS = {"metal", "paint", "plastic", "glass", "rubber", "ceramic", "water"}
RECIPES_DIR = Path(__file__).parent / "recipes"
_loaded: set = set()
_BUILTIN: dict = {}  # {"on": True} while the built-in recipes load: their CAD meshes are kept in the repo

DESIGN_SYSTEM = """You design ONE low poly 3D object for a "how it works" explainer as a recipe of basic shapes.
It must be the REAL thing at its REAL size, with its REAL working parts inside, so the video can cut it open and show
how it works (a fridge has a compressor, condenser coils, an evaporator, a capillary tube and refrigerant; a toilet
has a tank, flapper, float, fill valve, bowl and siphon; a washing machine has a drum, motor and belt).
Units are meters, y is up, the object stands on y = 0, its front faces +z (the camera side). 12-45 parts.
Look and proportions: real proportions (measure from the real thing), believable colours and materials (white
enamel, brushed steel, copper, black rubber, glass), rounded things round (lathe, dome, taper), never a pile of
boxes. The outer casing is "shell": true so the cutaway shows the works inside.
MECHANISM KIT: ready-made animated building blocks; add one as a part {"kit": "<piece>", "name": "<real part name>",
"pos": [x,y,z], "size": main size in m, "axis": "x"|"y"|"z"|"-x"|"-y"|"-z" (shaft / travel direction), optional
"teeth", "count", "stages", "blades", "turns"}. It becomes several moving parts named "<name>", "<name>_…", with
its own flow paths "<name>_<path>" and ports. Pieces:
KIT_LIST
Prefer kit pieces for every moving mechanism (they move correctly); use basic shapes for the casing and details.
Shapes and "size": box [w, h, d] (centred on pos), cylinder [r, h] (upright, centred), cone [r, h] (upright, base at pos),
sphere [r], capsule [r, length] (along x), torus [R, r] (flat ring), wedge [w, h, d] (a roof/ramp shape),
tube {"points": [[x,y,z],…]} with size [r] (pipes, coils, cables), extrude {"poly": [[x,y],…]} with size [depth],
lathe {"profile": [[radius, y], …], "caps": true|false} (a CURVED round shape spun around y: toilet bowls, bottles,
nacelles, tanks; "caps": false leaves the ends open), dome [r, h] (half a sphere: compressor domes, caps),
taper [r_bottom, h, r_top] (a narrowing cylinder: nozzles, funnels), gear [r, thickness] + "teeth" (a toothed gear
facing +z, spins about z), spring [radius, length, wire] + "turns" (a coil along y: springs, heating coils),
blades [radius, width, thickness] + "count" (fan / turbine / propeller blades around z, twisted).
Per part: "name" (the part's real name: compressor, coil, float, flapper… the camera can aim at it), "color",
"rot" [rx, ry, rz] degrees, "pivot" [x,y,z] and "axis" (x/y/z) for moving parts, "material" (metal, paint, plastic,
glass, rubber, ceramic, water), "opacity" (glass 0.3, water 0.75), "emissive" (0-1 glow),
"shell": true for the OUTER casing (cut open in a cutaway, so the works inside show; put the works inside it),
"kind": liquid (a liquid level that fills/drains; name it, e.g. "tank_water"), light (turns on), heater (glows orange
when turned on: heating elements, toaster wires), flame. A moving part turns about its "pivot" (default: its pos),
"motion" (how a working part moves; one dict or a list):
  {"type": "spin", "axis": "x", "speed": 1}            fans, motors, gears, drums (while the machine runs)
  {"type": "slide", "axis": "y", "amp": 0.02}          pistons, plungers (go up and down while it runs)
  {"type": "swing", "axis": "z", "deg": 20}            rocker arms, levers, wipers (while it runs)
  {"type": "open", "axis": "x", "amp": 0.5} or {"type": "open", "axis": "y", "deg": 100}   doors, lids, flappers, valves
  {"type": "swing", "axis": "z", "deg": 30, "drive": "open"}   a handle/lever that moves when the thing opens
  {"type": "level", "of": "tank_water", "axis": "y", "amp": 0.15}   a float riding on a liquid's level
  {"type": "pulse", "speed": 1}                         a light/spark that flashes in time
"paths": named polylines that flows travel along (refrigerant loop, water from tank to bowl, air in, gas out):
  {"loop": [[x,y,z],…], "water": [[x,y,z],…]}. "ports": named points other things connect to (inlet, outlet, power).
Believable colours (metal grey, copper coils, white enamel, black rubber), not toy colours.
"tour": the key working parts in the order they work, each with one plain, true sentence of what it does
([["compressor", "A compressor squeezes the gas, and it gets hot."], …]); no numbers.
CAD SHAPES (smooth, real-looking parts: prefer these for casings, drums, nozzles, hoses, brackets and mechanical
parts): a part with "cad": "<shape>" instead of "shape"; sizes in metres, centred on "pos" like the basic shapes:
CAD_LIST
Every casing has rounded edges ("fillet" 1-3 cm), round things are revolve/cylinder (never a box), hollow things are
"hollow" (a cut shows a thin wall, not a solid slab), doors have windows/handles, motors and pumps sit on brackets
and are bolted ("bolt"/"nut" parts), gears are "gear" parts that really mesh (centre distance = module x (n1 + n2) / 2).
BUILD THE BLUEPRINT: you get "blueprint" (how the real thing is built). Follow it exactly: the same part names,
sizes, positions, what sits inside the casing, which way parts face, shared axes, how they move. Every part must
touch what holds it (nothing floats), spinning parts turn about the blueprint's axis and share it where it says so.
REQUIRED: real part names (the camera aims at them: "drum", "magnetron", "compressor"), "key_part" (the most important
working part: the cutaway plane goes through it), "ports" for pipes/cables (inlet, outlet, power…), "paths" for every
flow (water in, air through, heat out, current), and a "tour".
Reply with JSON only: {"name", "about", "tags", "aliases", "key_part", "parts": [...], "paths": {...}, "ports": {...},
"tour": [...], "label": [x,y,z]}"""

DESCRIBE_SYSTEM = """Before a 3D model of a real object is built, you write down HOW THE REAL THING IS BUILT, like an
engineer looking at the real one. Real sizes in metres. Our axes: y is up, the object stands on y = 0, its FRONT
faces +z (towards the camera), x goes to the right. Think about: its main parts and their real shapes, which way it
stands and faces, what connects to what (a motor is bolted to the frame, a drum hangs on a shaft, a fan sits on its
motor's shaft), which parts share one axis (a turbine's fan, compressor and shaft; a drum and its pulley), what sits
inside a casing, which way things move, real dimensions, the details people recognise it by (buttons, a door
window, vents, a handle, bolts, hoses), materials, and where it normally sits (floor, kitchen counter, table, wall,
ceiling, in a car's engine bay).
Reply with JSON only:
{"what": "one plain sentence", "size_m": [width x, height y, depth z], "sits_on": "floor|counter|table|wall|ceiling|
ground|vehicle", "front": "what you see on its front", "casing": "the outer shell part's name or null",
 "parts": [{"name": "real part name (snake_case)", "shape": "its real shape in words", "size_m": [w, h, d],
   "pos": [x, y, z] (its centre), "inside": "casing name or null", "connects_to": ["part names it is fixed to"],
   "moves": "spins|slides|swings|opens|still", "axis": "x|y|z or null", "faces": "front|back|left|right|top|bottom|null",
   "material": "metal|paint|plastic|glass|rubber|ceramic|water", "color": "#rrggbb", "importance": "key|minor"}],
 "shared_axes": [["part", "part on the same axis"], …], "visible_details": ["…"]}"""

CHECK_SYSTEM = """You check low poly 3D objects made for a "how it works" explainer channel. You see 3 views of ONE
object: front 3/4, side, and cut open through its key part with the working parts moving. Judge only what you see.
Reply with JSON only: {"ok": true|false, "looks_like": "what it looks like", "problems": ["…"],
"fix": "what to change in the recipe: which parts, sizes, positions, shapes or colours"}.
ok = it clearly looks like the named thing, with believable proportions, and its key working parts are visible."""


def _design_system() -> str:
    from . import cad, kit  # noqa: PLC0415

    return DESIGN_SYSTEM.replace("KIT_LIST", kit.describe()).replace("CAD_LIST", cad.describe())


def describe_real_thing(name: str, description: str = "", rep=None) -> dict | None:
    """Step 1 of a design: how the real thing is built (parts, real sizes, axes, what is inside, which way it
    faces, where it sits). Stored with the object as its "blueprint". None without an AI that answers."""
    from .. import llm  # noqa: PLC0415

    def validate(obj):
        if not isinstance(obj.get("parts"), list) or len(obj["parts"]) < 3:
            raise ValueError("a blueprint needs its main parts")

    try:
        _, bp = llm.generate_json(DESCRIBE_SYSTEM, json.dumps({"object": name, "what_it_is": description}),
                                  validate=validate, rep=rep, task=f"describe a real {name}", temperature=0.3,
                                  max_tokens=3500, strong=True)
        return bp
    except Exception as exc:  # noqa: BLE001
        from ..messages import StopRequested  # noqa: PLC0415

        if isinstance(exc, StopRequested):
            raise
        return None


def _num(v, default, lo, hi) -> float:
    try:
        x = float(v)
        return default if x != x else max(lo, min(hi, x))
    except (TypeError, ValueError):
        return default


def _vec(v, n=3, default=0.0, lo=-80.0, hi=80.0) -> list[float]:
    v = list(v) if isinstance(v, (list, tuple)) else []
    return [_num(v[k] if k < len(v) else default, default, lo, hi) for k in range(n)]


def _color(c) -> str:
    c = str(c or "")
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return c
    return assets.C.get(c, "#9aa3ab")


def model_from_recipe(recipe: dict) -> Model:
    """Build a model from a recipe (raises ValueError if it can't be a sensible object)."""
    parts = recipe.get("parts") if isinstance(recipe, dict) else None
    if not isinstance(parts, list) or not parts:
        raise ValueError("a recipe needs a list of parts")
    from . import kit as kit_mod  # noqa: PLC0415

    m = Model()
    flat, kit_paths, kit_ports = [], {}, {}
    for p in parts[:60]:  # mechanism kit pieces ({"kit": "turbine", …}) become their own named parts
        if isinstance(p, dict) and p.get("kit"):
            kp, kpaths, kports = kit_mod.expand(p)
            flat += kp
            kit_paths.update(kpaths)
            for k, v in kports.items():
                kit_ports.setdefault(k, v)  # plain "inlet"/"outlet": the first piece that has one
        else:
            flat.append(p)
    for p in flat[:120]:
        if not isinstance(p, dict):
            continue
        shape = str(p.get("shape", "box")).lower()
        if shape not in SHAPES:
            shape = "box"
        size = p.get("size") if isinstance(p.get("size"), (list, tuple)) else [p.get("size", 1.0)]
        s = [_num(x, 0.1 if p.get("cad") else 1.0, 0.001 if p.get("cad") else 0.01, 60.0) for x in size] or [1.0]
        while len(s) < 3:
            s.append(s[-1])
        if p.get("cad"):  # a real CAD shape (build123d / bd_warehouse; mesh version without the CAD kernel)
            from . import cad  # noqa: PLC0415

            try:
                g = cad.shape(p, builtin=_BUILTIN.get("on", False))
            except Exception:  # noqa: BLE001
                continue
            shape = "cad"
        elif shape == "box":
            g = M.box(s[0], s[1], s[2])
        elif shape == "cylinder":
            g = M.cylinder(s[0], s[1], 14, base=False)
        elif shape == "cone":
            g = M.cone(s[0], s[1], 12)
        elif shape == "sphere":
            g = M.sphere(s[0], 1)
        elif shape == "capsule":
            g = M.capsule(s[0], s[1], 12)
        elif shape == "torus":
            g = M.torus(s[0], min(s[1], s[0] * 0.9), 18, 6)
        elif shape == "wedge":
            g = M.xf(M.prism_roof(s[0], s[2], s[1]), (0, -s[1] / 2, 0))
        elif shape == "lathe":  # a curved, round shape: a profile [[radius, height], ...] spun around (bowls, domes)
            prof = [(_num(q[0], 0.1, 0.0, 60.0), _num(q[1], 0.0, -60.0, 60.0)) for q in (p.get("profile") or [])
                    if isinstance(q, (list, tuple)) and len(q) >= 2][:24]
            if len(prof) < 2:
                continue
            closed = p.get("caps", True) is not False  # "caps": false = an open ring (an engine intake, a pipe)
            g = M.lathe(prof, 16, close_bottom=closed and prof[0][0] > 0, close_top=closed and prof[-1][0] > 0)
        elif shape == "dome":  # half a sphere (a compressor dome, a tank top): size [radius, height]
            r, h = s[0], s[1]
            g = M.lathe([(r * math.cos(a), h * math.sin(a)) for a in np.linspace(0, math.pi / 2, 7)], 16)
        elif shape == "gear":  # a toothed gear in the XY plane (it spins about z): size [radius, thickness]
            n = int(_num(p.get("teeth"), 12, 5, 60))
            g = M.gear(s[0], n, s[1], tooth=max(0.004, s[0] * 0.16))
        elif shape == "spring":  # a coil spring / heating coil along y: size [radius, length, wire]
            n = int(_num(p.get("turns"), 6, 1, 40))
            r, ln, w = s[0], s[1], min(s[2], s[0] * 0.5)
            pts = [(r * math.cos(a), -ln / 2 + ln * a / (2 * math.pi * n), r * math.sin(a))
                   for a in np.linspace(0, 2 * math.pi * n, n * 10 + 1)]
            g = M.tube(pts, w, 6, joints=False)
        elif shape == "blades":  # fan / turbine / propeller blades around z: size [radius, width, thickness]
            n = int(_num(p.get("count"), 6, 2, 40))
            hub = s[0] * 0.18
            bl = []
            for k in range(n):
                b = M.xf(M.box(s[0] - hub, s[1], s[2]), ((s[0] + hub) / 2, 0, 0), (25, 0, 0))  # twisted blade
                bl.append(M.xf(b, (0, 0, 0), (0, 0, 360.0 * k / n)))
            bl.append(M.xf(M.cylinder(hub, s[2] * 3, 12, base=False), (0, 0, 0), (90, 0, 0)))
            g = M.merge(*bl)
        elif shape == "taper":  # a cylinder that narrows: size [bottom radius, height, top radius]
            g = M.cylinder(s[0], s[1], 14, r_top=_num(size[2] if len(size) > 2 else s[0] * 0.5, s[0] * 0.5, 0.0, 60.0),
                           base=False)
        elif shape == "tube":
            pts = [_vec(q) for q in (p.get("points") or [])][:40]
            if len(pts) < 2:
                continue
            g = M.tube(pts, s[0], 8)
        elif shape != "cad":  # extrude
            poly = [_vec(q, 2) for q in (p.get("poly") or [])][:24]
            if len(poly) < 3:
                continue
            g = M.extrude(poly, s[0])
        if shape != "tube":
            if p.get("post_rot"):  # a kit piece turned to its axis: the part's own rot first, then the piece's
                g = M.xf(M.xf(g, (0, 0, 0), _vec(p.get("rot"), 3, 0.0, -360, 360)), _vec(p.get("pos")),
                         _vec(p.get("post_rot"), 3, 0.0, -360, 360))
            else:
                g = M.xf(g, _vec(p.get("pos")), _vec(p.get("rot"), 3, 0.0, -360, 360))
        kind = str(p.get("kind") or "")
        kind = kind if kind in KINDS else ""
        mo = p.get("motion")
        mo = [x for x in (motion_mod.check(q) for q in (mo if isinstance(mo, list) else [mo])) if x]
        mat = str(p.get("material") or "").lower()
        piv = p.get("pivot")
        if piv is None and (mo or kind in ("blade", "wheel")) and shape != "tube":
            piv = p.get("pos")  # no pivot given: it turns about its own centre, not about the model's origin
        m.add(re.sub(r"[^a-z0-9_]+", "_", str(p.get("name") or shape).lower())[:24] or shape, g, _color(p.get("color")),
              emissive=_num(p.get("emissive"), 0.0, 0, 1),
              opacity=_num(p.get("opacity"), 1.0, 0.1, 1.0), shell=bool(p.get("shell", False)), kind=kind,
              pivot=tuple(_vec(piv)), axis=str(p.get("axis") or "y") if p.get("axis") in ("x", "y", "z") else "y",
              motion=(mo[0] if len(mo) == 1 else mo) or None, material=mat if mat in MATERIALS else "",
              hollow=0.0 if p.get("cad") else _num(p.get("hollow"), 0.0, 0.0, 2.0))
    if not m.parts:
        raise ValueError("no usable parts")
    lo, hi = m.bounds()
    ext = hi - lo
    if not np.all(np.isfinite(ext)) or float(ext.max()) < 0.05 or float(ext.max()) > 120:
        raise ValueError(f"odd size ({ext.round(2).tolist()} m)")
    if lo[1] < -0.3:  # stand it on the ground
        m.parts = [M.Part(q.name, M.xf(q.geo, (0, -float(lo[1]), 0)), q.color, q.emissive, q.opacity, q.shell,
                          tuple(np.asarray(q.pivot) + [0, -float(lo[1]), 0]), q.axis, q.kind, motion=q.motion,
                          material=q.material) for q in m.parts]
    for name, pt in {**kit_ports, **(recipe.get("ports") or {})}.items():
        m.anchors[str(name)] = tuple(_vec(pt))
    for name, pts in kit_paths.items():
        if len(pts) >= 2:
            m.paths[str(name)] = [list(map(float, q)) for q in pts]
    key = re.sub(r"[^a-z0-9_]+", "_", str(recipe.get("key_part") or "").lower()).strip("_")
    if key and any(q.name == key or q.name.startswith(key + "_") for q in m.parts):
        m.key = key  # the most important part: a cutaway of the whole object cuts right through it
        c = assets.part_center(m, key)
        if c is not None:
            lo_k = [q.geo.bounds() for q in m.parts if q.name == key or q.name.startswith(key + "_")]
            mid = (np.min([b[0] for b in lo_k], 0) + np.max([b[1] for b in lo_k], 0)) / 2
            m.anchors["key"] = tuple(float(x) for x in mid)
    if recipe.get("label"):
        m.anchors["label"] = tuple(_vec(recipe["label"]))
    for item in (recipe.get("tour") or [])[:10]:  # the key parts in working order, one plain sentence each
        if isinstance(item, (list, tuple)) and len(item) == 2:
            m.tour.append((re.sub(r"[^a-z0-9_]+", "_", str(item[0]).lower())[:24], str(item[1])[:120]))
    for name, pts in (recipe.get("paths") or {}).items():  # e.g. "flow": blood through a vessel
        if isinstance(pts, list) and len(pts) >= 2:
            m.paths[str(name)] = [tuple(_vec(q)) for q in pts[:40]]
    return m


def register(recipe: dict) -> str:
    """Add a recipe to the library (checked first). Returns its asset name."""
    name = re.sub(r"[^a-z0-9_]+", "_", str(recipe.get("name") or "").lower()).strip("_")
    if not name:
        raise ValueError("a recipe needs a name")
    model_from_recipe(recipe)  # check it builds

    sits = str((recipe.get("blueprint") or {}).get("sits_on") or recipe.get("sits_on") or "").lower()
    if sits in ("counter", "table", "wall", "ceiling", "floor"):
        assets.PLACE[name] = sits  # where it belongs (a microwave on the counter, a ceiling fan on the ceiling)

    def make(**_):
        m = model_from_recipe(recipe)
        from . import sense  # noqa: PLC0415

        sense.add_supports(m)  # nothing floats: a part with nothing under it gets a bracket
        return m

    make.__name__ = name
    tags = [str(t) for t in (recipe.get("tags") or ["built"])][:8]
    m = model_from_recipe(recipe)
    if any(p.motion for p in m.parts) and "machine" not in tags:
        tags.append("machine")
    if any(p.shell for p in m.parts) and any(p.motion or p.kind in ("liquid", "blade") for p in m.parts):
        tags.append("cutaway")  # it has works inside an outer casing: the checker cuts it open when it works
    tags = list(dict.fromkeys(tags))
    assets.asset(name, str(recipe.get("about") or name.replace("_", " "))[:160], tags,
                 [re.sub(r"[^a-z0-9_]+", "_", str(a).lower()) for a in (recipe.get("aliases") or [])][:10])(make)
    return name


def load_dir(folder: Path) -> list[str]:
    names = []
    if not folder.is_dir():
        return names
    _BUILTIN["on"] = Path(folder).resolve() == RECIPES_DIR.resolve()
    try:
        return _load_dir(folder, names)
    finally:
        _BUILTIN["on"] = False


def _load_dir(folder: Path, names: list) -> list[str]:
    for f in sorted(folder.glob("*.json")):
        if str(f) in _loaded:
            continue
        try:
            names.append(register(json.loads(f.read_text(encoding="utf-8"))))
            _loaded.add(str(f))
        except (ValueError, OSError, json.JSONDecodeError):
            continue
    return names


def user_dir() -> Path:
    from .. import config  # noqa: PLC0415

    return config.get().root / "library" / "objects"


def register_kit() -> list[str]:
    """Every mechanism kit piece is also a library object (kit_gear_train, kit_turbine…), standing on the floor."""
    from . import kit as kit_mod  # noqa: PLC0415

    names = []
    for k, fn in kit_mod.KIT.items():
        name = f"kit_{k}"
        if name in assets.REGISTRY:
            continue
        recipe = {"name": name, "about": f"mechanism kit: {fn.__doc__.strip()}", "tags": ["kit", "machine"],
                  "aliases": [], "key_part": k, "parts": [{"kit": k, "name": k, "pos": [0, 0, 0]}]}
        lo = model_from_recipe(recipe).bounds()[0]
        recipe["parts"][0]["pos"] = [0.0, round(max(0.0, -float(lo[1])) + 0.001, 4), 0.0]  # on the floor
        try:
            names.append(register(recipe))
        except ValueError:
            continue
    return names


def load_all() -> None:
    """Built-in recipes + the mechanism kit + the ones designed before (Drive)."""
    load_dir(RECIPES_DIR)
    register_kit()
    try:
        load_dir(user_dir())
    except Exception:  # noqa: BLE001  (no settings yet: built-in recipes only)
        pass
    try:
        from . import imported  # noqa: PLC0415

        imported.scan_folders()  # other CC0 packs you put on Drive (Kenney zips, Quaternius, Poly Haven)
    except Exception:  # noqa: BLE001
        pass


def known(name: str) -> str | None:
    """The library object for a name, without guessing ('submarine' → None if there is none)."""
    n = str(name or "").strip().lower().replace(" ", "_").replace("-", "_")
    for cand in (n, n.rstrip("s"), n[:-2] if n.endswith("es") else ""):
        if cand in assets.REGISTRY:
            return cand
        if cand in assets.ALIASES:
            return assets.ALIASES[cand]
    return None


def self_check(name: str, recipe: dict, rep=None) -> tuple[bool | None, dict, list]:
    """Render the object from 3 angles and ask Gemini vision whether it looks like the thing with its key parts.
    → (ok: True/False, or None when it can't be checked (no OpenGL, no key, Gemini busy), the reply, the pictures)."""
    from .. import llm  # noqa: PLC0415

    model = model_from_recipe(recipe)
    stills = preview_stills(model)
    if not stills:
        return None, {}, []
    if llm.gemini_busy():
        return None, {}, stills
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    jpgs = []
    for im in stills:
        buf = io.BytesIO()
        Image.fromarray(im).save(buf, "JPEG", quality=85)
        jpgs.append(buf.getvalue())
    parts = sorted({re.sub(r"\d+$", "", p.name) for p in model.parts})[:30]
    bp = recipe.get("blueprint") or {}
    text = (f"Object: {name.replace('_', ' ')} ({recipe.get('about', '')}). Its parts: {', '.join(parts)}. "
            f"Key part: {recipe.get('key_part', '')}. How the real one is built: {bp.get('what', '')} "
            f"Front: {bp.get('front', '')}. Details: {', '.join(map(str, (bp.get('visible_details') or [])[:8]))}. "
            f"Does it clearly look like a {name.replace('_', ' ')} (a normal person could name it), match that "
            "description (parts facing the right way, lined up, nothing floating, the casing there), with believable "
            "proportions, and are the key working parts visible in the cut-open view?")
    reply = llm.vision_json(CHECK_SYSTEM, text, jpgs, rep=rep, max_tokens=800)
    if not isinstance(reply, dict) or "ok" not in reply:
        return None, {}, stills
    return bool(reply.get("ok")), reply, stills


def _save_check(name: str, stills: list) -> None:
    try:
        from PIL import Image  # noqa: PLC0415

        folder = user_dir()
        folder.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.hstack(stills)).save(folder / f"{name}_check.jpg", quality=85)
    except Exception:  # noqa: BLE001
        pass


def design(name: str, description: str = "", rep=None, tries: int = 3) -> str | None:
    """Ask the free AI to design an object as a recipe; check how it looks (3 views + Gemini vision), let the AI fix
    it up to 2 times, then save it to the shared library on Drive and return its name (None if no AI answered)."""
    from .. import llm  # noqa: PLC0415

    from . import sense  # noqa: PLC0415

    example = json.loads((RECIPES_DIR / "piston_pump.json").read_text(encoding="utf-8")) if \
        (RECIPES_DIR / "piston_pump.json").exists() else {}
    blueprint = describe_real_thing(name, description, rep)  # 1) how the real thing is built, first
    payload = {"object": name, "what_it_is": description, "example_recipe": example, "blueprint": blueprint or {}}

    def validate(obj):
        model_from_recipe(obj)

    best, verdict = None, None
    for attempt in range(tries):
        try:
            _, recipe = llm.generate_json(_design_system(), json.dumps(payload, ensure_ascii=False),
                                          validate=validate, rep=rep, task=f"design a {name}", temperature=0.5,
                                          max_tokens=6000, strong=True)
        except Exception as exc:  # noqa: BLE001
            from ..messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            break
        recipe["name"] = name
        if blueprint:
            recipe["blueprint"] = blueprint
        best = recipe
        physics = sense.check(model_from_recipe(recipe), blueprint)  # 2) does it hold together like the real thing?
        recipe["sense"] = physics
        if physics and attempt < tries - 1:
            if rep is not None:
                rep.info(f"🔩 The {name.replace('_', ' ')} doesn't make physical sense yet: {sense.summary(physics)[:160]}"
                         " → redesigning")
            payload = {**payload, "previous_recipe": recipe, "fix_this": {"problems": physics,
                                                                           "fix": "fix exactly these problems"}}
            verdict = "failed"
            continue
        if physics:  # still not right after the redesigns: used for this video, not saved for next time
            verdict = "failed"
            break
        ok, reply, stills = self_check(name, recipe, rep)  # 3) does it look like the thing? (3 views, vision)
        if stills:
            _save_check(name, stills)
        if ok is None:  # can't judge it (no OpenGL / no key / Gemini busy): use it as it is
            verdict = "unchecked"
            break
        if ok:
            verdict = "checked"
            if rep is not None:
                rep.ok(f"👁️ The new {name.replace('_', ' ')} looks right (Gemini vision)")
            break
        verdict = "failed"
        if rep is not None:
            rep.info(f"👁️ The {name.replace('_', ' ')} doesn't look right yet: "
                     f"{'; '.join(str(x) for x in (reply.get('problems') or [])[:2])[:160]} → redesigning")
        payload = {**payload, "previous_recipe": recipe,
                   "fix_this": {"problems": reply.get("problems"), "fix": reply.get("fix"),
                                "looks_like": reply.get("looks_like")}}
    if best is None:
        return None
    best["checked"] = verdict or "unchecked"
    try:
        out = register(best)
        if verdict != "failed":  # only good (or uncheckable) designs go into the shared library for next time
            folder = user_dir()
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{out}.json").write_text(json.dumps(best, indent=1), encoding="utf-8")
        return out
    except (ValueError, OSError):
        return None


def compose(name: str, about: str = "", rep=None) -> str | None:
    """No AI designer: a machine made of mechanism kit pieces for a known kind of machine (not saved)."""
    from . import kit  # noqa: PLC0415

    recipe = kit.compose(f"{name.replace('_', ' ')} {about}")
    if recipe is None:
        return None
    if known(recipe["name"]):
        return known(recipe["name"])
    try:
        out = register(recipe)
        if rep is not None:
            rep.info(f"🧩 Built a {out.replace('_', ' ')} from the mechanism kit (no AI designer)")
        return out
    except ValueError:
        return None


def ensure_objects(plan: dict, rep=None, limit: int = 6) -> list[str]:
    """Design the objects a plan needs that the library doesn't have (needs the AI; else the closest is used)."""
    load_all()
    done = []
    for o in plan.get("objects") or []:
        if not isinstance(o, dict):
            continue
        raw = str(o.get("asset") or o.get("type") or "")
        if not raw or known(raw) or len(done) >= limit:
            continue
        name = re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_")
        if rep is not None:
            rep.info(f"🧱 Designing a new object: {raw}")
        about = str(o.get("about") or o.get("description") or "")
        made = design(name, about, rep) or compose(name, about, rep)
        if made:
            o["asset"] = made
            done.append(made)
            if rep is not None:
                rep.ok(f"New object “{made}” saved to your library")
        elif rep is not None:
            rep.info(f"↪ No AI designer free: using the closest object for {raw}")
    return done


def preview_stills(model: Model, size: int = 320, running: float = 0.7) -> list:
    """Three pictures of an object for the self check: front 3/4, side, and cut open through its key part
    (the working parts moving at time `running`). [] when there is no OpenGL."""
    try:
        from . import gl, presets  # noqa: PLC0415
        from .scene import SHINE  # noqa: PLC0415

        r = gl.Renderer((size, size), msaa=2, shadow_size=768)
    except Exception:  # noqa: BLE001
        return []
    try:
        lo, hi = model.bounds()
        c = (lo + hi) / 2
        rad = float(np.linalg.norm(hi - lo)) / 2 + 1e-3
        st = {"spin_on": True, "spin": running * 2 * math.pi, "lift": 0.5, "open": 0.0, "opens": {}, "fills": {},
              "fill": 1.0, "light": 1.0}
        key = np.asarray(model.anchors.get("key", tuple(c)), np.float64)
        keys = []
        for i, p in enumerate(model.parts):
            k = f"pv{id(model)}_{i}"
            r.upload(k, p.geo)
            keys.append(k)
        out = []
        for az, el, cut in ((35.0, 18.0, False), (100.0, 8.0, False), (25.0, 22.0, True)):
            ra, re_ = math.radians(az), math.radians(el)
            v = np.array([math.sin(ra) * math.cos(re_), math.sin(re_), math.cos(ra) * math.cos(re_)])
            eye = c + v * (rad / math.sin(math.radians(18)))
            n = np.array([v[0], 0.0, v[2]])
            n /= max(np.linalg.norm(n), 1e-6)
            draws = []
            for i, p in enumerate(model.parts):
                mat = np.eye(4, dtype=np.float32)
                if p.motion:
                    for mo in (p.motion if isinstance(p.motion, list) else [p.motion]):
                        mm, _, _ = motion_mod.evaluate(p, st, running, mo)
                        if mm is not None:
                            mat = mm @ mat
                clip = (*n, float(np.dot(n, key))) if (cut and p.shell) else None
                emi = p.emissive + (0.8 if p.kind in ("light", "heater") else 0.0)
                draws.append(gl.Draw(keys[i], mat, gl.hex_rgb(p.color), emi, p.opacity, clip,
                                     tuple(max(0.05, x * 0.45) for x in gl.hex_rgb(p.color)), False,
                                     shine=SHINE.get(p.material, 0.0), additive=p.kind == "beam"))
            out.append(r.render(gl.Frame(eye=tuple(eye), target=tuple(c), fov=36.0, draws=draws, focus=tuple(c),
                                         focus_radius=rad * 1.6, grid_center=(c[0], c[2]),
                                         style=dict(presets.LOOKS["studio_light"]))))
        return out
    except Exception:  # noqa: BLE001
        return []
    finally:
        r.release()


def test_still(name: str, out: Path, size: int = 256) -> Path | None:
    """A small picture of a new object (to check it looks right). None if there is no OpenGL."""
    try:
        from PIL import Image  # noqa: PLC0415

        from . import gl  # noqa: PLC0415

        m = assets.build(name)
        r = gl.Renderer((size, size), msaa=2, shadow_size=512)
        try:
            lo, hi = m.bounds()
            c = (lo + hi) / 2
            rad = float(np.linalg.norm(hi - lo)) / 2 + 0.2
            draws = []
            for i, p in enumerate(m.parts):
                r.upload(f"t{i}", p.geo)
                draws.append(gl.Draw(f"t{i}", np.eye(4, dtype=np.float32), gl.hex_rgb(p.color), p.emissive, p.opacity))
            d = rad / math.sin(math.radians(18))
            eye = c + np.array([0.7, 0.45, 1.0]) / np.linalg.norm([0.7, 0.45, 1.0]) * d
            img = r.render(gl.Frame(eye=tuple(eye), target=tuple(c), draws=draws, focus=tuple(c), focus_radius=rad * 1.5,
                                    grid_center=(c[0], c[2])))
        finally:
            r.release()
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img).save(out)
        return out
    except Exception:  # noqa: BLE001
        return None


from . import assets  # noqa: E402  (at the end: assets imports this module to load the built-in recipes)
