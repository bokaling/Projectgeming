"""PART B: world presets, the object builder (recipes), video formats and the 3 new built-in demos."""
import copy
import json

import numpy as np
import pytest

from storyforge import formats
from storyforge.world import assets, builder, examples, planner, presets
from storyforge.world import plan as P
from storyforge.world.scene import World
from test_world import fake_timeline, make_script

builder.load_all()


@pytest.fixture(autouse=True)
def _clean_library():
    """Objects registered by a test are removed again (other tests count the library)."""
    reg, ali = dict(assets.REGISTRY), dict(assets.ALIASES)
    yield
    assets.REGISTRY.clear()
    assets.REGISTRY.update(reg)
    assets.ALIASES.clear()
    assets.ALIASES.update(ali)


def _texts(script):
    return [s["narration"] for s in make_script(script)["scenes"]]


# ------------------------------------------------------------------ presets
def test_presets_resolve_guess_and_style():
    assert presets.resolve("Underwater") == "ocean" and presets.resolve("mars") == "planet_surface"
    assert presets.resolve("nonsense") == "" and presets.resolve(None) == ""
    assert presets.guess([examples.COW_POOP_SCRIPT]) == "farm"  # "stomach" + "bacteria" don't win over 10 farm words
    assert presets.guess([examples.SUB_SCRIPT]) == "ocean"
    assert presets.guess([examples.SUGAR_SCRIPT]) == "body"
    assert presets.guess([examples.PYRAMID_SCRIPT]) == "ancient"
    assert presets.guess(["a quiet talk about nothing"]) == "studio"
    ocean, studio = presets.style_of("ocean"), presets.style_of("studio")
    assert ocean["grid"] == "#000000" and ocean["floor"] == presets.PRESETS["ocean"]["base"]  # no grid, open sea floor
    assert studio["grid"] == "#000000" and presets.PRESETS["studio"]["grid"] is None  # a clean light studio: no grid
    for name, p in presets.PRESETS.items():  # every preset has every colour the renderer needs
        assert set(presets.style_of(name)) >= {"background", "horizon", "floor", "grid", "sky", "ground_light", "sun"}
        assert all(a in assets.REGISTRY for a in p["props"]), name


def test_plan_keeps_or_guesses_the_preset():
    texts = _texts(examples.SUB_SCRIPT)
    assert P.validate(examples.SUB_PLAN, texts)[0]["preset"] == "ocean"
    raw = copy.deepcopy(examples.SUB_PLAN)
    raw.pop("preset")
    assert P.validate(raw, texts)[0]["preset"] == "ocean"  # guessed from the words
    raw["preset"] = "kitchen"
    assert P.validate(raw, texts)[0]["preset"] == "house_interior"  # alias


# ------------------------------------------------------------------ object builder
RECIPE = {"name": "Test Lantern", "about": "a little lantern", "tags": ["light"], "aliases": ["test lamp"],
          "parts": [{"shape": "box", "size": [0.6, 0.1, 0.6], "pos": [0, 0.05, 0], "color": "#444444"},
                    {"shape": "sphere", "size": [0.25], "pos": [0, 0.4, 0], "color": "#ffd76b", "kind": "light"},
                    {"shape": "cylinder", "size": [0.3, 0.6], "pos": [0, 0.4, 0], "color": "#bfe9ff", "opacity": 0.3},
                    {"shape": "nonsense", "size": [0.1, 0.1, 0.1], "pos": [0, 0.8, 0]}],  # unknown shape → a box
          "ports": {"power": [0, 0.8, 0]}, "label": [0, 1.2, 0]}


def test_recipe_builds_and_registers():
    m = builder.model_from_recipe(RECIPE)
    assert len(m.parts) == 4 and m.anchors["power"] == (0.0, 0.8, 0.0)
    assert any(p.kind == "light" for p in m.parts)
    name = builder.register(RECIPE)
    assert name == "test_lantern" and "test_lantern" in assets.REGISTRY
    assert assets.resolve("test lamp") == "test_lantern" and builder.known("test_lanterns") == "test_lantern"
    assert builder.known("zeppelin") is None


