"""Script → scene plan (JSON). The free AI chain (Gemini first) designs the world; the checker repairs it.

Without any AI the built-in planner still makes a working plan: it finds known objects in each scene's
words (cows, tank, pipe, house…), lays them out in areas, picks varied camera moves, and adds actions,
labels and keywords from the text. Never a dead end.
"""

from __future__ import annotations

import json
import re

from .. import beats, llm
from . import assets, examples, presets
from . import plan as P
from . import settings as settings_mod

VISUAL_SYSTEM = """You are the visual director of a viral 3D "how it works" channel (machines and everyday things: engines, elevators,
fridges, toilets, planes, phones). Step 1 of 2: for EVERY narration line, decide what the viewer must SEE so the line is
obvious with the sound off. Plain English, concrete objects only.
Rules:
- The subject is the LITERAL thing the line talks about. A line about a human shows a person; a line about a fridge's
  compressor shows the compressor (inside the fridge); "the car" shows a car. Never a random shape for an idea.
- Machines: show the INSIDE with the real working parts moving (cut open): pistons, valves, cables, pulleys, gears,
  compressor, coils, floats, flappers, motors. Name the exact part in focus ("part").
- Shot types ("shot"): "normal"; "hero" = ONE part alone, big, cut in half on a clean light background (use it 1-3
  times for the key parts: one piston, the compressor, the flapper); "macro" = an extreme close-up on a dark background
  with glow/sparks for the MOST dramatic moment (once per video); "comparison" = a big or tiny number shown with everyday
  things on a plain table ("as heavy as 9 cars", "thinner than a hair", "a water bottle squeezed to a shot glass", a
  seesaw for balance), then back to the machine (1-2 per video, only where the line has such a number).
- Every other number becomes a visual: a counter, a stack of N things, a gauge, a balance scale, a bar chart.
- Real scale: things keep their real size. Tiny things (molecules, bacteria, atoms) are a zoomed-in world ("micro": true).
- The place fits the machine ("setting"): kitchen (fridge, oven), bathroom (toilet, shower), garage (car engine),
  street (elevator building, cars, bright sunny day), living_room, office, desk (small things), lab, factory, outdoors
  (sunny grass, trees, tiny people for scale), studio (clean light studio, when no place fits), table (comparisons).
- Shot 1 shows the opening question directly (the gas pedal pressed, the elevator car rising), close and clear.
  The last shot shows the whole machine working.
- Several lines about the same thing can share one picture: say "same as before" in "see" and keep the subject.
- Keep the narration's facts; never add new numbers or claims.
Reply with JSON only:
{"machine": "the main machine/thing", "shots": [{"n": 1, "see": "what we see, one sentence", "subject": "a noun",
  "part": "the machine part in focus or ''", "shot": "normal|hero|macro|comparison", "objects": ["the nouns in the picture"],
  "moves": "what moves", "number_visual": "", "setting": "garage", "inside": true}]}"""

