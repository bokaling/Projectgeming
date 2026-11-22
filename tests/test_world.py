"""The 3D world: shapes, asset library, scene plan checker, timing, camera, labels, renderer (CPU only)."""
import math

import numpy as np
import pytest

from storyforge import captions, media, paste, project, script
from storyforge.audio import music, tts
from storyforge.world import assets, examples, mesh, plan, planner
from storyforge.world.scene import World


def make_script(text: str) -> dict:
    parsed = paste.parse_lines(text)
    raw = {"title": parsed["title"], "language": parsed["language"], "scenes": paste.to_scenes(parsed, "short"),
           "style": parsed.get("style", "")}
    return script.normalize_script(raw, project.EpisodeOptions())


def fake_timeline(texts: list[str], per_word: float = 0.36) -> dict:
    """Like Pipeline.timeline, but without a voice: every word takes the same time."""
    scenes, words, t = [], [], 0.0
    for text in texts:
        ws = text.split()
        dur = round(0.4 + len(ws) * per_word, 3)
        for k, w in enumerate(ws):
            words.append({"w": w, "s": t + 0.1 + k * per_word, "e": t + 0.1 + (k + 1) * per_word})
        scenes.append({"start": round(t, 3), "dur": dur, "voice": dur - 0.3})
        t += dur
    return {"scenes": scenes, "words": words, "total": t + 0.8, "end": {"start": t, "dur": 0.8}}


@pytest.fixture(scope="module")
def cow_world():
    sc = make_script(examples.COW_POOP_SCRIPT)
    texts = [s["narration"] for s in sc["scenes"]]
    p, _ = plan.validate(examples.COW_POOP_PLAN, texts)
    return World(p, fake_timeline(texts), (360, 640))


# ---------------------------------------------------------------- shapes
@pytest.mark.parametrize("g", [mesh.box(2, 1, 3), mesh.sphere(1.0, 1), mesh.cylinder(0.5, 2.0, 10),
                               mesh.cone(0.6, 1.2)], ids=["box", "sphere", "cyl", "cone"])
def test_shapes_face_outward(g):
    """Flat normals point away from the middle (otherwise the light and the cutaway look wrong)."""
    tri = g.pos.reshape(-1, 3, 3)
    centre = tri.reshape(-1, 3).mean(0)
    n = g.normals().reshape(-1, 3, 3)[:, 0]
    mid = tri.mean(1)
    out = np.einsum("ij,ij->i", n, mid - centre)
    if g.tris and abs(g.bounds()[1][1] - g.bounds()[0][1]) > 0:
        assert (out > -1e-6).mean() > 0.85


def test_box_and_transform():
    b = mesh.box(2, 1, 4, base=True)
    assert b.tris == 12
    lo, hi = b.bounds()
    assert np.allclose(lo, [-1, 0, -2]) and np.allclose(hi, [1, 1, 2])  # base=True sits on the floor
    lo, hi = mesh.xf(b, t=(5, 0, 0), r=(0, 90, 0)).bounds()
    assert np.allclose(lo, [3, 0, -1], atol=1e-5) and np.allclose(hi, [7, 1, 1], atol=1e-5)


# ---------------------------------------------------------------- asset library
def test_every_asset_builds_with_its_defaults():
    names = assets.names()
    assert len(names) >= 25 and {"cow", "tank", "digester", "generator", "house", "bacteria"} <= set(names)
    for name in names:
        m = assets.build(name)
        lo, hi = m.bounds()
        assert m.parts and m.tris > 0 and np.all(np.isfinite(lo)) and np.all(hi > lo - 1e-6), name
        assert {"top", "label", "center"} <= set(m.anchors), name


