"""Script → scene plan (JSON). The free AI chain (Gemini first) designs the world; the checker repairs it.

Without any AI the built-in planner still makes a working plan: it finds known objects in each scene's
words (cows, tank, pipe, house…), lays them out in areas, picks varied camera moves, and adds actions,
labels and keywords from the text. Never a dead end.
"""

from __future__ import annotations

import json
import re

from .. import beats, llm
from . import assets, examples
from . import plan as P

PLAN_SYSTEM = """You are the 3D director of a viral low poly "how it works" explainer channel (think clean low poly 3D, dark teal studio, glowing grid floor).
You turn a narrated script into ONE continuous 3D world and a shot plan. The camera flies smoothly from area to area.
Rules:
- Use ONLY assets from the catalog (exact names). Compose new things from simple ones (crate, cylinder_block, ball, pipe, arrow…) with params, color and scale.
- Put the story's places in areas, in story order. Objects stay in their area. Reuse objects in later scenes instead of making copies.
- pos is [x, z] in meters inside the area (x to the right, z toward the viewer), ground is y = 0. Keep objects within 12 m of the area centre and don't overlap them. Use count + layout + spacing for groups (5 cows in a row).
- Tiny things (bacteria, cells, molecules, atoms) go in their own area with "micro": true; reach it with camera "zoom_into" on the container in the scene before.
- Every scene: one camera move with a target object; 1-3 actions that happen ON a spoken word ("at": a word from that scene's text); 0-2 labels (1-3 words, next to an object); 0-2 keywords (only the important words, max 3 words).
- Kinds: problem (red) for problems/dangers, part (orange) for names of parts, number (white) for numbers, info (teal) otherwise.
- Vary the camera (never the same move 3 times in a row). Scene 1 is the hook: a striking, wide, moving shot.
- Exactly one plan scene per script scene, same order.
Reply with JSON only."""


def _scene_texts(script: dict) -> list[str]:
    return [" ".join(ln["text"] for ln in sc.get("lines", [])) or sc.get("narration", "") for sc in script["scenes"]]


def _fingerprint(texts: list[str]) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.lower()).strip() for t in texts)


def example_for(script: dict) -> dict | None:
    """The built-in demo plan when the script is the built-in demo script."""
    from .. import paste  # noqa: PLC0415

    parsed = paste.parse_lines(examples.COW_POOP_SCRIPT)
    demo = [" ".join(ln["text"] for ln in s["lines"]) for s in paste.to_scenes(parsed, "short")]
    mine = _scene_texts(script)
    same = bool(mine) and [_fingerprint([t]) for t in demo[: len(mine)]] == [_fingerprint([t]) for t in mine]
    return examples.COW_POOP_PLAN if same else None  # the whole demo, or its first scenes (Quick test)


