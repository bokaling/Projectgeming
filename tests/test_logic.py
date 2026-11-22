"""PART A: things connect and work (ports, routed pipes, pushing, grounding, flows that switch things on)."""
import copy

import numpy as np
import pytest

from storyforge import captions
from storyforge.world import checker, examples, logic
from storyforge.world import plan as P
from storyforge.world.scene import World
from test_world import fake_timeline, make_script


@pytest.fixture(scope="module")
def cow():
    sc = make_script(examples.COW_POOP_SCRIPT)
    texts = [s["narration"] for s in sc["scenes"]]
    p, _ = P.validate(examples.COW_POOP_PLAN, texts)
    return p, texts, World(p, fake_timeline(texts), (270, 480))


def test_pipes_run_from_port_to_port_with_real_bends(cow):
    p, texts, w = cow
    route = np.asarray(w.groups["pipe1"][0].model.paths["flow"])
    a, _ = logic.port(w, "tank1.outlet")
    b, _ = logic.port(w, "dig1.inlet")
    assert np.allclose(route[0], a, atol=1e-3) and np.allclose(route[-1], b, atol=1e-3)  # connected at both ends
    for s, e in zip(route[:-1], route[1:]):  # every piece is straight along one axis: real right-angle bends
        assert np.count_nonzero(np.abs(e - s) > 1e-3) == 1
    stands = [i for i in w.insts if i.asset == "pipe_stand"]
    assert stands  # low pipes rest on stands
    cable = np.asarray(w.groups["wire3"][0].model.paths["flow"])
    assert np.allclose(cable[-1], logic.port(w, "homes.power")[0], atol=1e-3)  # the cable reaches the house


def test_the_scraper_is_a_complete_machine_that_pushes_the_manure_into_the_pit(cow):
    p, texts, w = cow
    assert any(i.asset == "rail" for i in w.insts) and any(i.asset == "electric_motor" for i in w.insts)
    sc = w.scenes[2]
    pile = w.groups["piles"][0]
    start = w.state(pile, sc["start"])["pos"].copy()
    mid = w.state(pile, sc["start"] + sc["dur"] * 0.5)
    end = w.state(pile, sc["end"] - 0.01)
    assert mid["pos"][0] > start[0] + 1.0  # it rides in front of the blade
    blade = w.state(w.groups["scraper1"][0], sc["start"] + sc["dur"] * 0.5)["pos"]
    assert 0 < mid["pos"][0] - blade[0] < 1.5  # touching the blade, not floating ahead of it
    assert end["vis"] < 0.1 and end["drop"] < -0.5  # it dropped into the pit
    assert not checker.logic_problems(w, 2)


def test_lights_start_when_the_power_arrives(cow):
    p, texts, w = cow
    spark = next(e for e in w.events_of["wire3"] if e.do == "sparks")
    light = next(e for e in w.events_of["homes"] if e.do == "light_on")
    path = w.groups["wire3"][0].model.paths["flow"]
    length = sum(np.linalg.norm(np.subtract(b, a)) for a, b in zip(path[:-1], path[1:]))
    assert light.start >= spark.start + length / 7.0 - 1e-6


def test_nothing_floats_and_loose_pipes_get_connected(cow):
    p, texts, _ = cow
    q = copy.deepcopy(p)
    q["objects"].append({**q["objects"][-1], "id": "box9", "asset": "crate", "area": "power", "pos": [3.0, 3.0],
                         "y": 4.0, "count": 1, "params": {}})
    q["objects"].append({**q["objects"][-1], "id": "cloud9", "asset": "cloud", "area": "town", "pos": [0, 0],
                         "y": 9.0, "count": 1, "params": {}})
    loose = next(o for o in q["objects"] if o["id"] == "pipe1")
    loose.pop("from")
    loose.pop("to")
    loose["params"] = {"length": 7.0}
    loose["pos"] = [4.6, 0.0]
    w = World(q, fake_timeline(texts), (270, 480))
    assert w.groups["box9"][0].pos[1] == 0.0 and w.groups["cloud9"][0].pos[1] == 9.0  # crates sit, clouds float
    assert any("box9 was floating" in n for n in w.notes)
    o = next(o for o in w.plan["objects"] if o["id"] == "pipe1")
    assert o.get("from") and o.get("to") and any("pipe1 was loose" in n for n in w.notes)
    assert "from" not in next(x for x in q["objects"] if x["id"] == "pipe1")  # the caller's plan is not changed


def test_clean_composition_no_ghosts_no_props_in_front(cow):
    p, texts, w = cow
    for i in range(len(texts)):
        s = w.scenes[i]
        fr = w.frame(s["start"] + s["dur"] * 0.6)
        assert not any(d.xray for d in fr.draws), i  # blocking walls are left out, never drawn as ghost lines
        assert not checker.logic_problems(w, i), (i, checker.logic_problems(w, i))
    ev = captions.keyword_events([{"text": "the scraper", "kind": "part", "start": 0, "end": 2}], "en", 2)
    assert "\\fad" not in ev[0][3]  # captions are always fully opaque


def test_animals_are_seen_from_the_side(cow):
    p, texts, w = cow
    for i, c in enumerate(w._cams):
        if w.groups[c["target"]][0].asset in ("cow", "person"):
            assert c["el"] <= 20, i


def test_validate_keeps_links_and_drops_broken_ones():
    plan = {"areas": [{"id": "a"}], "objects": [
        {"id": "T", "asset": "tank", "area": "a"}, {"id": "P", "asset": "pipe", "area": "a", "from": "T.outlet",
                                                     "to": "Ghost.inlet"},
        {"id": "Q", "asset": "pipe", "area": "a", "from": "T.outlet", "to": "T.inlet"}],
        "scenes": [{"camera": {"move": "orbit", "target": "T"}}]}
    out, fixes = P.validate(plan, ["x"])
    by = {o["id"]: o for o in out["objects"]}
    assert "from" not in by["p"] and any("not an object" in f for f in fixes)
    assert by["q"]["from"] == "t.outlet" and by["q"]["to"] == "t.inlet"
    assert P.validate(out, ["x"])[0] == out  # still idempotent
