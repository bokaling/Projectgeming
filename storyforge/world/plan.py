"""The scene plan: strict JSON that describes ONE continuous 3D world and what happens in every scene.

{
  "title": "How cow poop becomes electricity",
  "areas":   [{"id": "barn", "x": 0, "z": 0}, …]                 (places along the world; x/z optional)
  "objects": [{"id": "cows", "asset": "cow", "area": "barn", "pos": [0, -2.4], "y": 0, "rot": -90, "scale": 1,
               "count": 5, "layout": "row", "spacing": 2.6, "color": "", "params": {}, "hidden": false}, …]
  "scenes":  [{"id": "s01", "camera": {"move": "orbit", "target": "barn1", "angle": 30, "height": 25},
               "actions":  [{"do": "appear", "target": "piles", "at": "manure"}, …],
               "labels":   [{"target": "tank1", "text": "Storage tank", "kind": "part", "at": "tank"}],
               "keywords": [{"text": "2,000 cows", "kind": "number", "at": "2,000"}]}, …]
}

`validate()` repairs anything the AI got wrong (unknown assets → closest asset, missing targets → a
sensible one, numbers clamped, scene count = script scene count) and lists every fix it made.
"""

from __future__ import annotations

import copy
import functools
import re

import numpy as np

from . import assets
from . import settings as settings_mod

CAMERA_MOVES = {
    "orbit": "circle slowly around the target", "push_in": "move closer to the target",
    "pull_out": "move back to reveal more", "fly_over": "glide over the target from one side to the other",
    "top_down": "look down from above", "close_up": "very close on the target",
    "low_angle": "low, looking up (big and dramatic)", "follow": "follow a moving target",
    "zoom_into": "dive into the target (then the next scene is inside it)", "cutaway": "orbit while it is cut open",
    "static": "almost still", "reveal": "start close and pull far back",
}
ACTIONS = {
    "appear": "pop in", "disappear": "shrink away", "grow": "grow (from → to size)", "move": "move to a place",
    "spin": "run the machine: engines, motors, compressors, pumps, fans and wheels move (speed 0.3-2)", "fill": "liquid level rises (from → to)",
    "drain": "liquid level falls", "flow": "particles flow from the target to 'to' (REQUIRED: the object id it goes into, or a pipe id)",
    "bubbles": "bubbles rise from it", "smoke": "smoke puffs rise", "sparks": "electric sparks travel from the target to 'to' (REQUIRED: an object id)",
    "light_on": "lights/windows/screens turn on", "light_off": "lights turn off", "glow": "pulse with light",
    "alarm": "pulse red (danger)", "shake": "shake", "cutaway": "cut it open to show the inside",
    "xray": "make the outside see-through", "float": "gently bob and turn (micro world, space)",
    "show_part": "make a hidden part appear (e.g. 'crust')", "hide_part": "hide a part", "count_up": "a number counts up",
    "drop": "fall from above and land with a plop (a poop, a box, a coin…); 'from' = height in m",
    "open": "open the machine's doors / lid / valve / flapper (whole object, or one part: 'fridge1.door')",
    "close": "close them again",
    "lift": "move the machine's lifting part to a level: 'to': 1 = top, 0 = bottom (an elevator car rises, its "
            "counterweight goes down, the ropes and pulley follow)",
}
WIDE_MOVES = {"fly_over", "pull_out", "top_down", "reveal"}
KINDS = {"problem": "red", "part": "orange", "number": "white", "info": "teal"}
LAYOUTS = {"grid", "row", "circle", "scatter", "column"}
ALIASES = {
    "rotate": "spin", "turn": "spin", "run": "spin", "start": "spin", "turn_on": "light_on", "light": "light_on",
    "lights_on": "light_on", "fill_up": "fill", "pour": "flow", "particles": "flow", "travel": "move",
    "drive": "move", "slide": "move", "pop_in": "appear", "show": "appear", "fade_in": "appear", "hide": "disappear",
    "fade_out": "disappear", "explode": "shake", "highlight": "glow", "pulse": "glow", "cut": "cutaway",
    "section": "cutaway", "cross_section": "cutaway", "see_through": "xray", "x_ray": "xray", "electricity": "sparks",
    "bob": "float", "wobble": "float", "warn": "alarm", "danger": "alarm", "empty": "drain", "steam": "smoke",
    "raise": "lift", "go_up": "lift", "rise": "lift", "lower": "lift", "go_down": "lift", "ascend": "lift",
    "descend": "lift", "unlock": "open", "shut": "close", "operate": "spin", "work": "spin",
}
CAM_ALIASES = {"zoom_in": "push_in", "zoom": "push_in", "dolly_in": "push_in", "zoom_out": "pull_out",
               "aerial": "fly_over", "flyover": "fly_over", "fly_through": "fly_over", "track": "follow",
               "overhead": "top_down", "birds_eye": "top_down", "closeup": "close_up", "close": "close_up",
               "dive": "zoom_into", "into": "zoom_into", "x_ray": "cutaway", "cross_section": "cutaway",
               "still": "static", "circle": "orbit", "rotate": "orbit"}
