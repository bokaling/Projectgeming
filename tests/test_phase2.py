"""Phase 2: the bigger asset library, long videos (planned in parts), fixing one shot, the quality check."""
import copy
import json

import numpy as np
import pytest

from storyforge import llm, pipeline, project
from storyforge.messages import FriendlyError, Reporter
from storyforge.world import assets, checker, examples, fixer, planner
from storyforge.world import plan as P
from storyforge.world.scene import World, area_layout, freeze_layout
from test_world import fake_timeline, make_script


@pytest.fixture(scope="module")
def cow():
    sc = make_script(examples.COW_POOP_SCRIPT)
    texts = [s["narration"] for s in sc["scenes"]]
    p, _ = P.validate(examples.COW_POOP_PLAN, texts)
    return freeze_layout(p), texts


# ---------------------------------------------------------------- asset library
def test_the_library_covers_every_kind_of_topic():
    names = set(assets.names())
    assert len(names) >= 120
    for need in ("pig", "factory", "wind_turbine", "car", "train", "rocket", "pump", "gear", "engine", "turbine",
                 "conveyor", "battery", "fire", "cell", "virus", "molecule", "atom", "dna", "planet", "coin", "cash",
                 "bar_chart", "beaker", "ground_layers", "terrain", "water", "cloud", "explosion", "skyscraper"):
        assert need in names, need
    tags = {t for i in assets.REGISTRY.values() for t in i.tags}
    assert {"animal", "building", "vehicle", "machine", "micro", "space", "money", "symbol", "helper"} <= tags
    assert assets.resolve("windmill") == "wind_turbine" and assets.resolve("H2O") == "molecule"
    assert assets.resolve("power plant") == "power_station" and assets.resolve("turbine") == "turbine"
    w = assets.build("molecule", formula="CO2")
    from storyforge.world.assets_more import ATOM_COLORS

    assert {ATOM_COLORS["C"], ATOM_COLORS["O"]} <= {p.color for p in w.parts}  # carbon and oxygen (merged per colour)


def test_new_moving_parts_animate(cow):
    p, texts = cow
    p = copy.deepcopy(p)
    p["objects"] += [{"id": "eng", "asset": "engine", "area": "power", "pos": [1.5, 8]},
                     {"id": "jack", "asset": "pumpjack", "area": "power", "pos": [-2.5, 9]},
                     {"id": "camp", "asset": "fire", "area": "power", "pos": [0, 10]}]
    p["scenes"][10]["camera"] = {"move": "static", "target": "camp", "angle": 0, "height": 40, "zoom": 0.3}
    p["scenes"][10]["actions"] += [{"do": "spin", "target": "eng", "at": 0.0}, {"do": "spin", "target": "jack", "at": 0.0}]
    p, _ = P.validate(p, texts)
    w = World(p, fake_timeline(texts), (180, 320))
    T = w.scenes[10]["start"] + 1.0

    def part_matrices(oid, kind, t):
        fr = w.frame(t)
        inst = w.groups[oid][0]
        keys = {inst.keys[k] for k, pt in enumerate(inst.model.parts) if pt.kind == kind}
        return [d.model.copy() for d in fr.draws if d.key in keys]

    for oid, kind in (("eng", "piston"), ("jack", "rocker"), ("camp", "flame")):
        a, b = part_matrices(oid, kind, T), part_matrices(oid, kind, T + 0.13)
        assert a and not all(np.allclose(x, y) for x, y in zip(a, b)), (oid, kind)


def test_liquid_shows_through_glass(needs_gl):
    from storyforge.world import gl

    r = gl.Renderer((160, 160), msaa=1, shadow_size=256)
    try:
        m = assets.build("beaker")
        draws = []
        for i, part in enumerate(m.parts):
            r.upload(f"b{i}", part.geo)
            draws.append(gl.Draw(f"b{i}", np.eye(4, dtype=np.float32), gl.hex_rgb(part.color), opacity=part.opacity))
        c = np.array([0, 0.9, 0.0])
        img = r.render(gl.Frame(eye=tuple(c + [3, 2, 4]), target=tuple(c), draws=draws, focus=tuple(c), focus_radius=3,
                                grid_center=(0, 0)))
    finally:
        r.release()
    px = img[80, 80].astype(int)
    assert px[1] > 120 and px[1] > px[0] + 60  # the teal liquid inside the glass, not hidden by it