def test_assets_take_parameters():
    small, big = assets.build("tank", r=2.0), assets.build("tank", r=6.0)
    assert (big.bounds()[1] - big.bounds()[0])[0] > 2.5 * (small.bounds()[1] - small.bounds()[0])[0]
    red = assets.build("crate", color="#ff0000")
    assert any(p.color.lower() == "#ff0000" for p in red.parts)
    tank = assets.build("tank", crust=True)
    assert {p.kind for p in tank.parts} >= {"liquid", "crust"}  # the liquid can fill, the crust can show


def test_resolve_names_the_ai_might_use():
    assert assets.resolve("cows") == "cow"
    assert assets.resolve("Cow") == "cow"
    assert assets.resolve("biodigester") == "digester"
    assert assets.resolve("storage tank") == "tank"
    assert assets.resolve("space laser 3000") == "crate"  # unknown → a simple box, never a crash
    text = assets.catalog()
    assert all(n in text for n in assets.names())


# ---------------------------------------------------------------- scene plan checker
def test_validate_repairs_a_broken_plan():
    bad = {"title": "x", "areas": [{"id": "farm"}],
           "objects": [{"id": "Cows!", "asset": "cows", "count": 500, "area": "nowhere", "scale": 99},
                       {"id": "ship", "asset": "space laser 3000"},
                       {"asset": "tank"}],
           "scenes": [{"camera": {"move": "spin around", "target": "ghost"},
                       "actions": [{"do": "explode", "target": "ship"}, {"do": "spin", "target": "missing"}],
                       "keywords": [{"text": "a very long keyword line that never ends", "kind": "danger"}],
                       "labels": [{"text": f"L{k}", "target": "cows"} for k in range(9)]}]}
    fixed, fixes = plan.validate(bad, ["One line.", "Two lines.", "Three lines."])
    assert fixes and len(fixed["scenes"]) == 3  # one shot per script scene
    ids = {o["id"] for o in fixed["objects"]}
    assert len(ids) == 3 and all(i == plan.slug(i) for i in ids)
    o = next(o for o in fixed["objects"] if o["asset"] == "cow")
    assert o["count"] <= 60 and o["scale"] <= 25 and o["area"] in {a["id"] for a in fixed["areas"]}
    s0 = fixed["scenes"][0]
    assert s0["camera"]["move"] in plan.CAMERA_MOVES and s0["camera"]["target"] in ids
    assert all(a["do"] in plan.ACTIONS and a["target"].split(".")[0] in ids for a in s0["actions"])
    assert len(s0["keywords"][0]["text"].split()) <= 4 and s0["keywords"][0]["kind"] in plan.KINDS
    assert len(s0["labels"]) <= 4
    md = plan.summary(fixed)
    assert "Scene 1" in md and "cow" in md


def test_the_example_plan_is_already_clean():
    sc = make_script(examples.COW_POOP_SCRIPT)
    texts = [s["narration"] for s in sc["scenes"]]
    assert 120 <= sum(len(t.split()) for t in texts) <= 175  # about 60 seconds of narration
    p, fixes = plan.validate(examples.COW_POOP_PLAN, texts)
    assert len(p["scenes"]) == len(texts) == 13 and len(fixes) <= 2, fixes


def test_planner_without_ai(offline):
    tiny = make_script("[TITLE] Dam\n[SCENE] a river\nNARRATOR: The river pushes 300 tons of water.\n"
                       "[SCENE] turbine\nNARRATOR: The turbine spins and the town lights up.")
    p, provider, _ = planner.make_plan(tiny, "short")
    assert provider.startswith("Built-in planner") and len(p["scenes"]) == 2
    assert {"house"} & {o["asset"] for o in p["objects"]}
    assert any(k["kind"] == "number" for s in p["scenes"] for k in s["keywords"])  # "300 TONS" in white
    demo = make_script(examples.COW_POOP_SCRIPT)
    p2, provider2, _ = planner.make_plan(demo, "short")
    assert provider2.startswith("Built-in example") and len(p2["scenes"]) == 13


