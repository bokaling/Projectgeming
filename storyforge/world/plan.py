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
import re

from . import assets

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
    "spin": "spin its wheels/blades/fan (or the whole object)", "fill": "liquid level rises (from → to)",
    "drain": "liquid level falls", "flow": "particles flow from one object to another (or along a pipe)",
    "bubbles": "bubbles rise from it", "smoke": "smoke puffs rise", "sparks": "electric sparks travel to 'to'",
    "light_on": "lights/windows/screens turn on", "light_off": "lights turn off", "glow": "pulse with light",
    "alarm": "pulse red (danger)", "shake": "shake", "cutaway": "cut it open to show the inside",
    "xray": "make the outside see-through", "float": "gently bob and turn (micro world, space)",
    "show_part": "make a hidden part appear (e.g. 'crust')", "hide_part": "hide a part", "count_up": "a number counts up",
}
KINDS = {"problem": "red", "part": "orange", "number": "white", "info": "teal"}
LAYOUTS = {"grid", "row", "circle", "scatter", "column"}
ALIASES = {
    "rotate": "spin", "turn": "spin", "run": "spin", "start": "spin", "turn_on": "light_on", "light": "light_on",
    "lights_on": "light_on", "fill_up": "fill", "pour": "flow", "particles": "flow", "travel": "move",
    "drive": "move", "slide": "move", "pop_in": "appear", "show": "appear", "fade_in": "appear", "hide": "disappear",
    "fade_out": "disappear", "explode": "shake", "highlight": "glow", "pulse": "glow", "cut": "cutaway",
    "section": "cutaway", "cross_section": "cutaway", "see_through": "xray", "x_ray": "xray", "electricity": "sparks",
    "bob": "float", "wobble": "float", "warn": "alarm", "danger": "alarm", "empty": "drain", "steam": "smoke",
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
        return max(lo, min(hi, x))
    except (TypeError, ValueError):
        return default


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


def validate(plan: dict, scenes_text: list[str] | None = None) -> tuple[dict, list[str]]:
    """Clean and repair a plan. Returns (plan, fixes). Never raises for bad content."""
    fixes: list[str] = []
    p = copy.deepcopy(plan) if isinstance(plan, dict) else {}
    out = {"title": str(p.get("title") or "").strip(), "style": p.get("style") if isinstance(p.get("style"), dict) else {}}
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
        objects.append(obj)
    if not areas:
        areas.append({"id": "main"})
        seen.add("main")
    for obj in objects:
        if not obj["area"]:
            obj["area"] = areas[0]["id"]
    if not objects:
        objects.append({"id": "crate", "asset": "crate", "area": areas[0]["id"], "pos": [0, 0], "y": 0, "rot": 0,
                        "scale": 1, "count": 1, "spacing": 0, "layout": "row", "params": {}, "color": "", "hidden": False})
        fixes.append("the plan had no objects: added a crate")
    out["areas"], out["objects"] = areas, objects
    ids = {o["id"] for o in objects}
    parts_of = {o["id"]: {pt.name for pt in assets.build(o["asset"], **o["params"]).parts} for o in objects}

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
    last_target = objects[0]["id"]
    for i in range(max(1, n)):
        s = raw_scenes[i] if i < len(raw_scenes) else {"camera": {"move": "orbit", "target": last_target}}
        cam = s.get("camera") if isinstance(s.get("camera"), dict) else {"move": str(s.get("camera") or "orbit")}
        move = slug(cam.get("move") or "orbit")
        move = CAM_ALIASES.get(move, move)
        if move not in CAMERA_MOVES:
            fixes.append(f"scene {i + 1}: camera '{cam.get('move')}' → orbit")
            move = "orbit"
        tgt = target(cam.get("target"), last_target).split(".")[0]
        last_target = tgt
        camera = {"move": move, "target": tgt}
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
            for k in ("dur", "from", "to_value", "speed", "stagger"):
                if isinstance(a.get(k), NUM):
                    act[k] = float(a[k])
            if do in ("flow", "sparks", "move"):
                to = a.get("to")
                if isinstance(to, (list, tuple)):
                    act["to"] = _xy(to)
                elif to is not None:
                    tt = target(to, "")
                    if tt:
                        act["to"] = tt
                if do in ("flow", "sparks") and "to" not in act and assets.REGISTRY[next(
                        o["asset"] for o in objects if o["id"] == tg.split(".")[0])].name not in ("pipe", "wire"):
                    fixes.append(f"scene {i + 1}: '{do}' from {tg} has no 'to': it flows upward instead")
            elif isinstance(a.get("to"), NUM):
                act["to_value"] = float(a["to"])
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
            if lb.get("at") is not None:
                item["at"] = lb["at"] if isinstance(lb["at"], NUM) else str(lb["at"])
            if isinstance(lb.get("from"), NUM) and isinstance(lb.get("to"), NUM):
                item["count"] = [float(lb["from"]), float(lb["to"])]  # "{n} homes" counts up
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
        scene = {"id": f"s{i + 1:02d}", "camera": camera, "actions": actions, "labels": labels, "keywords": keywords}
        if scenes_text is not None and i < len(scenes_text):
            scene["text"] = scenes_text[i]
        elif s.get("text"):
            scene["text"] = str(s["text"])
        scenes.append(scene)
    out["scenes"] = scenes
    return out, fixes


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
        "Camera moves: " + "; ".join(f"{k} = {v}" for k, v in CAMERA_MOVES.items()) + ".\n"
        "Actions: " + "; ".join(f"{k} = {v}" for k, v in ACTIONS.items()) + ".\n"
        "Label/keyword kinds: problem (red), part (orange, names of parts), number (white), info (teal).\n"
        "Layouts for count > 1: row, column, grid, circle, scatter."
    )