NUM = (int, float)


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", str(text or "").lower()).strip("_")
    return s or "obj"


def _num(v, default, lo, hi):
    try:
        x = float(v)
        if x != x:  # NaN
            raise ValueError
        return float(max(lo, min(hi, x)))
    except (TypeError, ValueError):
        return float(default)  # always a float: 0 and 0.0 must give the same fingerprint


def _xy(v, default=(0.0, 0.0)):
    if isinstance(v, dict):
        v = [v.get("x", 0), v.get("z", v.get("y", 0))]
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        if len(v) == 3:  # [x, y, z] given: use x and z
            v = [v[0], v[2]]
        return [_num(v[0], default[0], -80, 80), _num(v[1], default[1], -80, 80)]
    return list(default)


def _short(text: str, words: int) -> str:
    t = " ".join(str(text or "").split())
    w = t.split()
    return " ".join(w[:words]) if len(w) > words else t


@functools.lru_cache(maxsize=256)
def _has_path(asset: str) -> bool:
    """Things that carry a flow along themselves (pipes, wires, a blood vessel, the intestine)."""
    if assets.REGISTRY[asset].name in ("pipe", "wire"):
        return True
    try:
        return bool(assets.build(asset).paths.get("flow"))
    except Exception:  # noqa: BLE001
        return False


def auto_cutaway(i: int, camera: dict, actions: list, objects: list, done: set) -> dict | None:
    """A machine made to be cut open ("cutaway" tag) shown working or aimed at one of its inner parts: open it up
    once (it stays open), so the viewer sees the works. Not on the hook (shot 1 shows the outside first)."""
    tgt = camera["target"]
    if tgt in done or any(a["do"] in ("cutaway", "xray") and a["target"].split(".")[0] == tgt for a in actions):
        return None
    o = next((x for x in objects if x["id"] == tgt), None)
    if o is None or "cutaway" not in assets.REGISTRY[o["asset"]].tags:
        return None
    if i == 0:  # the hook shows the outside, unless it is about a part hidden inside (a spark in a cylinder)
        if not camera.get("part") or not _inner_part(o, camera["part"]):
            return None
    working = any(a["target"].split(".")[0] == tgt and a["do"] in ("spin", "lift", "open", "flow", "fill", "drain")
                  for a in actions)
    if not working and not camera.get("part"):
        return None
    return {"do": "cutaway", "target": tgt, "at": 0.0, "keep": True}


def _inner_part(o: dict, name: str) -> bool:
    """Is this part of the machine inside its shell (not one of the outer walls)?"""
    from .scene import World  # noqa: PLC0415

    model = assets.build(o["asset"], **o["params"])
    ks = World.part_names(model, name)
    shells = [p.geo.bounds() for p in model.parts if p.shell and p.geo.tris]
    if not ks or any(model.parts[k].shell for k in ks) or not shells:
        return False
    slo, shi = np.min([b[0] for b in shells], 0), np.max([b[1] for b in shells], 0)
    lo, hi = np.min([model.parts[k].geo.bounds()[0] for k in ks], 0), np.max([model.parts[k].geo.bounds()[1] for k in ks], 0)
    c, pad = (lo + hi) / 2, (shi - slo) * 0.15  # well inside the casing, not a handle on its face
    return bool(np.all(c > slo + pad) and np.all(c < shi - pad))


def _paths_of(o: dict) -> set:
    try:
        return set(assets.build(o["asset"], **o["params"]).paths)
    except Exception:  # noqa: BLE001
        return set()