PLAN_SYSTEM = """You are the 3D director of a viral low poly "how it works" explainer channel. The look: clean low poly 3D, a
clean light studio or a bright sunny day (blue sky, soft clouds, grass, trees, tiny people for scale), soft shadows; cut
faces in deep red. Step 2 of 2: turn the narration AND its visual ideas (step 1) into ONE continuous 3D world
and a calm, clear shot plan.
Rules:
- Follow each shot's visual idea EXACTLY: the camera target is the idea's subject (or the part in focus, as "obj.part",
  e.g. "eng1.piston", "lift1.car", "lift1.sheave").
- PART NAMES: use ONLY the exact names listed under [parts: ...] of that asset in the catalog (for camera targets,
  actions, labels and mounts). Never invent a part name, and never add a separate object for a part the machine already
  has (the elevator already has its car_door, motor, ropes, safety_brakes): target "lift1.car_door" instead.
- Set "preset" (the world look): one of PRESETS. Give every area a "setting": one of SETTINGS.
- Use assets from the catalog (exact names). If the thing a line needs is missing, use a short new snake_case asset name
  and add "about": what it looks like AND its real working parts with their real size; it will be DESIGNED as a new 3D
  object from real shapes and the mechanism kit (gears, pistons, pumps, fans, turbines, belts, springs, motors, heating
  coils…), checked from 3 angles and saved. Then aim at its parts by their real names (drum, magnetron, compressor).
  The kit pieces are also objects (kit_gear_train, kit_turbine…) for simple mechanisms. Never use an unrelated
  object as a stand-in.
- Real scale: every object keeps its real size (scale 1 = real size).
- Machines are cut open: add a "cutaway" action (keep: true) on the first shot that shows the inside; then "spin" to run
  an engine/motor/compressor, "lift" (to 0-1) for an elevator car, "open"/"close" for doors, lids, flappers and valves,
  "fill"/"drain" for liquids.
- HERO shots (camera "hero", target "obj.part"): one part alone, big, cut in half, clean light studio. Use 1-3 per video
  for the key parts the lines explain.
- MACRO shot (camera "macro"): the most dramatic moment, extreme close-up on a dark background; add "glow", "sparks" or
  "flow" on that part. Once per video.
- COMPARISON scenes: for a big or tiny number, add an area {"setting": "table"} with CLEAR everyday things side by
  side that anyone recognises at a glance, at their REAL size (no "scale"): bottle, coin, phone, plate, burger, tomato,
  carrot, cooking_pot, books, shot_glass, water_drop, person, hatchback, taxi, cow, sugar_cube, balance_scale… Pick two or
  three whose real sizes make the number obvious (a 25 cm plate next to a 2.5 cm coin), never abstract blocks. Cut to it
  ("cut": true), then cut back. 1-2 per video, only where a line has such a number.
- PLACES: things stand where they belong in real life: kitchen appliances (microwave, toaster, kettle) on the counter,
  lamps and laptops on a desk, ceiling fans on the ceiling, washers and fridges on the floor against the back wall. Don't
  give them a "y": the settings put them on a counter/desk/ceiling automatically.
- Outdoor places (street, outdoors, farm) are bright and sunny with tiny people for scale.
- Flows show cause and effect: a flow/sparks ALWAYS has "to" (object id) or "path" (one of the object's own [paths]).
- PACING: shots last 4-8 seconds. Slow, eased camera moves: orbit, push_in, close_up, follow, static, reveal; no fast
  spins. The camera flies smoothly between places in the same world; "cut": true only for a big change of place or time
  (and into/out of comparisons). Put visible changes (open, lift, fill) on an EARLY word, so they finish in the shot.
- Every scene: one camera move with a target; 1-3 actions ON a spoken word ("at": a word from that scene's text);
  0-2 labels (small white labels with the part's real name, kind "part"); keywords: 0-1, ONLY for a wow fact
  (a number or a myth buster, max 3 words, e.g. "MORE AIR", "10x SMALLER", "40,000 VOLTS"; kind "wow" or "number").
- Scene 1 shows the opening question directly (close_up or push_in on what it asks about, and it HAPPENS). Never start
  wide. The last scene shows the whole machine working.
- Exactly one plan scene per script scene, same order. Don't invent facts in labels: only words from the narration.
Reply with JSON only.""".replace("PRESETS", ", ".join(presets.PRESETS)).replace("SETTINGS", ", ".join(settings_mod.SETTINGS))


def _scene_texts(script: dict) -> list[str]:
    from .. import paste  # noqa: PLC0415

    return [" ".join(paste.PAUSE.sub(" ", " ".join(ln["text"] for ln in sc.get("lines", [])) or sc.get("narration", "")
                                     ).split()) for sc in script["scenes"]]


def _fingerprint(texts: list[str]) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.lower()).strip() for t in texts)


