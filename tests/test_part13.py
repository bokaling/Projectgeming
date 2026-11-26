"""Part 13: new topics work like library machines: mechanism kit, upgraded builder, 3-view self check with redesigns,
the shared library, laundry/hangar places and the no-AI composer."""
import json

import numpy as np
import pytest

from storyforge.world import assets, builder, kit


@pytest.fixture()
def clean_registry():
    reg, ali = dict(assets.REGISTRY), dict(assets.ALIASES)
    yield
    assets.REGISTRY.clear()
    assets.REGISTRY.update(reg)
    assets.ALIASES.clear()
    assets.ALIASES.update(ali)


def test_every_kit_piece_builds_moves_and_is_in_the_library():
    for name in kit.KIT:
        m = assets.build(f"kit_{name}")
        assert m.parts and m.bounds()[0][1] >= -0.01, name  # on the floor
        assert any(p.motion or p.kind for p in m.parts), name  # something works
    assert "[parts:" in next(x for x in assets.catalog().split("\n") if x.startswith("- kit_turbine:"))


def test_kit_parts_expand_with_names_axes_paths_and_ports():
    parts, paths, ports = kit.expand({"kit": "turbine", "name": "compressor", "pos": [1, 2, 0], "size": 0.5,
                                      "stages": 3, "axis": "z"})
    names = [p["name"] for p in parts]
    assert "compressor" in names and "compressor_shaft" in names and "compressor_case" in names
    assert "compressor_flow" in paths and abs(paths["compressor_flow"][0][2]) > 0.3  # turned along z
    spin_axes = {(p.get("motion") or {}).get("axis") for p in parts if p.get("motion")}
    assert spin_axes == {"z"}
    _, _, ports = kit.expand({"kit": "pump", "name": "drain_pump", "pos": [0, 0, 0], "size": 0.1})
    assert set(ports) >= {"inlet", "outlet", "drain_pump_inlet", "drain_pump_outlet"}


def test_builder_new_shapes_key_part_and_default_pivot(clean_registry):
    recipe = {"name": "test_gadget", "about": "x", "key_part": "rotor", "parts": [
        {"name": "case", "shape": "lathe", "profile": [[0.2, 0], [0.25, 0.3], [0.1, 0.5]], "caps": False,
         "color": "#ffffff", "shell": True},
        {"name": "rotor", "shape": "gear", "size": [0.1, 0.03], "teeth": 14, "pos": [0, 0.3, 0],
         "motion": {"type": "spin", "axis": "z"}},
        {"name": "coil", "shape": "spring", "size": [0.05, 0.2, 0.01], "turns": 5, "pos": [0.1, 0.2, 0],
         "kind": "heater"},
        {"name": "fan", "shape": "blades", "size": [0.12, 0.04, 0.01], "count": 5, "pos": [-0.1, 0.2, 0],
         "motion": {"type": "pump", "axis": "y", "amp": 0.01}},
        {"name": "nozzle", "shape": "taper", "size": [0.05, 0.1, 0.02], "pos": [0, 0.55, 0]},
        {"kit": "spring", "name": "damper", "pos": [0.2, 0.1, 0], "size": 0.1, "axis": "y"}]}
    m = builder.model_from_recipe(recipe)
    names = {p.name for p in m.parts}
    assert {"case", "rotor", "coil", "fan", "nozzle", "damper"} <= names
    assert m.anchors["key"][1] == pytest.approx(0.3, abs=0.02)  # the cutaway goes through the rotor
    rotor = next(p for p in m.parts if p.name == "rotor")
    assert rotor.pivot == pytest.approx((0, 0.3, 0))  # turns about itself, not about the model's origin
    assert next(p for p in m.parts if p.name == "coil").kind == "heater"
    assert next(p for p in m.parts if p.name == "fan").motion["type"] == "pump"


def test_machines_keep_their_part_names_when_merging(clean_registry):
    recipe = {"name": "two_nozzles", "about": "x", "tags": ["machine"], "parts": [
        {"name": "nozzle", "shape": "box", "size": [0.1, 0.1, 0.1], "pos": [0, 0.05, 0], "color": "#5b6672"},
        {"name": "fuel_nozzles", "shape": "box", "size": [0.1, 0.1, 0.1], "pos": [0.3, 0.05, 0], "color": "#5b6672"},
        {"name": "fan", "shape": "box", "size": [0.1, 0.1, 0.1], "pos": [0.6, 0.05, 0],
         "motion": {"type": "spin", "axis": "y"}}]}
    builder.register(recipe)
    assert {"nozzle", "fuel_nozzles"} <= {p.name for p in assets.build("two_nozzles").parts}