def _flow_target(src: str, objects: list, scene: dict, target) -> str:
    """Where a flow without a 'to' goes: along a pipe/cable that starts at it, else to another thing the same shot
    names, else to the nearest object in its area that has an inlet. '' = nothing sensible (the flow is removed)."""
    by_id = {o["id"]: o for o in objects}
    me = by_id.get(src)
    if me is None:
        return ""
    for o in objects:  # a pipe from this object: the flow follows it
        if str(o.get("from", "")).split(".")[0] == src and o["id"] != src:
            return o["id"]
    names = [(scene.get("camera") or {}).get("target")] if isinstance(scene.get("camera"), dict) else []
    names += [a.get("target") for a in (scene.get("actions") or []) if isinstance(a, dict)]
    names += [lb.get("target") for lb in (scene.get("labels") or []) if isinstance(lb, dict)]
    for n in names:
        t = target(n, "").split(".")[0] if n else ""
        if t and t != src and t in by_id:
            return t

    def has_inlet(o):
        try:
            return "inlet" in assets.build(o["asset"], **o["params"]).anchors
        except Exception:  # noqa: BLE001
            return False

    near = [o for o in objects if o["id"] != src and o["area"] == me["area"] and has_inlet(o)]
    if near:
        return min(near, key=lambda o: (o["pos"][0] - me["pos"][0]) ** 2 + (o["pos"][1] - me["pos"][1]) ** 2)["id"]
    return ""


def guess_setting(aid: str, objects: list, raw_scenes: list, texts: list | None) -> str:
    """farm / town / site (the old pads with props) for farms, towns and industrial sites; else from the words."""
    from .decor import FARM, TOWN  # noqa: PLC0415

    mine = [o for o in objects if o["area"] == aid]
    names = {o["asset"] for o in mine}
    if names & FARM:
        return "farm"
    if names & TOWN and not names & {"elevator"}:
        return "town"
    words: list = []
    names = [o["asset"].replace("_", " ") for o in mine]
    ids = {o["id"] for o in mine}
    for k, sc in enumerate(raw_scenes):
        tgt = str(((sc.get("camera") or {}) if isinstance(sc, dict) else {}).get("target") or "").split(".")[0]
        if tgt in ids and texts and k < len(texts):
            words.append(str(texts[k]))
    found = settings_mod.guess(words, names)
    if found == "studio" and any({"industry", "energy"} & set(assets.REGISTRY[o["asset"]].tags) and "machine" not in
                                 assets.REGISTRY[o["asset"]].tags for o in mine):
        return "site"
    return found