def test_ai_plan_is_checked_and_fixed(sf_root, monkeypatch):
    import json

    from storyforge import llm

    tiny = make_script("[TITLE] T\n[SCENE] a cow\nNARRATOR: One cow.\n[SCENE] a tank\nNARRATOR: One tank.")

    def fake(messages, json_mode, temperature, max_tokens):
        return json.dumps({"areas": [{"id": "farm"}], "objects": [{"id": "c", "asset": "cow", "area": "farm"}],
                           "scenes": [{"camera": {"move": "orbit", "target": "c"}, "actions": []}]})

    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])
    p, provider, fixes = planner.make_plan(tiny, "short")
    assert provider == "FakeAI" and len(p["scenes"]) == 2 and fixes  # the missing shot was added


# ---------------------------------------------------------------- world: timing, events, camera, labels
def test_actions_hit_on_the_spoken_word(cow_world):
    w = cow_world
    sc = w.scenes[1]
    t = w.at_time(1, "manure")
    word = next(x for x in sc["words"] if x["w"].lower().startswith("manure"))
    assert abs(sc["start"] + t - word["s"]) < 1e-6
    assert abs(w.at_time(1, 0.5) - sc["dur"] / 2) < 1e-6  # a fraction of the shot
    assert w.at_time(1, "zebra", 0.1) == pytest.approx(sc["dur"] * 0.1)  # unknown word → default


def test_objects_appear_and_stay(cow_world):
    w = cow_world
    pile = w.groups["piles"][0]
    assert "piles" in w.hidden_at_start
    assert w.state(pile, 0.1)["vis"] == 0.0
    assert w.state(pile, w.scenes[1]["end"] - 0.05)["vis"] > 0.9  # appeared on "manure"
    mixer = w.groups["mixer1"][0]
    on = w.scenes[5]["start"] + w.at_time(5, "spins")
    assert not w.state(mixer, on - 0.2)["spin_on"]  # starts on the word "spins"
    a, b = w.state(mixer, on + 0.3), w.state(mixer, on + 0.8)
    assert a["spin_on"] and b["spin"] > a["spin"]  # the agitator spins


def test_camera_never_jumps_between_shots(cow_world):
    w = cow_world
    for i in range(1, len(w.scenes)):
        e0, _, _, f0 = w.camera(i - 1, w.scenes[i - 1]["dur"] - 1e-3)
        e1, _, _, f1 = w.camera(i, 1e-3)
        if max(f0, f1) > 0.5:  # a fade (into the tiny world) hides the cut
            continue
        assert np.linalg.norm(e1 - e0) < 0.5, i
    for i in range(len(w.scenes)):
        eye, tgt, fov, _ = w.camera(i, w.scenes[i]["dur"] / 2)
        assert eye[1] > 0.3 and 15 < fov < 80 and np.linalg.norm(eye - tgt) > 1.0  # above the floor, looking at something


def test_labels_stay_on_screen_and_dont_overlap(cow_world):
    from storyforge.world.labels import LabelMaker

    w = cow_world
    lm = LabelMaker(w.size)
    seen = 0
    for i, sc in enumerate(w.scenes):
        T = sc["end"] - 0.3
        eye, tgt, fov, _ = w.camera(i, T - sc["start"])
        out = w.labels(i, T, eye, tgt, fov, lm)
        seen += len(out)
        for lb in out:
            h, wd = lb.image.shape[:2]
            assert wd / 2 - 1 <= lb.x <= w.size[0] - wd / 2 + 1
        for a in range(len(out)):
            for b in range(a):
                la, lb2 = out[a], out[b]
                same_row = abs(la.y - lb2.y) < la.image.shape[0] * 0.9
                assert not (same_row and abs(la.x - lb2.x) < (la.image.shape[1] + lb2.image.shape[1]) / 2 - 2)
    assert seen >= 8


def test_frames_are_pure_functions_of_time(cow_world):
    """Same time → same frame (that's what makes resume and single-scene re-renders work)."""
    w = cow_world
    T = w.scenes[8]["start"] + 1.0
    a, b = w.frame(T), w.frame(T)
    assert np.allclose(a.eye, b.eye) and len(a.draws) == len(b.draws)
    pa, pb = w.particles(8, T), w.particles(8, T)
    assert (pa is None and pb is None) or np.allclose(pa, pb)


