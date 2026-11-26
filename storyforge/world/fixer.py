"""🔧 Fix one shot: you type what to change ("make the tank bigger", "show the gas flowing"),
the free AI edits that shot's plan, and only the shots that show the change are rendered again.

Without any AI, simple rules understand the most common requests (bigger, smaller, closer, wider, from
above, spin, flow, cut open, x-ray, light up, smoke, colors, labels, keywords, add/hide an object).
"""

from __future__ import annotations

import copy
import json
import re

from .. import llm
from . import assets
from . import plan as P

FIX_SYSTEM = """You edit ONE shot of a 3D scene plan for a low poly "how it works" explainer video.
You get the whole world (areas, objects), the shot to change (its JSON and its narration) and the user's instruction.
Rules:
- Change only what the instruction asks. Keep everything else in the shot the same.
- You may change objects (scale, color, params, count, pos) or add new objects (only assets from the catalog).
- Actions happen on a spoken word of THIS shot ("at": a word from its narration) or a fraction 0-1.
- Keep labels 1-3 words and keywords max 3 words.
Reply with JSON only: {"scene": {the full new shot}, "objects": [only objects you changed or added, full objects], "changes": ["short notes"]}"""

COLORS = {"red": "#d9534f", "blue": "#3d8fd6", "green": "#4aa564", "yellow": "#f4c430", "orange": "#f28c28",
          "purple": "#9a6ad6", "pink": "#f2a7b5", "white": "#f4f1ea", "black": "#2a2a2e", "gray": "#9aa3ab",
          "grey": "#9aa3ab", "brown": "#7a5232", "teal": "#2cc7b8", "gold": "#f6c445", "silver": "#c7cfd6"}
CAMERA_WORDS = [("top down", "top_down"), ("from above", "top_down"), ("bird", "top_down"), ("overhead", "top_down"),
                ("fly over", "fly_over"), ("flyover", "fly_over"), ("low angle", "low_angle"), ("from below", "low_angle"),
                ("orbit", "orbit"), ("circle around", "orbit"), ("go around", "orbit"), ("follow", "follow"),
                ("push in", "push_in"), ("pull out", "pull_out"), ("pull back", "pull_out"), ("reveal", "reveal"),
                ("static", "static"), ("still camera", "static"), ("close up", "close_up"), ("close-up", "close_up")]
FLOW_COLORS = {"gas": "#9fe870", "biogas": "#9fe870", "water": "#3aa6d9", "steam": "#dfe6ea", "oil": "#3b3f46",
               "manure": "#6b4a2c", "slurry": "#6b4a2c", "blood": "#c0392b", "air": "#bfe9ff"}


def ai_fix(plan: dict, i: int, instruction: str, scene_text: str, rep=None, quick: bool = False) -> tuple[str, dict]:
    payload = {
        "instruction": instruction,
        "shot_number": i + 1,
        "narration": scene_text,
        "shot": plan["scenes"][i],
        "world": {"areas": plan["areas"], "objects": plan["objects"]},
        "asset_catalog": assets.catalog(),
        "schema": P.schema_text(),
    }

    def validate(obj):
        if not isinstance(obj, dict) or not isinstance(obj.get("scene"), dict):
            raise ValueError("need a 'scene' object")
        if not isinstance(obj.get("objects", []), list):
            raise ValueError("'objects' must be a list")

    return llm.generate_json(FIX_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate, rep=rep,
                             task="fix a shot", temperature=0.4, max_tokens=6000, strong=not quick)


def apply_ai(plan: dict, i: int, reply: dict) -> tuple[dict, list[str]]:
    plan = copy.deepcopy(plan)
    new_scene = dict(reply["scene"])
    new_scene["id"] = plan["scenes"][i].get("id", f"s{i + 1:02d}")
    plan["scenes"][i] = new_scene
    by_id = {o["id"]: o for o in plan["objects"]}
    for o in reply.get("objects") or []:
        if not isinstance(o, dict) or not o.get("id"):
            continue
        if o["id"] in by_id:
            by_id[o["id"]].update({k: v for k, v in o.items() if k != "id"})
        else:
            o.setdefault("area", by_id.get(_cam_target(plan, i), {}).get("area", ""))
            plan["objects"].append(o)
    changes = [str(c) for c in (reply.get("changes") or [])][:6] or ["The AI changed this shot."]
    return plan, changes


def _cam_target(plan: dict, i: int) -> str:
    return plan["scenes"][i]["camera"].get("target", "")


def _named_objects(plan: dict, text: str) -> list[str]:
    """Objects the instruction talks about ('the tank' → tank1)."""
    from .planner import find_assets  # noqa: PLC0415

    low = text.lower()
    found = [o["id"] for o in plan["objects"] if re.search(rf"\b{re.escape(o['id'].lower())}\b", low)]
    for name in find_assets(text):
        found += [o["id"] for o in plan["objects"] if o["asset"] == name and o["id"] not in found]
    return found