def validate(plan: dict, scenes_text: list[str] | None = None) -> tuple[dict, list[str]]:
    """Clean and repair a plan. Returns (plan, fixes). Never raises for bad content."""
    fixes: list[str] = []
    p = copy.deepcopy(plan) if isinstance(plan, dict) else {}
    out = {"title": str(p.get("title") or "").strip(), "style": p.get("style") if isinstance(p.get("style"), dict) else {}}
    from . import presets  # noqa: PLC0415

    out["preset"] = presets.resolve(p.get("preset")) or presets.guess([out["title"]] + list(scenes_text or []) + [
        str(s.get("text", "")) for s in (p.get("scenes") or []) if isinstance(s, dict)])
    # areas
    areas, seen = [], set()
    for a in p.get("areas") or []:
        if not isinstance(a, dict):
            continue
        aid = slug(a.get("id") or a.get("name") or f"area{len(areas) + 1}")
        while aid in seen:
            aid += "_2"
        seen.add(aid)
        area = {"id": aid}
        if isinstance(a.get("x"), NUM) or isinstance(a.get("z"), NUM):
            area["x"], area["z"] = _num(a.get("x"), 0, -400, 400), _num(a.get("z"), 0, -400, 400)
        if a.get("micro"):
            area["micro"] = True
        st = settings_mod.resolve(a.get("setting"))
        if st:
            area["setting"] = st
        areas.append(area)
    # objects
    objects, ids = [], set()
    for o in p.get("objects") or []:
        if not isinstance(o, dict):
            continue
        raw = o.get("asset") or o.get("type") or o.get("kind") or "crate"
        name = assets.resolve(raw)
        if name != str(raw).lower().replace(" ", "_") and assets.ALIASES.get(str(raw).lower().replace(" ", "_")) != name:
            fixes.append(f"object {o.get('id', raw)}: asset '{raw}' → '{name}'")
        oid = slug(o.get("id") or name)
        while oid in ids:
            oid += "_2"
        ids.add(oid)
        area = slug(o.get("area")) if o.get("area") else ""
        if area and area not in seen:
            areas.append({"id": area})
            seen.add(area)
            fixes.append(f"added missing area '{area}'")
        info = assets.REGISTRY[name]
        params = {k: v for k, v in (o.get("params") or {}).items() if k in info.params} \
            if isinstance(o.get("params"), dict) else {}
        obj = {
            "id": oid, "asset": name, "area": area, "pos": _xy(o.get("pos")), "y": _num(o.get("y"), 0, 0, 40),
            "rot": _num(o.get("rot"), 0, -360, 360), "scale": _num(o.get("scale"), 1, 0.05, 25),
            "count": int(_num(o.get("count"), 1, 1, 60)), "spacing": _num(o.get("spacing"), 0, 0, 30),
            "layout": o.get("layout") if o.get("layout") in LAYOUTS else "row", "params": params,
            "color": str(o.get("color") or "").strip(), "hidden": bool(o.get("hidden", False)),
        }
        if obj["color"] and "color" in info.params:
            obj["params"].setdefault("color", obj["color"])
        for k in ("from", "to"):  # pipes, cables, chains: routed between two ports ("tank1.outlet")
            if o.get(k):
                obj[k] = str(o[k]).strip()
        if o.get("mount"):  # sits on / inside another object ("car1.engine_bay")
            obj["mount"] = str(o["mount"]).strip()
        if o.get("about") or o.get("description"):
            obj["about"] = str(o.get("about") or o.get("description"))[:160]
        objects.append(obj)
    if not areas:
        areas.append({"id": "main"})
        seen.add("main")
    for obj in objects:
        if not obj["area"]:
            obj["area"] = areas[0]["id"]
    micro_areas = {a["id"] for a in areas if a.get("micro")}
    for obj in objects:  # real size: a bottle is never bigger than the person holding it
        info = assets.REGISTRY[obj["asset"]]
        if obj["area"] in micro_areas or ("symbol" in info.tags and obj["asset"] not in assets.REAL_SIZE) or \
                out["preset"] in ("body", "space"):
            continue  # tiny worlds, the inside of the body and space are drawn zoomed
        real = assets.real_scale(obj["asset"], obj["params"])
        if real is None:
            continue
        if abs(obj["scale"] - 1.0) < 1e-9:
            obj["scale"] = round(real, 4)
            fixes.append(f"object {obj['id']}: real size ({assets.REAL_SIZE[obj['asset']]} m)")
        elif not real * 0.6 - 1e-6 <= obj["scale"] <= real * 1.6 + 1e-6:
            obj["scale"] = round(min(real * 1.6, max(real * 0.6, obj["scale"])), 4)
            fixes.append(f"object {obj['id']}: size kept close to real ({assets.REAL_SIZE[obj['asset']]} m)")
    if not objects:
        objects.append({"id": "crate", "asset": "crate", "area": areas[0]["id"], "pos": [0, 0], "y": 0, "rot": 0,
                        "scale": 1, "count": 1, "spacing": 0, "layout": "row", "params": {}, "color": "", "hidden": False})
        fixes.append("the plan had no objects: added a crate")
    out["areas"], out["objects"] = areas, objects
    for a in areas:  # the place around each area's machine (kitchen, bathroom, garage, street…), guessed if missing
        if not a.get("micro") and "setting" not in a:
            a["setting"] = guess_setting(a["id"], objects, p.get("scenes") or [], scenes_text)
    ids = {o["id"] for o in objects}
    for o in objects:
        for k in ("from", "to"):
            if k in o and slug(o[k].split(".")[0]) not in ids:
                fixes.append(f"{o['id']}: '{k}' {o[k]} is not an object: the link was removed")
                o.pop("from", None)
                o.pop("to", None)
            elif k in o:
                base, dot, port = o[k].partition(".")
                o[k] = slug(base) + (dot + port if dot else "")
    built = {o["id"]: assets.build(o["asset"], **o["params"]) for o in objects}
    parts_of = {k: {pt.name for pt in m.parts} for k, m in built.items()}
    for o in objects:  # a mount must name another object and one of its anchor points
        if "mount" in o:
            base, _, anchor = o["mount"].partition(".")
            base = slug(base)
            if base == o["id"] or base not in built or (anchor and anchor not in built[base].anchors):
                fixes.append(f"{o['id']}: mount '{o['mount']}' doesn't exist: it stands on the ground")
                o.pop("mount")
            else:
                o["mount"] = base + ("." + anchor if anchor else "")
                o["area"] = next(x["area"] for x in objects if x["id"] == base)

    def focus_ok(oid: str, name: str) -> bool:
        m = built.get(oid)
        if m is None:
            return False
        from .scene import World  # noqa: PLC0415

        return bool(World.part_names(m, name)) or name in m.anchors

    def target(t, fallback):
        t = str(t or "").strip()
        base = slug(t.split(".")[0]) if t else ""
        if base in ids:
            return base + ("." + t.split(".", 1)[1] if "." in t else "")
        if t:  # 'the cows' / 'cow' → the object made of that asset
            name = assets.resolve(t)
            for o in objects:
                if o["asset"] == name:
                    return o["id"]
        return fallback

    # scenes
    raw_scenes = [s for s in (p.get("scenes") or []) if isinstance(s, dict)]
    n = len(scenes_text) if scenes_text is not None else len(raw_scenes)
    if scenes_text is not None and len(raw_scenes) != n:
        fixes.append(f"the plan had {len(raw_scenes)} scenes, the script has {n}: adjusted")
    scenes = []
    cut_done: set = set()
    last_target = objects[0]["id"]
    for i in range(max(1, n)):
        s = raw_scenes[i] if i < len(raw_scenes) else {"camera": {"move": "orbit", "target": last_target}}
        cam = s.get("camera") if isinstance(s.get("camera"), dict) else {"move": str(s.get("camera") or "orbit")}
        move = slug(cam.get("move") or "orbit")
        move = CAM_ALIASES.get(move, move)
        if move not in CAMERA_MOVES:
            fixes.append(f"scene {i + 1}: camera '{cam.get('move')}' → orbit")
            move = "orbit"
        full = target(cam.get("target"), last_target)
        tgt = full.split(".")[0]
        part = full.split(".", 1)[1] if "." in full else str(cam.get("part") or "").strip()
        last_target = tgt
        if i == 0 and move in WIDE_MOVES:  # the hook is close and direct, never a far-away wide shot
            fixes.append(f"scene 1: camera '{move}' → close_up (the first shot is the hook)")
            move = "close_up"
        camera = {"move": move, "target": tgt}
        if part:
            if focus_ok(tgt, part):
                camera["part"] = part  # aim at one part of the machine (lift1.car, eng1.piston)
            else:
                fixes.append(f"scene {i + 1}: camera part '{part}' is not a part of {tgt}: the whole object")
        for k, lo, hi in (("angle", -720, 720), ("to_angle", -720, 720), ("height", -5, 89), ("distance", 0.5, 300),
                          ("zoom", 0.2, 5), ("fov", 15, 80)):
            if isinstance(cam.get(k), NUM):
                camera[k] = _num(cam[k], 0, lo, hi)
        actions = []
        for a in s.get("actions") or []:
            if not isinstance(a, dict):
                continue
            do = slug(a.get("do") or a.get("type") or a.get("action") or "")
            do = ALIASES.get(do, do)
            if do not in ACTIONS:
                fixes.append(f"scene {i + 1}: unknown action '{a.get('do')}' removed")
                continue
            tg = target(a.get("target"), "")
            if not tg:
                fixes.append(f"scene {i + 1}: action '{do}' without a known target removed")
                continue
            act = {"do": do, "target": tg}
            if a.get("at") is not None:
                act["at"] = a["at"] if isinstance(a["at"], NUM) else str(a["at"])
            for k in ("dur", "from", "to_value", "speed", "stagger", "y"):
                if isinstance(a.get(k), NUM):
                    act[k] = float(a[k])
            if do in ("flow", "sparks", "move"):
                to = a.get("to")
                if isinstance(to, (list, tuple)):
                    act["to"] = _xy(to)
                elif to is not None:
                    tt = target(to, "")
                    if tt and tt.split(".")[0] != tg.split(".")[0]:  # a flow into itself goes nowhere
                        act["to"] = tt
                if do in ("flow", "sparks") and "to" not in act and not (
                        isinstance(a.get("path"), str) and a["path"] in _paths_of(
                            next(o for o in objects if o["id"] == tg.split(".")[0]))) and not _has_path(next(
                        o["asset"] for o in objects if o["id"] == tg.split(".")[0])):
                    to = _flow_target(tg.split(".")[0], objects, s, target)
                    if not to:
                        fixes.append(f"scene {i + 1}: '{do}' from {tg} has no 'to' (where does it go?): removed")
                        continue
                    act["to"] = to
                    fixes.append(f"scene {i + 1}: '{do}' from {tg} had no 'to': it now goes to {to}")
            elif isinstance(a.get("to"), NUM):
                act["to_value"] = float(a["to"])
            if do in ("flow", "sparks"):
                own = _paths_of(next(o for o in objects if o["id"] == tg.split(".")[0]))
                if isinstance(a.get("path"), str) and a["path"] in own:
                    act["path"] = a["path"]  # along one of the machine's own paths (an engine's intake, a fridge's loop)
                for k in ("color2",):
                    if isinstance(a.get(k), str) and a[k].strip():
                        act[k] = a[k].strip()
            if do == "lift" and "to_value" not in act and isinstance(a.get("level"), NUM):
                act["to_value"] = float(a["level"])
            if do == "lift" and "to_value" in act:
                act["to_value"] = _num(act["to_value"], 1.0, 0.0, 1.0)
            if do in ("fill", "drain", "open", "close", "lift", "spin", "glow") and "." in tg:
                obj_id, part = tg.split(".", 1)
                if not focus_ok(obj_id, part):  # 'spark' = spark1..spark4 (the same names the camera uses)
                    fixes.append(f"scene {i + 1}: '{do}' on part '{part}' of {obj_id}: no such part, the whole object")
                    act["target"] = obj_id
            if do in ("show_part", "hide_part") and "." not in tg:
                part = str(a.get("part") or "")
                if part in parts_of.get(tg, set()):
                    act["target"] = f"{tg}.{part}"
                else:
                    fixes.append(f"scene {i + 1}: {do} needs a part like 'tank1.crust': removed")
                    continue
            for k in ("color", "keep", "count"):
                if a.get(k) is not None:
                    act[k] = a[k]
            actions.append(act)
        labels = []
        for lb in (s.get("labels") or [])[:4]:
            if not isinstance(lb, dict) or not str(lb.get("text", "")).strip():
                continue
            tg = target(lb.get("target"), tgt)
            kind = lb.get("kind") if lb.get("kind") in KINDS else "part"
            item = {"target": tg.split(".")[0], "text": _short(lb["text"], 4), "kind": kind}
            lpart = tg.split(".", 1)[1] if "." in tg else str(lb.get("part") or "")
            if lpart and focus_ok(item["target"], lpart):
                item["part"] = lpart  # points at that part of the machine
            if lb.get("at") is not None:
                item["at"] = lb["at"] if isinstance(lb["at"], NUM) else str(lb["at"])
            if isinstance(lb.get("from"), NUM) and isinstance(lb.get("to"), NUM):
                item["count"] = [float(lb["from"]), float(lb["to"])]  # "{n} homes" counts up
            elif isinstance(lb.get("count"), (list, tuple)) and len(lb["count"]) == 2 and \
                    all(isinstance(v, NUM) for v in lb["count"]):  # a plan that was checked before
                item["count"] = [float(lb["count"][0]), float(lb["count"][1])]
            labels.append(item)
        keywords = []
        for kw in (s.get("keywords") or [])[:3]:
            if isinstance(kw, str):
                kw = {"text": kw}
            if not isinstance(kw, dict) or not str(kw.get("text", "")).strip():
                continue
            item = {"text": _short(kw["text"], 4), "kind": kw.get("kind") if kw.get("kind") in KINDS else "info"}
            if kw.get("at") is not None:
                item["at"] = kw["at"] if isinstance(kw["at"], NUM) else str(kw["at"])
            keywords.append(item)
        cut = auto_cutaway(i, camera, actions, objects, cut_done)
        if cut:
            actions.insert(0, cut)
            fixes.append(f"scene {i + 1}: {camera['target']} is cut open to show its working parts")
        for a in actions:
            if a["do"] in ("cutaway", "xray"):
                cut_done.add(a["target"].split(".")[0])
        scene = {"id": f"s{i + 1:02d}", "camera": camera, "actions": actions, "labels": labels, "keywords": keywords}
        if scenes_text is not None and i < len(scenes_text):
            scene["text"] = scenes_text[i]
        elif s.get("text"):
            scene["text"] = str(s["text"])
        scenes.append(scene)
    out["scenes"] = scenes
    if isinstance(p.get("ideas"), list):  # step 1 of the AI planner: what every shot must show (kept for the checks)
        out["ideas"] = [{k: (str(d.get(k) or "")[:200] if k != "objects" else
                             [str(x)[:40] for x in (d.get(k) or [])][:6] if isinstance(d.get(k), list) else [])
                         for k in ("see", "subject", "part", "number_visual", "setting", "objects")}
                        for d in p["ideas"] if isinstance(d, dict)]
    return out, fixes