def example_for(script: dict) -> dict | None:
    """A built-in demo plan when the script is one of the built-in demo scripts (or its first scenes)."""
    from .. import paste  # noqa: PLC0415

    mine = _scene_texts(script)
    if not mine:
        return None
    for demo_script, demo_plan in examples.EXAMPLES:
        parsed = paste.parse_lines(demo_script)
        demo = [" ".join(ln["text"] for ln in s["lines"]) for s in paste.to_scenes(parsed, "short")]
        if [_fingerprint([t]) for t in demo[: len(mine)]] == [_fingerprint([t]) for t in mine]:
            return demo_plan
    return None


CHUNK = 14  # long videos are planned in parts of this many shots (one request each)


def visual_ideas(script: dict, length: str, rep=None) -> list[dict] | None:
    """Step 1: what the viewer must SEE in every shot (plain English). None when no AI answers."""
    texts = _scene_texts(script)
    out: list[dict] = []
    for a in range(0, len(texts), 30):
        b = min(len(texts), a + 30)
        payload = {"title": script.get("title", ""), "format": "YouTube Short 9:16" if length == "short" else "16:9",
                   "lines": [{"n": i + 1, "text": texts[i], "writer_hint": script["scenes"][i].get("visual", "")}
                             for i in range(a, b)],
                   "reply_format": {"machine": "…", "shots": [f"exactly {b - a}, n = {a + 1}..{b}"]}}

        def validate(obj, n=b - a):
            if not isinstance(obj, dict) or not isinstance(obj.get("shots"), list) or len(obj["shots"]) < max(1, n // 2):
                raise ValueError(f"need {n} shots with what we see")

        try:
            _, obj = llm.generate_json(VISUAL_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate,
                                       rep=rep, task="visual ideas", temperature=0.5, max_tokens=6000, strong=True)
        except Exception as exc:  # noqa: BLE001
            from ..messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested) or llm.all_busy(exc):
                raise  # every Gemini model is busy: the built-in planner, no second long wait
            return None
        got = {}
        for sh in obj["shots"]:
            try:
                got[int(sh.get("n")) - 1] = sh
            except (TypeError, ValueError, AttributeError):
                continue
        for i in range(a, b):
            sh = got.get(i) or {}
            out.append({k: str(sh.get(k) or "")[:200] for k in ("see", "subject", "part", "number_visual", "setting",
                                                                "shot")}
                       | {"objects": [str(x)[:40] for x in (sh.get("objects") or [])][:6] if isinstance(
                           sh.get("objects"), list) else [], "inside": bool(sh.get("inside")),
                          "machine": str(obj.get("machine") or "")[:60]})
    return out


def ai_plan(script: dict, length: str, rep=None, ideas: list | None = None, feedback: dict | None = None
            ) -> tuple[str, dict]:
    """Shorts: one request. Long videos: one request per CHUNK shots, every request sees the world so far."""
    texts = _scene_texts(script)
    if len(texts) <= CHUNK + 2:
        return _ai_request(script, texts, 0, len(texts), None, length, rep, ideas, feedback)
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
            prov, part = _ai_request(script, texts, a, b, merged if k else None, length, rep, ideas)
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