# ---------------------------------------------------------------- long videos: planned in parts
def _long_script(n=40):
    lines = ["[TITLE] How a city gets water"]
    things = ["dam", "pump", "pipe", "water tower", "factory", "house"]
    for i in range(n):
        lines += [f"[SCENE] shot {i + 1}", f"NARRATOR: Step {i + 1}: the {things[i % len(things)]} moves "
                                           f"{(i + 1) * 10} liters every minute."]
    return make_script("\n".join(lines))


def test_long_plan_is_made_in_parts_that_share_one_world(sf_root, monkeypatch):
    calls = []

    def fake(messages, json_mode, temperature, max_tokens):
        pay = json.loads(messages[1]["content"])
        calls.append(pay)
        first = pay["scenes"][0]["n"]
        n = len(pay["scenes"])
        if "world_so_far" not in pay:
            reply = {"areas": [{"id": "lake"}], "objects": [{"id": "dam1", "asset": "dam", "area": "lake"}],
                     "scenes": [{"camera": {"move": "orbit", "target": "dam1"}} for _ in range(n)]}
        elif first < 20:  # part 2 reuses dam1 and adds a pump (and repeats dam1 by mistake)
            reply = {"areas": [{"id": "station"}], "objects": [{"id": "dam1", "asset": "dam", "area": "lake"},
                                                               {"id": "p1", "asset": "pump", "area": "station"}],
                     "scenes": [{"camera": {"move": "push_in", "target": "p1"}} for _ in range(n - 2)]}  # 2 missing
        else:  # part 3 uses the id 'p1' for something else: it is renamed, not mixed up
            reply = {"areas": [{"id": "town"}], "objects": [{"id": "p1", "asset": "house", "area": "town"}],
                     "scenes": [{"camera": {"move": "fly_over", "target": "p1"}} for _ in range(n)]}
        return json.dumps(reply)

    monkeypatch.setattr(llm, "providers", lambda allow_local=True, strong=False: [("FakeAI", fake)])
    rep = Reporter(echo=False)
    plan, provider, fixes = planner.make_plan(_long_script(40), "long", rep)
    assert len(calls) == 3 and provider.startswith("FakeAI") and "3 parts" in provider
    assert len(plan["scenes"]) == 40 and "world_so_far" in calls[1] and "dam1: dam in lake" in calls[1]["world_so_far"][
        "objects"]
    ids = {o["id"]: o["asset"] for o in plan["objects"]}
    assert ids["dam1"] == "dam" and ids["p1"] == "pump" and ids["p1_b"] == "house" and len(ids) == 3
    assert plan["scenes"][15]["camera"]["target"] == "p1"
    assert plan["scenes"][14 + 12]["camera"]["target"] == "p1"  # the 2 missing shots keep the last subject
    assert all(s["camera"]["target"] == "p1_b" for s in plan["scenes"][28:])
    assert "Planning shots 15-28 of 40" in rep.text()


def test_a_failing_part_uses_the_built_in_planner(sf_root, monkeypatch):
    def fake(messages, json_mode, temperature, max_tokens):
        pay = json.loads(messages[1]["content"])
        if "world_so_far" in pay:
            raise RuntimeError("busy")
        n = len(pay["scenes"])
        return json.dumps({"areas": [{"id": "area1"}], "objects": [{"id": "dam1", "asset": "dam", "area": "area1"}],
                           "scenes": [{"camera": {"move": "orbit", "target": "dam1"}} for _ in range(n)]})

    monkeypatch.setattr(llm, "providers", lambda allow_local=True, strong=False: [("FakeAI", fake)])
    plan, provider, _ = planner.make_plan(_long_script(30), "long", Reporter(echo=False))
    assert "FakeAI" in provider and "Built-in planner" in provider and len(plan["scenes"]) == 30
    areas = [a["id"] for a in plan["areas"]]
    assert len(areas) == len(set(areas)) and "area1" in areas and any(a.startswith("p15_") for a in areas)
    w = World(plan, fake_timeline([s["text"] for s in plan["scenes"]]), (320, 180))
    xs = sorted(x for x, z in w.area_xz.values() if z == 0)
    assert all(b - a > 5 for a, b in zip(xs, xs[1:]))  # areas side by side, never on top of each other