def test_self_check_redesigns_until_it_looks_right(sf_root, monkeypatch, clean_registry):
    from storyforge import llm

    bad = {"name": "x", "about": "a washing machine", "key_part": "drum",
           "parts": [{"name": "cabinet", "shape": "box", "size": [0.6, 0.85, 0.6], "pos": [0, 0.42, 0], "shell": True}]}
    good = json.loads(json.dumps(bad))
    good["parts"].append({"kit": "drum", "name": "drum", "pos": [0, 0.5, 0], "size": 0.22, "axis": "z"})
    designs, asked = [bad, good], []
    monkeypatch.setattr(llm, "generate_json", lambda system, user, **k: (asked.append(json.loads(user)) or
                                                                         ("FakeAI", json.loads(json.dumps(designs.pop(0))))))
    verdicts = [{"ok": False, "problems": ["no drum inside"], "fix": "add a drum"}, {"ok": True}]
    monkeypatch.setattr(builder, "preview_stills", lambda m, size=320, running=0.7: [np.zeros((8, 8, 3), np.uint8)] * 3)
    monkeypatch.setattr(llm, "vision_json", lambda *a, **k: verdicts.pop(0))
    name = builder.design("washer_test", "a washing machine")
    assert name == "washer_test" and not designs and not verdicts
    assert asked[1]["fix_this"]["problems"] == ["no drum inside"]  # the 2nd design saw what was wrong
    saved = json.loads((builder.user_dir() / "washer_test.json").read_text(encoding="utf-8"))
    assert saved["checked"] == "checked" and any(p.get("kit") == "drum" for p in saved["parts"])
    assert (builder.user_dir() / "washer_test_check.jpg").exists()


def test_a_design_that_never_looks_right_is_not_saved(sf_root, monkeypatch, clean_registry):
    from storyforge import llm

    recipe = {"name": "x", "about": "y", "parts": [{"name": "body", "shape": "box", "size": [1, 1, 1]}]}
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: ("FakeAI", json.loads(json.dumps(recipe))))
    monkeypatch.setattr(builder, "preview_stills", lambda m, size=320, running=0.7: [np.zeros((8, 8, 3), np.uint8)])
    monkeypatch.setattr(llm, "vision_json", lambda *a, **k: {"ok": False, "problems": ["a plain box"]})
    assert builder.design("blob_test", "z") == "blob_test"  # still used for this video
    assert not (builder.user_dir() / "blob_test.json").exists()  # but not shared for next time


def test_no_ai_composer_and_planner_build_new_machines(sf_root, clean_registry):
    from storyforge.world import planner

    for topic, part in (("How a washing machine works", "drum"), ("How a jet engine works", "combustor"),
                        ("How a microwave heats food", "magnetron")):
        r = kit.compose(topic)
        m = builder.model_from_recipe(r)
        assert any(p.name == part for p in m.parts) and "key" in m.anchors, topic
    assert kit.compose("how a cheese grater works") is None
    builder.compose("washing machine")
    script = {"title": "How a washing machine works", "scenes": [
        {"narration": "The drum turns one way, then the other.", "visual": "the drum"},
        {"narration": "A pump drains the dirty water.", "visual": "the pump"}]}
    raw = planner.offline_plan(script)
    assert raw["objects"][0]["asset"] == "washing_machine"
    assert raw["scenes"][0]["camera"]["target"].endswith(".drum")


def test_new_places_for_new_machines():
    from storyforge.world import settings

    assert settings.guess(["how a washing machine works"], ["washing_machine"]) == "laundry"
    assert settings.guess(["how a jet engine works"], ["jet_engine"]) == "hangar"
    assert "laundry" in settings.SETTINGS and "hangar" in settings.SETTINGS


def test_preview_stills_draw_three_views(needs_gl, clean_registry):
    m = builder.model_from_recipe(kit.compose("microwave"))
    ims = builder.preview_stills(m, size=96)
    assert len(ims) == 3 and all(im.shape == (96, 96, 3) for im in ims)
    assert ims[2].std() > 5  # the cut-open view shows something


def test_a_pasted_plan_uses_objects_from_the_shared_library(offline, clean_registry):
    """Regression: a plan naming a design saved on Drive must not turn into a crate."""
    from storyforge import pipeline, project, script
    from storyforge.messages import Reporter

    folder = builder.user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    recipe = {"name": "spin_gizmo", "about": "x", "tags": ["machine"], "parts": [
        {"name": "body", "shape": "box", "size": [0.4, 0.4, 0.4], "pos": [0, 0.2, 0], "shell": True},
        {"kit": "fan", "name": "fan", "pos": [0, 0.2, 0], "size": 0.15, "axis": "z"}]}
    (folder / "spin_gizmo.json").write_text(json.dumps(recipe), encoding="utf-8")
    series = project.Series.create("Lib")
    ep = series.episode(1)
    opts = project.EpisodeOptions()
    script.script_from_text(series, ep, opts, "NARRATOR: The fan inside the gizmo spins very fast all day long.",
                            Reporter(echo=False))
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), opts)
    plan = pipe.save_plan({"areas": [{"id": "a"}], "objects": [{"id": "g1", "asset": "spin_gizmo", "area": "a"}],
                           "scenes": [{"camera": {"move": "close_up", "target": "g1.fan"}}]})
    assert plan["objects"][0]["asset"] == "spin_gizmo" and plan["scenes"][0]["camera"]["part"] == "fan"