def _ai_request(script: dict, texts: list[str], a: int, b: int, world: dict | None, length: str, rep,
                ideas: list | None = None, feedback: dict | None = None) -> tuple[str, dict]:
    n = b - a
    payload = {
        "title": script.get("title", ""),
        "format": "YouTube Short, vertical 9:16 (keep the action narrow and tall)" if length == "short"
        else "long YouTube video, horizontal 16:9",
        "style": script.get("style", ""),
        "scenes": [{"n": i + 1, "text": texts[i], "picture": script["scenes"][i].get("visual", ""),
                    **({"visual_idea": {k: v for k, v in ideas[i].items() if v not in ("", [], False)}}
                       if ideas and i < len(ideas) else {}),
                    **({"chapter": script["scenes"][i]["chapter"]} if script["scenes"][i].get("chapter") else {})}
                   for i in range(a, b)],
        "asset_catalog": assets.catalog(),
        "settings": settings_mod.SETTINGS,
        "schema": P.schema_text(),
        "example_plan": examples.MACHINE_EXAMPLE_PLAN,
        "reply_format": {"title": "…", "areas": [{"id": "…"}], "objects": ["…"], "scenes": ["one per script scene"]},
    }
    if feedback:  # a second try: these shots didn't show their line
        payload["fix_these_shots"] = feedback
        payload["previous_plan"] = feedback.get("_plan")
        feedback.pop("_plan", None)
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
    from . import builder  # noqa: PLC0415

    builder.load_all()  # objects designed before (Drive library)
    texts = _scene_texts(script)
    raw, provider = example_for(script), "Built-in example plan"
    ideas = None
    if raw is None:
        try:
            ideas = visual_ideas(script, length, rep)  # step 1: what we must SEE in every shot
            if rep is not None and ideas:
                rep.info(f"👁️ Visual idea for every shot ({len(ideas)}): e.g. “{ideas[0].get('see', '')[:90]}”")
            provider, raw = ai_plan(script, length, rep, ideas)  # step 2: objects, camera, actions
            builder.ensure_objects(raw, rep)  # objects the library doesn't have: designed by the AI as recipes
            if ideas:
                raw = _second_try(script, length, rep, ideas, raw, texts)
        except Exception as exc:  # noqa: BLE001
            from ..messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            if rep is not None:
                rep.warn("Gemini is busy, so I made the plan with the built-in planner (machines from the library). "
                         "For AI shots, press 🧭 Plan again in a few minutes." if llm.all_busy(exc) else
                         "No AI planner answered, so I made a plan from the words of your script "
                         "(add a free GEMINI_API_KEY for much better scenes).")
            made = builder.compose(str(script.get("title") or ""), " ".join(texts[:3]), rep)  # a new machine: kit
            raw, provider = offline_plan(script), "Built-in planner (no AI)" + (f" + kit {made}" if made else "")
    if ideas:
        raw["ideas"] = ideas
    plan, fixes = P.validate(raw, texts)
    plan, more = P.fix_literal(plan, texts)  # a shot that still doesn't show its line: aim at the thing it names
    fixes += more
    plan["title"] = plan.get("title") or script.get("title", "")
    return plan, provider, fixes


def _second_try(script: dict, length: str, rep, ideas: list, raw: dict, texts: list) -> dict:
    """Shots whose camera subject doesn't literally show the line go back to the AI once, with the reasons."""
    from . import builder  # noqa: PLC0415

    trial = dict(raw, ideas=ideas)
    checked, _ = P.validate(trial, texts)
    bad = P.literal_problems(checked, texts)
    if not bad:
        return raw
    if rep is not None:
        rep.info(f"🔁 {len(bad)} shot(s) didn't show their line ({', '.join(str(k + 1) for k in sorted(bad))}): "
                 "asking the AI to fix them")
    feedback = {f"shot {k + 1}": why for k, why in sorted(bad.items())}
    feedback["_plan"] = raw
    try:
        _, again = ai_plan(script, length, rep, ideas, feedback)
        builder.ensure_objects(again, rep)
    except Exception as exc:  # noqa: BLE001
        from ..messages import StopRequested  # noqa: PLC0415

        if isinstance(exc, StopRequested):
            raise
        return raw
    trial2 = dict(again, ideas=ideas)
    checked2, _ = P.validate(trial2, texts)
    return again if len(P.literal_problems(checked2, texts)) < len(bad) else raw


# ---------------------------------------------------------------------------
# No AI: a simple planner from the words
# ---------------------------------------------------------------------------