# ---------------------------------------------------------------------------------------------------------------
# Does every shot literally show its line?
# ---------------------------------------------------------------------------------------------------------------

STOP = {"the", "and", "its", "his", "her", "this", "that", "with", "into", "from", "for", "are", "was", "has", "have",
        "inside", "close", "view", "shot", "big", "small", "huge", "giant", "tiny", "part", "parts", "one", "two",
        "real", "whole", "every", "all", "our", "your", "their", "out", "off", "over", "under", "then", "when", "how",
        "what", "why", "who", "which", "very", "more", "most", "it's", "thing", "things", "way", "like", "just"}
SYNONYMS = {"human": "person", "people": "person", "man": "person", "woman": "person", "worker": "person",
            "passenger": "person", "driver": "person", "kid": "person", "child": "person", "cabin": "car",
            "cable": "rope", "cables": "rope", "refrigerator": "fridge", "lavatory": "toilet", "wc": "toilet",
            "automobile": "car", "motor": "motor", "germ": "bacteria", "microbe": "bacteria", "lift": "elevator"}


def _stem(w: str) -> str:
    w = re.sub(r"[^a-z0-9]", "", w.lower())
    w = SYNONYMS.get(w, w)
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes", "zes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return SYNONYMS.get(w[:-1], w[:-1])
    return w