def ai_plan(script: dict, length: str, rep=None) -> tuple[str, dict]:
    texts = _scene_texts(script)
    payload = {
        "title": script.get("title", ""),
        "format": "YouTube Short, vertical 9:16 (keep the action narrow and tall)" if length == "short"
        else "long YouTube video, horizontal 16:9",
        "style": script.get("style", ""),
        "scenes": [{"n": i + 1, "text": t, "picture": sc.get("visual", "")} for i, (t, sc) in
                   enumerate(zip(texts, script["scenes"]))],
        "asset_catalog": assets.catalog(),
        "schema": P.schema_text(),
        "example_plan": examples.COW_POOP_PLAN,
        "reply_format": {"title": "…", "areas": [{"id": "…"}], "objects": ["…"], "scenes": ["one per script scene"]},
    }

    def validate(obj):
        if not isinstance(obj, dict) or not isinstance(obj.get("objects"), list) or not isinstance(obj.get("scenes"), list):
            raise ValueError("need 'objects' and 'scenes' lists")
        if not obj["objects"]:
            raise ValueError("no objects")
        if len(obj["scenes"]) < max(1, len(texts) // 2):
            raise ValueError(f"need {len(texts)} scenes (one per script scene), got {len(obj['scenes'])}")

    return llm.generate_json(PLAN_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate, rep=rep,
                             task="scene plan", temperature=0.6, max_tokens=12000, strong=True)


def make_plan(script: dict, length: str = "short", rep=None) -> tuple[dict, str, list[str]]:
    """→ (validated plan, who made it, fixes)."""
    texts = _scene_texts(script)
    raw, provider = example_for(script), "Built-in example plan"
    if raw is None:
        try:
            provider, raw = ai_plan(script, length, rep)
        except Exception as exc:  # noqa: BLE001
            from ..messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            if rep is not None:
                rep.warn("The AI planner is busy, so I made a simple plan from the words of your script "
                         "(add a free GEMINI_API_KEY for much better scenes).")
            raw, provider = offline_plan(script), "Built-in planner (no AI)"
    plan, fixes = P.validate(raw, texts)
    plan["title"] = plan.get("title") or script.get("title", "")
    return plan, provider, fixes


# ---------------------------------------------------------------------------
# No AI: a simple planner from the words
# ---------------------------------------------------------------------------

MOVES = ["orbit", "push_in", "fly_over", "close_up", "pull_out", "low_angle", "orbit", "top_down", "push_in"]


def find_assets(text: str) -> list[str]:
    """Known objects named in a text, in order ('the tank fills' → ['tank'])."""
    found = []
    low = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    words = low.split()
    names = set(assets.REGISTRY) | set(assets.ALIASES)
    for k in range(len(words)):
        for n in (3, 2, 1):
            phrase = "_".join(words[k:k + n])
            for cand in (phrase, phrase.rstrip("s"), phrase[:-2] if phrase.endswith("es") else ""):
                if cand and cand in names:
                    name = assets.ALIASES.get(cand, cand)
                    if name not in found and name not in ("ground", "platform", "crate"):
                        found.append(name)
                    break
    return found


def offline_plan(script: dict) -> dict:
    texts = _scene_texts(script)
    areas, objects, scenes = [], [], []
    by_asset: dict[str, str] = {}
    last = None
    for i, (sc, text) in enumerate(zip(script["scenes"], texts)):
        found = find_assets(sc.get("visual", "") + " " + text)[:3]
        if not found and last is None:
            found = ["sign_number"]
        new = [a for a in found if a not in by_asset]
        if new:
            area = f"area{len(areas) + 1}"
            micro = any(a in ("bacteria", "methane") for a in new)
            areas.append({"id": area, **({"micro": True} if micro else {})})
            for k, a in enumerate(new):
                oid = f"{a}{len(objects) + 1}"
                info = assets.REGISTRY[a]
                group = a in ("cow", "house", "tree", "person", "bacteria", "methane", "manure")
                objects.append({"id": oid, "asset": a, "area": area, "pos": [(k - (len(new) - 1) / 2) * 7.0, 0],
                                "count": 4 if group else 1, "layout": "scatter" if micro else "row",
                                "y": 1.0 if micro else 0, "params": {}})
                by_asset[a] = oid
                del info  # (only the name is needed)
        ids = [by_asset[a] for a in found] or ([last] if last else [objects[0]["id"]])
        target = ids[0]
        last = target
        actions = []
        for oid in ids:
            obj = next(o for o in objects if o["id"] == oid)
            model = assets.build(obj["asset"])
            kinds = {p.kind for p in model.parts}
            word = _first_word(text)
            if oid in [by_asset.get(a) for a in new]:
                actions.append({"do": "appear", "target": oid, "at": 0.08})
            if "blade" in kinds:
                actions.append({"do": "spin", "target": oid, "at": word})
            elif "light" in kinds:
                actions.append({"do": "light_on", "target": oid, "at": word})
            elif "liquid" in kinds:
                actions.append({"do": "fill", "target": oid, "at": word})
            elif "wheel" in kinds:
                actions.append({"do": "move", "target": oid, "to": [obj["pos"][0] + 6, obj["pos"][1] + 2]})
            elif obj["asset"] in ("pipe", "wire"):
                actions.append({"do": "flow" if obj["asset"] == "pipe" else "sparks", "target": oid, "at": 0.1})
            elif obj["asset"] in ("bacteria", "methane"):
                actions.append({"do": "float", "target": oid})
            elif obj["asset"] == "manure":
                actions.append({"do": "grow", "target": oid, "at": word})
        labels = [{"target": target, "text": next(o for o in objects if o["id"] == target)["asset"].replace("_", " "),
                   "kind": "part", "at": 0.2}]
        scenes.append({"camera": {"move": MOVES[i % len(MOVES)], "target": target},
                       "actions": actions[:3], "labels": labels, "keywords": _keywords(text)})
    return {"title": script.get("title", ""), "areas": areas, "objects": objects, "scenes": scenes}


def _first_word(text: str) -> float | str:
    words = [w for w in re.findall(r"[A-Za-z']+", text or "") if len(w) > 4]
    return words[0] if words else 0.2


def _keywords(text: str) -> list[dict]:
    out = []
    m = re.search(r"(\d[\d,.]*\s*(?:%|[A-Za-z]+)?)", text or "")
    if m:
        out.append({"text": m.group(1).strip(), "kind": "number", "at": m.group(1).split()[0]})
    bad = beats.has_any(text, beats.SHOCK)
    if bad and len(out) < 2:
        out.append({"text": bad[0], "kind": "problem", "at": bad[0]})
    return out