@pytest.mark.parametrize("bad", [{}, {"parts": []}, {"parts": [{"shape": "box", "pos": [-80, 0, 0]}, {"shape": "box", "pos": [80, 0, 0]}]},
                                 {"parts": [{"shape": "tube", "points": [[0, 0, 0]]}]}])
def test_bad_recipes_are_refused(bad):
    with pytest.raises(ValueError):
        builder.model_from_recipe(bad)


def test_built_in_recipes_all_load():
    names = [json.loads(f.read_text())["name"] for f in builder.RECIPES_DIR.glob("*.json")]
    assert len(names) >= 15
    for n in names:
        assert n in assets.REGISTRY and assets.build(n).parts, n
    sub = assets.build("submarine")
    assert {"vent", "inlet", "outlet"} <= set(sub.anchors) and any(p.kind == "liquid" for p in sub.parts)
    assert assets.build("blood_vessel").paths.get("flow")  # flows run along it without a 'to'


def test_ensure_objects_designs_unknown_things(monkeypatch, tmp_path):
    from storyforge import llm

    monkeypatch.setattr(builder, "user_dir", lambda: tmp_path)
    recipe = copy.deepcopy({**RECIPE, "name": "x", "aliases": []})
    recipe["parts"][1]["pos"] = [0, 0.35, 0]  # the bulb sits on the base, the cap on the glass: it holds together
    recipe["parts"][3]["pos"] = [0, 0.75, 0]
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: ("fake", copy.deepcopy(recipe)))
    plan = {"objects": [{"id": "z1", "asset": "zeppelin"}, {"id": "c1", "asset": "cow"}]}
    assert builder.ensure_objects(plan) == ["zeppelin"]
    assert plan["objects"][0]["asset"] == "zeppelin" and "zeppelin" in assets.REGISTRY
    assert (tmp_path / "zeppelin.json").exists()  # saved for next time (Drive library)
    assert plan["objects"][1]["asset"] == "cow"


def test_a_design_with_floating_parts_is_used_but_not_saved(monkeypatch, tmp_path):
    from storyforge import llm

    monkeypatch.setattr(builder, "user_dir", lambda: tmp_path)
    recipe = {**RECIPE, "name": "x", "aliases": []}  # bulb and cap hang in the air, every redesign too
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: ("fake", copy.deepcopy(recipe)))
    plan = {"objects": [{"id": "z1", "asset": "airship_lantern"}]}
    assert builder.ensure_objects(plan) == ["airship_lantern"]
    assert "airship_lantern" in assets.REGISTRY  # used for this video
    assert not (tmp_path / "airship_lantern.json").exists()  # but not saved for next time


def test_without_ai_the_closest_object_is_used(monkeypatch, tmp_path):
    from storyforge import llm

    def fail(*a, **k):
        raise RuntimeError("no AI")

    monkeypatch.setattr(builder, "user_dir", lambda: tmp_path)
    monkeypatch.setattr(llm, "generate_json", fail)
    plan = {"objects": [{"id": "h1", "asset": "hovercraft_x"}]}
    assert builder.ensure_objects(plan) == []
    assert plan["objects"][0]["asset"] == "hovercraft_x"  # unchanged: plan.validate maps it to the closest asset
    assert assets.resolve("hovercraft_x") in assets.REGISTRY


# ------------------------------------------------------------------ formats
def test_formats_detect_and_settings():
    assert formats.detect("How a Submarine Dives") == "how_it_works"
    assert formats.detect("What Happens Inside Your Body When You Eat Sugar") == "what_if"
    assert formats.detect("What happens if the Moon disappeared?") == "what_if"
    assert formats.detect("How the Pyramids Were Built") == "how_made"
    assert formats.detect("The history of the light bulb") == "history"
    assert formats.detect("Top 5 deadliest machines") == "top_list"
    assert formats.resolve("story", "How a Submarine Dives") == "story"
    assert formats.resolve("auto", "Top 10 bridges") == "top_list"
    story, how = formats.get("story"), formats.get("how_it_works")
    assert story["captions"] == "words" and story["ending"] == "card"
    assert how["captions"] == "keywords" and how["ending"] == "overview"
    assert formats.get("nope") == how


