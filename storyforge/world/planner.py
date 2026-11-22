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
- Vary the camera (never the same move 3 times in a row). Scene 1 is the hook: CLOSE, funny or shocking, showing the
  first line directly (e.g. close_up of one cow dropping a huge poop with a "50 kg" label). Never start wide.
- The camera frames its target automatically (it fills the picture); add the things the line talks about as actions or
  labels in the same area so they are framed together. Use close_up for details, wide moves only for overviews.
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


CHUNK = 14  # long videos are planned in parts of this many shots (one request each)


def ai_plan(script: dict, length: str, rep=None) -> tuple[str, dict]:
    """Shorts: one request. Long videos: one request per CHUNK shots, every request sees the world so far."""
    texts = _scene_texts(script)
    if len(texts) <= CHUNK + 2:
        return _ai_request(script, texts, 0, len(texts), None, length, rep)
    from ..messages import StopRequested  # noqa: PLC0415

    merged = {"title": script.get("title", ""), "areas": [], "objects": [], "scenes": []}
    used = []
    starts = list(range(0, len(texts), CHUNK))
    if len(texts) - starts[-1] < 4 and len(starts) > 1:  # no tiny last part
        starts.pop()
    for k, a in enumerate(starts):
        b = starts[k + 1] if k + 1 < len(starts) else len(texts)
        if rep is not None:
            rep.info(f"🧭 Planning shots {a + 1}-{b} of {len(texts)} (part {k + 1}/{len(starts)})")
        try:
            prov, part = _ai_request(script, texts, a, b, merged if k else None, length, rep)
        except StopRequested:
            raise
        except Exception:  # noqa: BLE001  (this part only: the built-in planner, the rest stays AI)
            if k == 0:
                raise  # nothing worked at all: the caller makes the whole plan offline
            prov = "Built-in planner (no AI)"
            part = _prefixed(offline_plan({"title": "", "scenes": script["scenes"][a:b]}), f"p{a + 1}_")
        merge_part(merged, part, b - a)
        used.append(prov)
    names = list(dict.fromkeys(used))
    return " + ".join(names) + f" ({len(starts)} parts)", merged