def _quoted(text: str, after: str) -> str:
    m = re.search(rf"{after}\w*\s*[:=]?\s*[\"“'‘]([^\"”'’]+)[\"”'’]", text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(rf"{after}\w*\s*[:=]?\s+(?:that says\s+|saying\s+)?([\w %°.,+-]+)$", text, re.I)
    return m.group(1).strip() if m else ""


def rule_fix(plan: dict, i: int, instruction: str, scene_text: str = "") -> tuple[dict, list[str]]:
    """Understand simple requests without AI. Returns (new plan, what changed). Nothing understood → no changes."""
    plan = copy.deepcopy(plan)
    text = " " + instruction.lower().strip() + " "
    sc = plan["scenes"][i]
    cam = sc["camera"]
    named = _named_objects(plan, instruction)
    target = named[0] if named else cam.get("target") or plan["objects"][0]["id"]
    obj = next((o for o in plan["objects"] if o["id"] == target), plan["objects"][0])
    changes: list[str] = []
    word = _first_long_word(scene_text)

    def has(*words):
        return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text) for w in words)

    def add_action(do, tgt=None, **kw):
        tgt = tgt or target
        if not any(a["do"] == do and a["target"] == tgt for a in sc["actions"]):
            sc["actions"].append({"do": do, "target": tgt, "at": kw.pop("at", word), **kw})
            changes.append(f"{do.replace('_', ' ')}: {tgt}")

    # size and number
    much = 2.0 if has("much", "way", "huge", "giant", "twice", "double") else 1.5
    if has("bigger", "larger", "huge", "giant", "big", "enlarge"):
        obj["scale"] = round(float(obj.get("scale", 1)) * much, 2)
        changes.append(f"{target} is {much:g}× bigger")
    elif has("smaller", "tiny", "little", "shrink"):
        obj["scale"] = round(float(obj.get("scale", 1)) / much, 2)
        changes.append(f"{target} is {much:g}× smaller")
    m = re.search(r"\b(\d{1,2})\s+([a-z]+)", text)
    if m and assets.resolve(m.group(2)) == obj["asset"]:
        obj["count"] = int(m.group(1))
        changes.append(f"{obj['count']} × {obj['asset']}")
    else:
        m = re.search(r"\bmore\s+([a-z]+)", text)
        if m and assets.resolve(m.group(1)) == obj["asset"]:  # "more cows"
            obj["count"] = int(obj.get("count", 1)) + 2
            changes.append(f"{obj['count']} × {obj['asset']}")
    # color
    for name, hexc in COLORS.items():
        if has(name) and not has(f"{name} light"):
            obj["color"] = hexc
            obj.setdefault("params", {})["color"] = hexc
            changes.append(f"{target} is {name}")
            break
    # camera
    for words, move in CAMERA_WORDS:
        if words in text:
            if cam.get("move") != move:
                cam["move"] = move
                changes.append(f"camera: {move.replace('_', ' ')}")
            break
    if has("closer", "zoom in", "nearer", "tighter"):
        cam["zoom"] = round(float(cam.get("zoom", 1.0)) * 1.4, 2)
        changes.append("camera closer")
    elif has("wider", "further", "farther", "zoom out", "whole", "everything"):
        cam["zoom"] = round(float(cam.get("zoom", 1.0)) / 1.4, 2)
        changes.append("camera further away")
    if named and named[0] != cam.get("target") and has("look at", "show the", "focus", "camera on", "point at"):
        cam["target"] = named[0]
        changes.append(f"camera looks at {named[0]}")
    # actions
    if has("flow", "flowing", "flows", "pour", "pump", "pumping", "moving through"):
        tgt = target
        if "flow" not in assets.build(obj["asset"], **obj.get("params", {})).paths:
            pipes = [o["id"] for o in plan["objects"] if "flow" in assets.build(o["asset"]).paths
                     and o["area"] == obj["area"]] or [o["id"] for o in plan["objects"] if o["asset"] == "pipe"]
            tgt = pipes[0] if pipes else target
        color = next((c for k, c in FLOW_COLORS.items() if has(k)), None)
        add_action("flow", tgt, at=0.1, **({"color": color} if color else {}))
    if has("spin", "spinning", "rotate", "rotating", "turn", "turning", "run", "running", "start"):
        if has("stop"):
            sc["actions"] = [a for a in sc["actions"] if not (a["do"] == "spin" and a["target"] == target)]
            changes.append(f"{target} stops")
        else:
            add_action("spin")
    if has("cut", "cutaway", "cut open", "inside", "cross section", "cross-section", "open it"):
        add_action("cutaway", at=0.1)
    if has("x-ray", "xray", "x ray", "see through", "see-through", "transparent"):
        add_action("xray", at=0.1)
    if has("light", "lights", "glow", "shine", "turn on", "power on"):
        kinds = {p.kind for p in assets.build(obj["asset"], **obj.get("params", {})).parts}
        add_action("light_on" if "light" in kinds else "glow")
    if has("smoke", "steam", "exhaust"):
        add_action("smoke")
    if has("bubble", "bubbles", "bubbling", "boil", "boiling"):
        add_action("bubbles", at=0.1)
    if has("spark", "sparks", "electricity", "current", "power flowing"):
        add_action("sparks", at=0.1)
    if has("shake", "shaking", "vibrate"):
        add_action("shake")
    if has("alarm", "danger", "dangerous", "warning", "red alert"):
        add_action("alarm")
    if has("fill", "filling", "fills up"):
        add_action("fill")
    if has("empty", "drain", "draining"):
        add_action("drain")
    if has("hide", "remove", "delete", "get rid") and named and not has("label", "keyword", "caption"):
        add_action("disappear", named[0], at=0.0)
    if has("appear", "pop in", "show up"):
        add_action("appear")
    # add a new object: "add a pump", "put 3 trees next to the barn"
    m = re.search(r"\b(?:add|put|place)\s+(?:a |an |some |(\d{1,2}) )?([a-z ]+?)(?:\s+(?:next to|near|by|beside|"
                  r"behind|in front of|on|to)\b|$)", text.strip())
    if m and not has("label", "keyword", "caption"):
        key = m.group(2).strip().replace(" ", "_")
        if any(k in assets.REGISTRY or k in assets.ALIASES for k in (key, key.rstrip("s"))):
            name = assets.resolve(key)
            nid = f"{name}_{len(plan['objects']) + 1}"
            pos = obj.get("pos", [0, 0])
            plan["objects"].append({"id": nid, "asset": name, "area": obj["area"], "pos": [pos[0] + 5, pos[1] + 2],
                                    "count": int(m.group(1) or 1), "layout": "row", "hidden": True})
            sc["actions"].append({"do": "appear", "target": nid, "at": 0.1})
            changes.append(f"added {nid}")
    # labels and keywords
    if has("label", "labels", "name tag"):
        if has("remove", "no", "hide", "delete", "without"):
            sc["labels"] = []
            changes.append("labels removed")
        else:
            txt = _quoted(instruction, "label") or obj["asset"].replace("_", " ")
            sc["labels"] = [lb for lb in sc["labels"] if lb["target"] != target][:3] + [
                {"target": target, "text": txt, "kind": "part", "at": 0.2}]
            changes.append(f"label “{txt}”")
    if has("keyword", "keywords", "caption", "captions", "title text"):
        if has("remove", "no", "hide", "delete", "without"):
            sc["keywords"] = []
            changes.append("keywords removed")
        else:
            txt = _quoted(instruction, "keyword") or _quoted(instruction, "caption")
            if txt:
                kind = "number" if re.search(r"\d", txt) else ("problem" if has("problem", "danger", "red") else "info")
                sc["keywords"] = sc["keywords"][:1] + [{"text": txt, "kind": kind, "at": 0.15}]
                changes.append(f"keyword “{txt}”")
    return plan, changes