def words_of(text: str) -> set:
    return {_stem(w) for w in re.split(r"[^A-Za-z0-9']+", str(text or "")) if len(w) > 2 and w.lower() not in STOP} - {""}


@functools.lru_cache(maxsize=512)
def _asset_words(name: str) -> frozenset:
    info = assets.REGISTRY.get(name)
    ws = words_of(name.replace("_", " "))
    ws |= words_of(" ".join(a.replace("_", " ") for a, n in assets.ALIASES.items() if n == name))
    if info is not None:
        ws |= words_of(re.split(r"[(:;.]", info.about)[0])  # the first clause: what it IS (not every detail)
    return frozenset(ws)


def object_words(o: dict) -> set:
    return set(_asset_words(o["asset"])) | words_of(o["id"].replace("_", " ")) | words_of(o.get("about", ""))


def part_words(o: dict, part: str) -> set:
    return words_of(part.replace("_", " ")) if part else set()


def subject_of(plan: dict, i: int, texts: list | None = None) -> set:
    """The words that name what shot i is about: the visual idea's subject/part (or, without ideas, nothing)."""
    ideas = plan.get("ideas") or []
    if i < len(ideas):
        return words_of(ideas[i].get("subject", "")) | words_of(ideas[i].get("part", ""))
    return set()