# ---------------------------------------------------------------- keyword captions and sounds
def test_keyword_captions_are_colored_by_meaning():
    head = "\n".join(captions.keyword_header((1080, 1920), "9x16", "en"))
    assert "Style: Key_problem" in head and "Style: Key_part" in head and "Style: Key_number" in head
    ev = captions.keyword_events([{"text": "130 TONS", "kind": "number", "start": 1.0, "end": 3.0},
                                  {"text": "CRUST", "kind": "problem", "start": 2.0, "end": 4.0},
                                  {"text": "agitator", "kind": "part", "start": 4.0, "end": 5.0}], "en", 5.0)
    assert [e[2] for e in ev] == ["Key_number", "Key_problem", "Key_part"]
    assert ev[0][1] <= ev[1][0]  # one keyword at a time
    assert "AGITATOR" in ev[2][3].upper()
    fa = captions.keyword_events([{"text": "مخزن", "kind": "part", "start": 0, "end": 1}], "fa", 1.0)
    assert captions.RLE in fa[0][3] and captions.PDF in fa[0][3]


@pytest.mark.parametrize("name", ["hum", "pour", "bubbles", "zap", "click", "pop", "alarm_hum", "rumble", "steam"])
def test_mechanical_sounds_are_soft(name):
    x = music.make_sfx(name, 1)
    assert len(x) > music.SR * 0.1 and np.abs(x).max() <= 1.0
    spec = np.abs(np.fft.rfft(x[:, 0]))
    freqs = np.fft.rfftfreq(len(x), 1 / music.SR)
    assert spec[freqs > 8000].sum() / spec.sum() < 0.01  # nothing above 8 kHz


def test_onnx_kokoro_is_the_first_backup():
    order = [e for e, _ in tts.engine_order("en", tts.DEFAULT_VOICE["en"])]
    assert order[:3] == ["kokoro", "kokoro_onnx", "edge"]
    assert dict(tts.engine_order("en", tts.DEFAULT_VOICE["en"]))["kokoro_onnx"] == "am_fenrir"  # the same voice


# ---------------------------------------------------------------- the renderer (EGL / Mesa on the CPU)
def test_renderer_draws_the_low_poly_look(cow_world, needs_gl):
    from storyforge.world import gl
    from storyforge.world.labels import LabelMaker

    r = gl.Renderer((180, 320), msaa=2, shadow_size=512)
    try:
        cow_world.upload(r)
        img = r.render(cow_world.frame(cow_world.scenes[0]["start"] + 1.0, LabelMaker(cow_world.size)))
    finally:
        r.release()
    assert img.shape == (320, 180, 3) and img.dtype == np.uint8
    corner = img[:12, :12].reshape(-1, 3).mean(0)
    assert corner[2] > corner[0] and corner[1] > corner[0]  # dark teal background
    assert img.std() > 12  # the barn, cows and grid are drawn


def test_render_span_makes_a_clip_of_the_right_length(cow_world, needs_gl, tmp_path):
    from storyforge.world import video
    from storyforge.world.labels import LabelMaker

    r, rsize, how = video.make_renderer((180, 320))
    try:
        cow_world.upload(r)
        out = tmp_path / "c.mp4"
        n = video.render_span(cow_world, r, LabelMaker(rsize), 2.0, 3.0, out, (180, 320))
        still = video.render_still(cow_world, r, LabelMaker(rsize), 2.5, tmp_path / "s.jpg")
    finally:
        r.release()
    assert n == video.FPS and abs(media.duration(out) - 1.0) < 0.05 and media.video_size(out) == (180, 320)
    assert still.exists() and "CPU" in how or "GPU" in how
    assert math.isfinite(media.duration(out))