MOVES = ["orbit", "push_in", "close_up", "orbit", "pull_out", "low_angle", "static", "push_in"]  # calm, eased moves
PART_MOVES = ["close_up", "orbit", "push_in", "orbit", "low_angle", "push_in"]
DRAMA = ("spark", "flame", "fire", "explod", "burn", "snap", "break", "bang", "boom", "lightning", "volts")
GROUPS = {"house", "tree", "person", "bacteria", "methane", "manure", "car", "coin", "molecule", "blood_cell", "virus",
          "cell", "solar_panel", "wind_turbine", "barrel", "rock", "cloud", "skyscraper", "atom"}


VERBISH = {"lift", "scale", "display", "float", "sink", "drill", "tap", "run", "drive", "fan", "light"}  # usually
# verbs in a sentence ("the handle lifts a chain"): never turned into objects by the built-in planner


def find_assets(text: str) -> list[str]:
    """Known objects named in a text, in order ('the tank fills' → ['tank'])."""
    found = []
    low = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    words = low.split()
    names = (set(assets.REGISTRY) | set(assets.ALIASES)) - VERBISH
    k = 0
    while k < len(words):
        step = 1
        for n in (3, 2, 1):  # the longest name wins: "car engine" is the engine, not also a car
            phrase = "_".join(words[k:k + n])
            hit = next((c for c in (phrase, phrase.rstrip("s"), phrase[:-2] if phrase.endswith("es") else "")
                        if c and c in names), None)
            if hit:
                name = assets.ALIASES.get(hit, hit)
                tags = set(assets.REGISTRY[name].tags) if name in assets.REGISTRY else set()
                if name not in found and name not in ("ground", "platform", "crate") and not tags & {
                        "helper", "terrain", "set"}:
                    found.append(name)
                step = n
                break
        k += step
    return found


def _strip_part_words(text: str, machines: list) -> str:
    """Remove the words that name parts of these machines ("the elevator's motor" is not a separate motor)."""
    words = set()
    for m in machines:  # every part of the machine (its pipes, coils, tubes too), not only the moving ones
        model = assets.build(m)
        names = list(assets.focus_points(m)) + [re.sub(r"\d+$", "", p.name) for p in model.parts]
        for f in names:
            words |= {w for w in f.split("_") if len(w) > 2}
        words |= {"tube", "pipe", "coil", "wire", "cable"} if any("pipe" in n or "capillary" in n or "coil" in n
                                                                  for n in names) else set()
    words -= {"power", "light", "oil", "wall", "side", "top", "base", "floor"}
    return " ".join(w for w in re.split(r"(\W+)", text or "") if w.lower().rstrip("s") not in words and
                    w.lower() not in words)