def _first_long_word(text: str):
    words = [w for w in re.findall(r"[A-Za-z']+", text or "") if len(w) > 4]
    return words[0] if words else 0.15


def fix(plan: dict, i: int, instruction: str, scene_text: str, rep=None, quick: bool = False,
        use_ai: bool = True) -> tuple[dict, list[str], str]:
    """→ (new plan, changes, who did it). Raises ValueError if nothing could be understood.
    quick: the light Gemini model first, no long waits (automatic checks); use_ai=False: only the simple rules."""
    try:
        if not use_ai:
            raise RuntimeError("rules only")
        provider, reply = ai_fix(plan, i, instruction, scene_text, rep, quick)
        new, changes = apply_ai(plan, i, reply)
        checked, _ = P.validate(new, None)
        if checked["scenes"][i] != P.validate(plan, None)[0]["scenes"][i] or checked["objects"] != \
                P.validate(plan, None)[0]["objects"]:
            return new, changes, provider
    except Exception as exc:  # noqa: BLE001
        from ..messages import StopRequested  # noqa: PLC0415

        if isinstance(exc, StopRequested):
            raise
    new, changes = rule_fix(plan, i, instruction, scene_text)
    if not changes:
        raise ValueError("not understood")
    return new, changes, "Built-in fixer (no AI)"