def _ai_request(script: dict, texts: list[str], a: int, b: int, world: dict | None, length: str, rep) -> tuple[str, dict]:
    n = b - a
    payload = {
        "title": script.get("title", ""),
        "format": "YouTube Short, vertical 9:16 (keep the action narrow and tall)" if length == "short"
        else "long YouTube video, horizontal 16:9",
        "style": script.get("style", ""),
        "scenes": [{"n": i + 1, "text": texts[i], "picture": script["scenes"][i].get("visual", ""),
                    **({"chapter": script["scenes"][i]["chapter"]} if script["scenes"][i].get("chapter") else {})}
                   for i in range(a, b)],
        "asset_catalog": assets.catalog(),
        "schema": P.schema_text(),
        "example_plan": examples.COW_POOP_PLAN,
        "reply_format": {"title": "…", "areas": [{"id": "…"}], "objects": ["…"], "scenes": ["one per script scene"]},
    }
    if world is not None:  # a later part of a long video
        payload["world_so_far"] = {
            "areas": [x["id"] + (" (micro)" if x.get("micro") else "") for x in world["areas"]],
            "objects": [f"{o['id']}: {o['asset']} in {o.get('area', '')}" + (" ×" + str(o["count"]) if o.get("count", 1) > 1
                                                                              else "") for o in world["objects"]],
            "last_shots": [{"n": a - k, "text": texts[a - k - 1][:160],
                            "camera": (world["scenes"][a - k - 1].get("camera") or {}) if a - k - 1 < len(world["scenes"])
                            else {}} for k in range(min(2, a), 0, -1)],
        }
        payload["this_part"] = (f"Plan ONLY scenes {a + 1} to {b} ({n} scenes). REUSE objects from world_so_far by id "
                                f"(don't repeat them). In 'areas' and 'objects' list ONLY NEW ones; new areas come after the "
                                f"existing ones. Reply with exactly {n} scenes.")
        payload["reply_format"] = {"areas": ["only new areas"], "objects": ["only new objects"],
                                   "scenes": [f"exactly {n}, for scenes {a + 1}..{b}"]}

    def validate(obj):
        if not isinstance(obj, dict) or not isinstance(obj.get("scenes"), list):
            raise ValueError("need a 'scenes' list")
        if not isinstance(obj.get("objects", []), list):
            raise ValueError("'objects' must be a list")
        if world is None and not obj.get("objects"):
            raise ValueError("no objects")
        if len(obj["scenes"]) < max(1, n // 2):
            raise ValueError(f"need {n} scenes (one per script scene), got {len(obj['scenes'])}")

    return llm.generate_json(PLAN_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate, rep=rep,
                             task="scene plan", temperature=0.6, max_tokens=12000, strong=True)


def _prefixed(part: dict, pre: str) -> dict:
    """Give a part's own areas and objects unique names (two offline parts both start at 'area1')."""
    amap = {x["id"]: pre + x["id"] for x in part.get("areas", [])}
    omap = {o["id"]: pre + o["id"] for o in part.get("objects", [])}
    part["areas"] = [{**x, "id": amap[x["id"]]} for x in part.get("areas", [])]
    part["objects"] = [{**o, "id": omap[o["id"]], "area": amap.get(o.get("area"), o.get("area"))}
                       for o in part.get("objects", [])]
    _rename_refs(part.get("scenes", []), omap)
    return part


def _rename_refs(scenes: list, omap: dict) -> None:
    def ren(t):
        if not isinstance(t, str) or not t:
            return t
        base, dot, rest = t.partition(".")
        return omap.get(base, base) + (dot + rest if dot else "")

    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        if isinstance(sc.get("camera"), dict):
            sc["camera"]["target"] = ren(sc["camera"].get("target"))
        for key in ("actions", "labels"):
            for it in sc.get(key) or []:
                if isinstance(it, dict):
                    it["target"] = ren(it.get("target"))
                    if isinstance(it.get("to"), str):
                        it["to"] = ren(it["to"])


def merge_part(world: dict, part: dict, n: int) -> None:
    """Add one planned part of a long video to the world: new areas and objects, exactly n scenes."""
    have_areas = {x["id"] for x in world["areas"] if isinstance(x, dict)}
    for x in part.get("areas") or []:
        if isinstance(x, str):
            x = {"id": x}
        if isinstance(x, dict) and x.get("id") and x["id"] not in have_areas:
            world["areas"].append(x)
            have_areas.add(x["id"])
    have = {o["id"]: o.get("asset") for o in world["objects"] if isinstance(o, dict) and o.get("id")}
    omap = {}
    for o in part.get("objects") or []:
        if not isinstance(o, dict) or not o.get("id"):
            continue
        oid = o["id"]
        if oid in have:
            if assets.resolve(str(have[oid])) == assets.resolve(str(o.get("asset", ""))):
                continue  # the same thing again: reuse it
            new = oid
            while new in have:
                new += "_b"
            omap[oid] = new
            o = {**o, "id": new}
        world["objects"].append(o)
        have[o["id"]] = o.get("asset")
    scenes = [sc for sc in (part.get("scenes") or []) if isinstance(sc, dict)][:n]
    _rename_refs(scenes, omap)
    last = (world["scenes"][-1].get("camera") or {}).get("target") if world["scenes"] else None
    while len(scenes) < n:  # the AI forgot a shot: keep looking at the last thing
        scenes.append({"camera": {"move": "orbit", "target": (scenes[-1].get("camera") or {}).get("target")
                                  if scenes else last}})
    world["scenes"] += scenes


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
GROUPS = {"house", "tree", "person", "bacteria", "methane", "manure", "car", "coin", "molecule", "blood_cell", "virus",
          "cell", "solar_panel", "wind_turbine", "barrel", "rock", "cloud", "skyscraper", "atom"}


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
            micro = any("micro" in assets.REGISTRY[a].tags for a in new)
            areas.append({"id": area, **({"micro": True} if micro else {})})
            for k, a in enumerate(new):
                oid = f"{a}{len(objects) + 1}"
                info = assets.REGISTRY[a]
                group = a in GROUPS or "animal" in info.tags
                objects.append({"id": oid, "asset": a, "area": area, "pos": [(k - (len(new) - 1) / 2) * 7.0, 0],
                                "count": 4 if group else 1, "layout": "scatter" if micro else "row",
                                "y": 1.0 if micro else 0, "params": {}})
                by_asset[a] = oid
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
            if kinds & {"blade", "piston", "rocker"}:
                actions.append({"do": "spin", "target": oid, "at": word})
            elif "light" in kinds:
                actions.append({"do": "light_on", "target": oid, "at": word})
            elif "liquid" in kinds:
                actions.append({"do": "fill", "target": oid, "at": word})
            elif "wheel" in kinds:
                actions.append({"do": "move", "target": oid, "to": [obj["pos"][0] + 6, obj["pos"][1] + 2]})
            elif "flow" in model.paths:
                electric = obj["asset"] in ("wire", "power_line", "neuron")
                actions.append({"do": "sparks" if electric else "flow", "target": oid, "at": 0.1})
            elif "micro" in assets.REGISTRY[obj["asset"]].tags or obj["asset"] in ("cloud", "fish", "bird"):
                actions.append({"do": "float", "target": oid})
            elif "exhaust" in model.anchors:
                actions.append({"do": "smoke", "target": oid, "at": word})
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