# ------------------------------------------------------------------ the 3 new demos
@pytest.mark.parametrize("k", [1, 2, 3])
def test_new_demos_validate_cleanly(k):
    script, plan = examples.EXAMPLES[k]
    texts = _texts(script)
    p, fixes = P.validate(plan, texts)
    assert fixes == [] and len(p["scenes"]) == len(texts)
    assert P.validate(p, texts)[0] == p  # idempotent
    assert planner.example_for(make_script(script)) is plan


@pytest.fixture(scope="module")
def sub_world():
    texts = _texts(examples.SUB_SCRIPT)
    p, _ = P.validate(examples.SUB_PLAN, texts)
    return World(p, fake_timeline(texts), (270, 480))


def test_ocean_world_is_open_sea(sub_world):
    w = sub_world
    assets_used = {i.asset for i in w.insts}
    assert "person" not in assets_used and "pad" not in assets_used and "ground_plate" not in assets_used
    assert "lamp_post" not in assets_used and "railing" not in assets_used
    assert w.style["grid"] == "#000000"
    sub = w.groups["sub1"][0]
    assert sub.pos[1] > 5  # the sub floats, it isn't pushed down to the sea floor
    fish = [i for i in w.insts if i.asset == "fish" and i.oid.startswith("_env")]
    assert all(i.pos[1] > 1.0 for i in fish)  # prop fish swim, they don't lie on the sand


def test_air_particles_stay_out_of_the_lens(sub_world):
    w = sub_world
    for i in (0, 4, 7):
        T = w.scenes[i]["start"] + w.scenes[i]["dur"] * 0.5
        eye = np.asarray(w.camera(i, T - w.scenes[i]["start"])[0])
        air = np.asarray(w._air(i, T))
        assert len(air) > 20
        assert np.min(np.linalg.norm(air[:, :3] - eye, axis=1)) >= 2.0


def test_dive_moves_down_and_tanks_fill_in_place(sub_world):
    w = sub_world
    sub = w.groups["sub1"][0]
    s5, s6 = w.scenes[4], w.scenes[5]
    st = w.state(sub, s5["start"] + 0.05)
    assert st["fill"] < 0.1  # tanks still full of air
    st = w.state(sub, s6["start"] + s6["dur"] - 0.01)
    assert st["fill"] > 0.9 and st["pos"][1] < 3.0  # flooded, and dived


def test_group_moves_keep_their_formation():
    texts = _texts(examples.PYRAMID_SCRIPT)
    p, _ = P.validate(examples.PYRAMID_PLAN, texts)
    w = World(p, fake_timeline(texts), (270, 480))
    s = w.scenes[3]
    xs = sorted(float(w.state(m, s["start"] + s["dur"] - 0.01)["pos"][0]) for m in w.groups["team"])
    assert len(xs) == 4 and min(np.diff(xs)) > 0.5  # four men in a row, not one on top of another


def test_person_moods():
    geos = {m: assets.build("person", mood=m) for m in ("neutral", "happy", "sad", "angry", "surprised", "scared")}
    verts = {m: np.concatenate([p.geo.pos.ravel() for p in g.parts]) for m, g in geos.items()}
    assert not np.array_equal(verts["happy"], verts["sad"])
    assert not np.array_equal(verts["neutral"], verts["surprised"])


def test_story_captions_are_single_pop_words_with_red_accents(tmp_path):
    from storyforge import captions

    words = [{"w": w, "s": k * 0.4, "e": k * 0.4 + 0.35} for k, w in
             enumerate("Mira found a DEAD tree in the village".split())]
    ev = captions.caption_events(words, (1080, 1920), "9x16", "en", style="pop", accent="red", total=4.0, single=True)
    head = captions.header((1080, 1920), "9x16", "en", style="pop", accent="red")
    text = captions.to_text(head, captions.slice_events(ev, 0.0, 4.0))
    assert "Dialogue:" in text and "[Script Info]" in text
    assert len(ev) == len(words) and all(e[2] == "Main" for e in ev)  # one word at a time
    assert any(captions.ass_color(captions.ACCENTS["red"]) in e[3] for e in ev)  # a key word in red
