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

from . import assets
from . import mesh as M
from . import motion as motion_mod
from .mesh import Model

SHAPES = {"box", "cylinder", "cone", "sphere", "capsule", "torus", "tube", "wedge", "extrude"}
KINDS = {"", "blade", "wheel", "piston", "rocker", "flame", "liquid", "light", "lamp", "load"}
MATERIALS = {"metal", "paint", "plastic", "glass", "rubber", "ceramic", "water"}
RECIPES_DIR = Path(__file__).parent / "recipes"
_loaded: set = set()

DESIGN_SYSTEM = """You design ONE low poly 3D object for a "how it works" explainer as a recipe of basic shapes.
It must be the REAL thing at its REAL size, with its REAL working parts inside, so the video can cut it open and show
how it works (a fridge has a compressor, condenser coils, an evaporator, a capillary tube and refrigerant; a toilet
has a tank, flapper, float, fill valve, bowl and siphon; a washing machine has a drum, motor and belt).
Units are meters, y is up, the object stands on y = 0, its front faces +z (the camera side). 10-45 parts.
Shapes and "size": box [w, h, d] (centred on pos), cylinder [r, h] (upright, centred), cone [r, h] (upright, base at pos),
sphere [r], capsule [r, length] (along x), torus [R, r] (flat ring), wedge [w, h, d] (a roof/ramp shape),
tube {"points": [[x,y,z],…]} with size [r] (pipes, coils, cables), extrude {"poly": [[x,y],…]} with size [depth].
Per part: "name" (the part's real name: compressor, coil, float, flapper… the camera can aim at it), "color",
"rot" [rx, ry, rz] degrees, "pivot" [x,y,z] and "axis" (x/y/z) for moving parts, "material" (metal, paint, plastic,
glass, rubber, ceramic, water), "opacity" (glass 0.3, water 0.75), "emissive" (0-1 glow),
"shell": true for the OUTER casing (cut open in a cutaway, so the works inside show; put the works inside it),
"kind": liquid (a liquid level that fills/drains; name it, e.g. "tank_water"), light (turns on), flame,
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
Reply with JSON only: {"name", "about", "tags", "aliases", "parts": [...], "paths": {...}, "ports": {...}, "label": [x,y,z]}"""


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
    m = Model()
    for p in parts[:60]:
        if not isinstance(p, dict):
            continue
        shape = str(p.get("shape", "box")).lower()
        if shape not in SHAPES:
            shape = "box"
        size = p.get("size") if isinstance(p.get("size"), (list, tuple)) else [p.get("size", 1.0)]
        s = [_num(x, 1.0, 0.01, 60.0) for x in size] or [1.0]
        while len(s) < 3:
            s.append(s[-1])
        if shape == "box":
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
        elif shape == "tube":
            pts = [_vec(q) for q in (p.get("points") or [])][:40]
            if len(pts) < 2:
                continue
            g = M.tube(pts, s[0], 8)
        else:  # extrude
            poly = [_vec(q, 2) for q in (p.get("poly") or [])][:24]
            if len(poly) < 3:
                continue
            g = M.extrude(poly, s[0])
        if shape != "tube":
            g = M.xf(g, _vec(p.get("pos")), _vec(p.get("rot"), 3, 0.0, -360, 360))
        kind = str(p.get("kind") or "")
        kind = kind if kind in KINDS else ""
        mo = p.get("motion")
        mo = [x for x in (motion_mod.check(q) for q in (mo if isinstance(mo, list) else [mo])) if x]
        mat = str(p.get("material") or "").lower()
        m.add(re.sub(r"[^a-z0-9_]+", "_", str(p.get("name") or shape).lower())[:24] or shape, g, _color(p.get("color")),
              emissive=_num(p.get("emissive"), 0.0, 0, 1),
              opacity=_num(p.get("opacity"), 1.0, 0.1, 1.0), shell=bool(p.get("shell", False)), kind=kind,
              pivot=tuple(_vec(p.get("pivot"))), axis=str(p.get("axis") or "y") if p.get("axis") in ("x", "y", "z") else "y",
              motion=(mo[0] if len(mo) == 1 else mo) or None, material=mat if mat in MATERIALS else "")
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
    for name, pt in (recipe.get("ports") or {}).items():
        m.anchors[str(name)] = tuple(_vec(pt))
    if recipe.get("label"):
        m.anchors["label"] = tuple(_vec(recipe["label"]))
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

    def make(**_):
        return model_from_recipe(recipe)

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


def load_all() -> None:
    """Built-in recipes + the ones designed before (Drive)."""
    load_dir(RECIPES_DIR)
    try:
        load_dir(user_dir())
    except Exception:  # noqa: BLE001  (no settings yet: built-in recipes only)
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


def design(name: str, description: str = "", rep=None) -> str | None:
    """Ask the free AI to design an object as a recipe; check it, save it, return its name (None if it failed)."""
    from .. import llm  # noqa: PLC0415

    example = json.loads((RECIPES_DIR / "piston_pump.json").read_text(encoding="utf-8")) if \
        (RECIPES_DIR / "piston_pump.json").exists() else {}
    payload = {"object": name, "what_it_is": description, "example_recipe": example}

    def validate(obj):
        model_from_recipe(obj)

    try:
        _, recipe = llm.generate_json(DESIGN_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate,
                                      rep=rep, task=f"design a {name}", temperature=0.5, max_tokens=5000, strong=True)
    except Exception as exc:  # noqa: BLE001
        from ..messages import StopRequested  # noqa: PLC0415

        if isinstance(exc, StopRequested):
            raise
        return None
    recipe["name"] = name
    try:
        out = register(recipe)
        folder = user_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{out}.json").write_text(json.dumps(recipe, indent=1), encoding="utf-8")
        return out
    except (ValueError, OSError):
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
        made = design(name, str(o.get("about") or o.get("description") or ""), rep)
        if made:
            o["asset"] = made
            done.append(made)
            if rep is not None:
                rep.ok(f"New object “{made}” saved to your library")
        elif rep is not None:
            rep.info(f"↪ No AI designer free: using the closest object for {raw}")
    return done


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