def literal_problems(plan: dict, texts: list | None = None) -> dict:
    """{shot index: why} for shots whose camera subject is not the thing the visual idea (or the line) names."""
    objs = {o["id"]: o for o in plan["objects"]}
    out = {}
    for i, sc in enumerate(plan["scenes"]):
        want = subject_of(plan, i, texts)
        if not want:
            continue
        cam = sc["camera"]
        o = objs.get(cam["target"])
        if o is None:
            continue
        have = object_words(o) | part_words(o, cam.get("part", ""))
        if want & have:
            continue
        idea = (plan.get("ideas") or [{}] * (i + 1))[i]
        match = best_match(plan, want)
        if match:
            out[i] = (f"the camera looks at {o['id']} ({o['asset']}), but the shot is about "
                      f"'{idea.get('subject', '')}': aim at {match[0]}" + (f".{match[1]}" if match[1] else ""))
        else:
            out[i] = (f"the shot is about '{idea.get('subject', '')}' ({idea.get('see', '')[:80]}) but no object shows "
                      f"it: add one (a catalog asset, or a new asset with 'about' and its working parts)")
    return out


def best_match(plan: dict, want: set) -> tuple[str, str] | None:
    """(object id, part or '') that shows these words best: a part of a machine first, then an object."""
    from .scene import World  # noqa: PLC0415

    best, score = None, 0
    for o in plan["objects"]:
        ow = object_words(o)
        try:
            model = assets.build(o["asset"], **o["params"])
        except Exception:  # noqa: BLE001
            continue
        stems = {re.sub(r"\d+$", "", p.name) for p in model.parts} | set(model.anchors)
        for stem in stems:
            pw = words_of(stem.replace("_", " "))
            n = len(want & pw)
            if n and n * 2 + (1 if want & ow else 0) > score and World.part_names(model, stem) or (
                    n and stem in model.anchors and n * 2 > score):
                best, score = (o["id"], stem), n * 2 + (1 if want & ow else 0)
        n = len(want & ow)
        if n and n * 2 > score:
            best, score = (o["id"], ""), n * 2
    return best