# ---------------------------------------------------------------- fixing one shot
def test_rules_understand_common_requests(cow):
    p, texts = cow
    cases = {
        (4, "make the tank bigger"): lambda q: next(o for o in q["objects"] if o["id"] == "tank1")["scale"] == 1.5,
        (6, "show the gas flowing"): lambda q: any(a["do"] == "flow" and a.get("color") == "#9fe870"
                                                   for a in q["scenes"][6]["actions"]),
        (6, "cut it open"): lambda q: any(a["do"] == "cutaway" for a in q["scenes"][6]["actions"]),
        (11, "from above, closer"): lambda q: q["scenes"][11]["camera"]["move"] == "top_down"
        and q["scenes"][11]["camera"]["zoom"] > 1,
        (2, "make the scraper red"): lambda q: next(o for o in q["objects"] if o["id"] == "scraper1")["color"] == "#d9534f",
        (10, 'add a label "500 kW"'): lambda q: any(lb["text"] == "500 kW" for lb in q["scenes"][10]["labels"]),
        (1, "add 3 pigs next to the cows"): lambda q: any(o["asset"] == "pig" and o["count"] == 3 for o in q["objects"]),
        (9, "remove the labels"): lambda q: q["scenes"][9]["labels"] == [],
    }
    for (i, text), ok in cases.items():
        new, changes = fixer.rule_fix(p, i, text, texts[i])
        assert changes and ok(new), (text, changes)
        P.validate(new, texts)  # always a valid plan
    assert fixer.rule_fix(p, 3, "hello there", texts[3])[1] == []


def test_ai_fix_is_used_when_available(cow, sf_root, monkeypatch):
    p, texts = cow

    def fake(messages, json_mode, temperature, max_tokens):
        pay = json.loads(messages[1]["content"])
        scene = dict(pay["shot"])
        scene["camera"] = {**scene["camera"], "move": "low_angle"}
        return json.dumps({"scene": scene, "objects": [{"id": "gen1", "scale": 1.3}], "changes": ["low angle, bigger"]})

    monkeypatch.setattr(llm, "providers", lambda allow_local=True, strong=False: [("FakeAI", fake)])
    new, changes, who = fixer.fix(p, 10, "make it look powerful", texts[10])
    assert who == "FakeAI" and new["scenes"][10]["camera"]["move"] == "low_angle"
    assert next(o for o in new["objects"] if o["id"] == "gen1")["scale"] == 1.3 and changes == ["low angle, bigger"]
    monkeypatch.setattr(llm, "providers", lambda allow_local=True, strong=False: [])
    with pytest.raises(ValueError):
        fixer.fix(p, 10, "make it look powerful", texts[10])  # no AI and no rule matches


def test_a_fix_rerenders_only_the_shots_that_show_it(cow, sf_root):
    p, texts = cow
    series = project.Series.create("Fp Show")
    pipe = pipeline.Pipeline(series, series.episode(1), Reporter(echo=False), project.EpisodeOptions())
    tl = fake_timeline(texts)
    tl["words"] = []
    fps = lambda q: [pipe.scene_fp(q, tl, i, (360, 640)) for i in range(len(q["scenes"]))]  # noqa: E731
    before = fps(p)
    bigger, _ = fixer.rule_fix(p, 4, "make the tank bigger", texts[4])
    bigger = freeze_layout(P.validate(bigger, texts)[0])
    changed = [i for i, (a, b) in enumerate(zip(before, fps(bigger))) if a != b]
    assert 4 in changed and 0 not in changed and 1 not in changed and 11 not in changed  # the barn and town shots stay
    assert area_layout(bigger) == area_layout(p)  # frozen: nothing else moved
    labels, _ = fixer.rule_fix(p, 9, "remove the labels", texts[9])
    assert [i for i, (a, b) in enumerate(zip(before, fps(P.validate(labels, texts)[0]))) if a != b] == [9]


def test_fix_scene_in_the_app_rerenders_one_shot(offline, needs_gl):
    from test_pipeline import TINY, make

    series, opts = make("Fix Show")
    pipeline.generate(series, opts, TINY, Reporter(echo=False))
    ep = series.episode(1)
    rep = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep, ep.load_options()).fix_scene(2, "make the house bigger")
    text = rep.text(300)
    assert "Shot 3 changed" in text and "Scene 3/3" in text and "Scene 1/3" not in text and "Scene 2/3" not in text
    with pytest.raises(FriendlyError):
        pipeline.Pipeline(series, ep, Reporter(echo=False), ep.load_options()).fix_scene(0, "sing a song")