def offline_plan(script: dict) -> dict:
    texts = _scene_texts(script)
    areas, objects, scenes = [], [], []
    by_asset: dict[str, str] = {}
    shot_kinds: dict = {}  # how many hero / macro shots so far
    last = None
    title_m = [a for a in find_assets(str(script.get("title") or "")) if {"machine", "cutaway"} &
               set(assets.REGISTRY[a].tags) and not a.startswith("kit_")][:1]
    if title_m:  # "How a washing machine works": the machine is there from the start ("the drum" = its drum)
        areas.append({"id": "area1"})
        objects.append({"id": f"{title_m[0]}1", "asset": title_m[0], "area": "area1", "pos": [0.0, 0], "count": 1,
                        "layout": "row", "y": 0, "params": {}})
        by_asset[title_m[0]] = f"{title_m[0]}1"
        last = f"{title_m[0]}1"
    for i, (sc, text) in enumerate(zip(script["scenes"], texts)):
        line = sc.get("visual", "") + " " + text
        present = [a for a in by_asset if {"machine", "cutaway"} & set(assets.REGISTRY[a].tags)]
        first = find_assets(_strip_part_words(line, present))  # "the motor" of the elevator is not a new motor
        new_m = [a for a in first if {"machine", "cutaway"} & set(assets.REGISTRY[a].tags)]
        about = [m for m in present if _named_part(m, line)]  # a part of a machine we already have
        rest = [] if about else [a for a in find_assets(_strip_part_words(line, present + new_m)) if a not in new_m]
        found = list(dict.fromkeys(about + new_m + rest))[:3]  # "the elevator car" is the elevator's car
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
            drives = _drives(model)
            word = _first_word(text)
            if oid in [by_asset.get(a) for a in new]:
                actions.append({"do": "appear", "target": oid, "at": 0.08})
            if "lift" in drives and re.search(r"\b(up|rise|rises|lift|top|climb|down|floor)", text.lower()):
                actions.append({"do": "lift", "target": oid, "at": word})
            elif "open" in drives and re.search(r"\b(open|opens|door|lid|flush|pull)", text.lower()):
                actions.append({"do": "open", "target": oid, "at": word})
            elif "run" in drives:
                actions.append({"do": "spin", "target": oid, "at": 0.0, "speed": 0.6})
            elif kinds & {"blade", "piston", "rocker"}:
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
        cam = {"move": MOVES[i % len(MOVES)], "target": target}
        part = _named_part(next(o for o in objects if o["id"] == target)["asset"], sc.get("visual", "") + ". " + text)
        label = next(o for o in objects if o["id"] == target)["asset"].replace("_", " ")
        if part:  # the line names a part of the machine ("the sheave", "the pistons"): look at it
            cam["target"] = f"{target}.{part}"
            cam["move"] = PART_MOVES[i % len(PART_MOVES)]  # close moves on a part (no top-down on a piston)
            label = part.replace("_", " ")
            drama = any(w in (text or "").lower() for w in DRAMA)
            if drama and not shot_kinds.get("macro") and i > 0:  # the most dramatic moment: a dark macro shot
                cam["move"] = "macro"
                shot_kinds["macro"] = 1
                actions.append({"do": "glow", "target": cam["target"], "at": _first_word(text)})
            elif i > 0 and shot_kinds.get("hero", 0) < 3 and part not in shot_kinds.get("hero_parts", []) and \
                    shot_kinds.get("since", 9) >= 2:  # a key part alone, big, cut in half
                cam["move"] = "hero"
                shot_kinds["hero"] = shot_kinds.get("hero", 0) + 1
                shot_kinds.setdefault("hero_parts", []).append(part)
                shot_kinds["since"] = 0
            shot_kinds["since"] = shot_kinds.get("since", 9) + 1
        labels = [{"target": target, "text": label, "kind": "part", "at": 0.2}]
        scenes.append({"camera": cam,
                       "actions": actions[:3], "labels": labels, "keywords": _keywords(text)})
    return {"title": script.get("title", ""), "areas": areas, "objects": objects, "scenes": scenes}


def _drives(model) -> set:
    """How a machine is worked: run (spin), lift (elevator) or open (doors, flappers)."""
    out = set()
    for p in model.parts:
        for m in (p.motion if isinstance(p.motion, list) else [p.motion] if p.motion else []):
            t = m.get("type")
            if t in ("lift", "stretch") or m.get("drive") == "lift":
                out.add("lift")
            elif t == "open" or m.get("drive") == "open":
                out.add("open")
            elif t in ("spin", "slide", "rod", "valve", "pulse", "chamber", "swing"):
                out.add("run")
    return out


def _named_part(asset: str, text: str) -> str:
    """A focus part of this machine that the line names (plural or not)."""
    seq = [P._stem(w) for w in re.split(r"[^A-Za-z0-9']+", text or "") if w]
    best, at = "", len(seq) + 1
    for name in assets.focus_points(asset):  # the part named FIRST in the line is what it's about
        if name in ("power", "inlet", "outlet"):
            continue
        ws = P.words_of(name.replace("_", " "))
        pos = next((k for k, w in enumerate(seq) if w in ws), None)
        if pos is not None and pos < at:
            best, at = name, pos
    return best


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