def fix_literal(plan: dict, texts: list | None = None) -> tuple[dict, list[str]]:
    """Aim every shot that doesn't show its line at the object (or machine part) that does."""
    fixes = []
    for i, why in literal_problems(plan, texts).items():
        m = best_match(plan, subject_of(plan, i, texts))
        if not m:
            fixes.append(f"scene {i + 1}: {why} (could not fix it automatically)")
            continue
        cam = plan["scenes"][i]["camera"]
        cam["target"] = m[0]
        if m[1]:
            cam["part"] = m[1]
        else:
            cam.pop("part", None)
        fixes.append(f"scene {i + 1}: the camera now shows {m[0]}" + (f".{m[1]}" if m[1] else "") + " (what the line is about)")
    ideas = plan.get("ideas") or []
    for i, sc in enumerate(plan["scenes"]):  # the idea names a part of the machine the camera looks at: aim at it
        cam = sc["camera"]
        if cam.get("part") or i >= len(ideas) or not (ideas[i].get("part") or ideas[i].get("subject")):
            continue
        o = next((x for x in plan["objects"] if x["id"] == cam["target"]), None)
        if o is None:
            continue
        model = assets.build(o["asset"], **o["params"])
        from .scene import World  # noqa: PLC0415

        for want in (ideas[i].get("part", ""), ideas[i].get("subject", "")):
            ws = words_of(want)
            hit = next((n for n in sorted({re.sub(r"\d+$", "", p.name) for p in model.parts} | set(model.anchors))
                        if ws & words_of(n.replace("_", " ")) and (World.part_names(model, n) or n in model.anchors)
                        and n not in ("label", "top", "center")), None)
            if hit:
                cam["part"] = hit
                fixes.append(f"scene {i + 1}: the camera aims at {o['id']}.{hit} (the part the shot is about)")
                break
    return plan, fixes


def summary(plan: dict, timeline: dict | None = None) -> str:
    """The plan in plain words (shown in the app)."""
    objs = {o["id"]: o for o in plan.get("objects", [])}
    lines = [f"### {plan.get('title') or 'Scene plan'}",
             f"**World:** {len(plan.get('areas', []))} areas ({', '.join(a['id'] for a in plan.get('areas', []))}), "
             f"{sum(o['count'] for o in plan.get('objects', []))} objects."]
    for i, s in enumerate(plan.get("scenes", [])):
        dur = ""
        if timeline and i < len(timeline.get("scenes", [])):
            dur = f" · {timeline['scenes'][i]['dur']:.1f} s"
        cam = s["camera"]
        tgt = objs.get(cam["target"], {})
        acts = ", ".join(f"{a['do'].replace('_', ' ')} {a['target']}" + (f" (on “{a['at']}”)" if isinstance(a.get('at'), str) else "")
                         for a in s["actions"]) or "—"
        labels = ", ".join(f"“{lb['text']}”" for lb in s["labels"]) or "—"
        keys = ", ".join(f"{k['text']} ({k['kind']})" for k in s["keywords"]) or "—"
        lines.append(f"\n**Scene {i + 1}**{dur} — *{s.get('text', '')}*\n"
                     f"- 🎥 {cam['move'].replace('_', ' ')} → {cam['target']} ({tgt.get('asset', '?')})\n"
                     f"- ⚙️ {acts}\n- 🏷️ {labels}\n- 🔑 {keys}")
    return "\n".join(lines)


def schema_text() -> str:
    """What the AI must follow (shown in the prompt)."""
    return (
        "Areas: {id, setting, micro?}. Objects: {id, asset, area, pos [x, z], y?, rot?, count?, layout?, spacing?, "
        "params?, color?, hidden?, from?/to? (pipes: 'tank1.outlet'), mount? ('car1.engine_bay'), about? (new assets: "
        "what it is + its working parts)}. Scenes: {camera {move, target ('obj' or 'obj.part'), angle?, height?}, "
        "actions [{do, target ('obj' or 'obj.part'), at, to?, path?, color?, color2?, keep?, speed?}], labels "
        "[{target, text, kind, at, from?, to?}], keywords [{text, kind, at}]}.\n"
        "Camera moves: " + "; ".join(f"{k} = {v}" for k, v in CAMERA_MOVES.items()) + ".\n"
        "Actions: " + "; ".join(f"{k} = {v}" for k, v in ACTIONS.items()) + ".\n"
        "Label/keyword kinds: problem (red), part (orange, names of parts), number (white), info (teal).\n"
        "Layouts for count > 1: row, column, grid, circle, scatter."
    )


def relevant_objects(plan: dict, i: int) -> set:
    """The objects shot i can show: everything in the areas its camera (and the camera it flies in from) looks at,
    plus everything its actions and labels name. A change elsewhere doesn't re-render this shot."""
    obj = {o["id"]: o for o in plan["objects"]}
    sc = plan["scenes"]
    areas = set()
    for k in (i - 1, i):
        if 0 <= k < len(sc):
            t = sc[k]["camera"].get("target")
            if t in obj:
                areas.add(obj[t]["area"])
    ids = {o["id"] for o in plan["objects"] if o["area"] in areas}
    for a in sc[i]["actions"]:
        ids.add(a["target"].split(".")[0])
        if isinstance(a.get("to"), str):
            ids.add(a["to"].split(".")[0])
    ids |= {lb["target"] for lb in sc[i]["labels"]}
    return {x for x in ids if x in obj}