# ---------------------------------------------------------------- quality check
def _qc_world(texts):
    tl = fake_timeline(texts)

    def make_world(q):
        return World(q, tl, (180, 320))

    def still(w, i):  # a fake 'picture': busy unless the shot is marked empty
        return np.full((32, 18, 3), 30, np.uint8) if w.plan["scenes"][i].get("_empty") else \
            np.random.default_rng(i).integers(0, 255, (32, 18, 3), dtype=np.uint8)
    return make_world, still


def test_quality_check_finds_and_fixes_broken_shots(cow, sf_root):
    """Framing is automatic now; a camera can still break (e.g. a bug, or a forced fill). The check catches it."""
    p, texts = cow
    make_world, still = _qc_world(texts)

    def broken_world(q):  # a tiny zoom stands for "something made this shot's camera wrong"
        w = make_world(q)
        for i, sc in enumerate(q["scenes"]):
            z = sc["camera"].get("zoom", 1.0)
            if z < 0.5:
                w._cams[i]["fill"] = 0.12  # the subject is a dot
            elif z > 4:
                w._cams[i]["fill"] = 9.0  # the camera ends up inside it
        return w

    bad = copy.deepcopy(p)
    bad["scenes"][4]["camera"].update({"move": "static", "zoom": 0.2})
    bad["scenes"][6]["camera"].update({"move": "static", "zoom": 5, "height": 2})
    w = broken_world(bad)
    assert "target_too_small" in checker.local_problems(w, 4)
    probs6 = checker.local_problems(w, 6)
    assert any(x.startswith("camera_inside") or x == "target_too_big" for x in probs6), probs6
    assert all(not checker.local_problems(make_world(p), i) for i in range(len(texts)))  # the good plan passes
    new, report, stills = checker.check(bad, broken_world, still, texts, use_ai=False)
    assert any(r.startswith("Shot 5") for r in report) and any(r.startswith("Shot 7") for r in report)
    w2 = broken_world(new)
    assert not checker.local_problems(w2, 4) and not checker.local_problems(w2, 6) and len(stills) == len(texts)
    assert checker.empty_picture(np.full((64, 36, 3), 20, np.uint8))


def test_every_demo_shot_is_framed_by_the_rules(cow):
    """Rule 1: the main object fills ≥ 30 % of the frame, fully visible inside the safe area; nothing mostly empty."""
    p, texts = cow
    w = World(p, fake_timeline(texts), (270, 480))
    for i in range(len(texts)):
        assert checker.local_problems(w, i) == [], (i, checker.local_problems(w, i))
    assert p["scenes"][0]["camera"]["move"] not in P.WIDE_MOVES  # the hook is close


def test_gemini_vision_fixes_what_it_sees(cow, sf_root, monkeypatch):
    p, texts = cow
    seen = {}

    def fake_vision(system, text, images, rep=None, max_tokens=3000):
        seen.setdefault("calls", []).append(len(images))
        if "Shot 1:" in text:
            return {"shots": [{"n": 1, "ok": True}, {"n": 3, "ok": False, "problem": "labels overlap",
                                                     "fix": "remove the labels"}]}
        return {"shots": []}

    monkeypatch.setattr(llm, "vision_json", fake_vision)
    p2 = copy.deepcopy(p)
    p2["scenes"][2]["labels"] = [{"target": "scraper1", "text": "SCRAPER", "kind": "part"}]
    make_world, still = _qc_world(texts)
    new, report, _ = checker.check(p2, make_world, still, texts)
    assert seen["calls"] == [8, 5]  # 13 stills, in batches of 8
    assert new["scenes"][2]["labels"] == [] and any("Gemini: labels overlap" in r for r in report)


def test_vision_needs_the_free_key(sf_root, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.vision_json("s", "t", [b"x"]) is None  # no key: no call, the local checks are enough


def test_checking_a_plan_twice_changes_nothing(cow):
    """Saved plans are checked again after every edit: nothing may drift (0 → 0.0, count-ups lost…)."""
    p, texts = cow
    again, fixes = P.validate(p, texts)
    assert again == p and fixes == []
    assert any(lb.get("count") == [0.0, 150.0] for lb in again["scenes"][11]["labels"])
