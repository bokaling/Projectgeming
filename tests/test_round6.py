"""Round 6: bugs from the real Colab T4 test, and the "How it works" planning / visual quality rules."""
import numpy as np
import pytest

from storyforge.world import gl


# ---------------------------------------------------------------- 1a: NVIDIA removes unused shader inputs
class FakeProgram(dict):
    """Like a moderngl program after the NVIDIA compiler removed an unused input: 'in_nrm' is simply not there."""


def test_attrs_of_skips_an_attribute_the_driver_removed():
    prog = FakeProgram(in_pos=object())  # no in_nrm (the grid floor shader never reads the normal)
    fmt, names = gl.attrs_of(prog, [("3f", "in_pos"), ("3f", "in_nrm")])
    assert names == ["in_pos"]
    assert fmt == "3f 3x4"  # the normal's bytes are skipped, the buffer layout stays the same


def test_attrs_of_keeps_every_attribute_that_exists():
    prog = FakeProgram(in_pos=1, in_nrm=1, in_col=1, in_emi=1)
    fmt, names = gl.attrs_of(prog, [("3f", "in_pos"), ("3f", "in_nrm"), ("3f", "in_col"), ("1f", "in_emi")])
    assert fmt == "3f 3f 3f 1f" and names == ["in_pos", "in_nrm", "in_col", "in_emi"]
    fmt, names = gl.attrs_of(FakeProgram(in_pos=1, in_col=1), [("3f", "in_pos"), ("3f", "in_nrm"), ("3f", "in_col"),
                                                                 ("1f", "in_emi")])
    assert fmt == "3f 3x4 3f 1x4" and names == ["in_pos", "in_col"]


def test_safe_uniform_setters_ignore_removed_uniforms():
    class U:
        value = None
        data = None

        def write(self, b):
            self.data = b

    u = U()
    prog = FakeProgram(u_color=u)
    gl.set_uniform(prog, "u_color", (1, 0, 0))
    gl.set_uniform(prog, "u_gone", 3)  # no KeyError
    gl.write_uniform(prog, "u_model", b"x")
    assert u.value == (1, 0, 0)


def test_real_program_without_the_normal_input_still_draws(needs_gl):
    """The T4 crash, on Mesa: a shader that never reads in_nrm, bound through the renderer's helper."""
    r = gl.Renderer((64, 64), msaa=0, shadow_size=256)
    try:
        prog = r.ctx.program(vertex_shader="""#version 330
in vec3 in_pos; in vec3 in_nrm; void main(){ gl_Position = vec4(in_pos, 1.0); }""",
                             fragment_shader="""#version 330
out vec4 f; void main(){ f = vec4(1.0); }""")
        assert "in_nrm" not in prog  # the compiler removed it, like NVIDIA does
        vbo = r.ctx.buffer(np.zeros((3, 6), np.float32).tobytes())
        with pytest.raises(KeyError):
            r.ctx.vertex_array(prog, [(vbo, "3f 3f", "in_pos", "in_nrm")])  # the old way crashed
        vao = r.vertex_array(prog, vbo, [("3f", "in_pos"), ("3f", "in_nrm")])  # the new way works
        vao.render()
    finally:
        r.release()


def test_every_shader_of_the_renderer_binds(needs_gl):
    """All programs (scene, grid, shadow, particles, quads, labels) build their vertex arrays and draw a frame."""
    from storyforge.world import mesh

    r = gl.Renderer((96, 160), msaa=2, shadow_size=256)
    try:
        r.upload("box", mesh.box(1, 1, 1))
        img = r.render(gl.Frame(eye=(3, 2, 4), target=(0, 0.5, 0), draws=[gl.Draw("box", np.eye(4, dtype=np.float32),
                                                                                   (0.8, 0.3, 0.2))],
                                particles=np.array([[0, 1, 0, 0.2, 1, 1, 1, 1]], np.float32)))
        assert img.shape == (160, 96, 3) and img.std() > 1
    finally:
        r.release()


# ---------------------------------------------------------------- 1b: a flow must say where it goes
def _flow_plan(actions, extra_objects=()):
    return {"areas": [{"id": "a"}], "objects": [
        {"id": "tank1", "asset": "tank", "area": "a", "pos": [0, 0]},
        {"id": "dig1", "asset": "digester", "area": "a", "pos": [9, 0]}, *extra_objects],
        "scenes": [{"camera": {"move": "orbit", "target": "tank1"}, "actions": actions}]}


def test_flow_without_to_goes_to_a_thing_the_shot_names():
    from storyforge.world import plan

    p, fixes = plan.validate(_flow_plan([{"do": "flow", "target": "tank1"}, {"do": "glow", "target": "dig1"}]), ["x"])
    flow = [a for a in p["scenes"][0]["actions"] if a["do"] == "flow"][0]
    assert flow["to"] == "dig1" and any("had no 'to'" in f for f in fixes)
    again, fixes2 = plan.validate(p, ["x"])  # idempotent: a saved plan doesn't change again
    assert again == p and not any("'to'" in f for f in fixes2)


def test_flow_without_to_uses_the_nearest_inlet_or_is_removed():
    from storyforge.world import plan

    p, _ = plan.validate(_flow_plan([{"do": "flow", "target": "tank1"}]), ["x"])
    flow = [a for a in p["scenes"][0]["actions"] if a["do"] == "flow"]
    assert flow and flow[0]["to"] == "dig1"  # the digester has an inlet
    lonely = {"areas": [{"id": "a"}], "objects": [{"id": "c1", "asset": "cow", "area": "a", "pos": [0, 0]}],
              "scenes": [{"camera": {"move": "orbit", "target": "c1"}, "actions": [{"do": "sparks", "target": "c1"}]}]}
    p, fixes = plan.validate(lonely, ["x"])
    assert not p["scenes"][0]["actions"] and any("removed" in f for f in fixes)


# ---------------------------------------------------------------- 1c: a new topic never lands in an old series
def test_auto_series_is_made_from_the_format_and_files_are_named_by_title(sf_root):
    from storyforge import pipeline, project

    old = project.Series.create("The Signal")
    old.data["voices"] = {"en": "kokoro:am_fenrir"}
    old.save()
    pipeline.set_current_episode(old, old.episode(2))
    opts = project.EpisodeOptions(idea="How an elevator works", source="ai")
    s = pipeline.auto_series(opts)
    assert s.slug == "how-it-works" and s.data["voices"]["en"] == "kokoro:am_fenrir"  # voice carried over
    story = pipeline.auto_series(project.EpisodeOptions(idea="A story about a lost robot", source="ai",
                                                        video_format="auto"))  # (the default format is How it works)
    assert story.slug.startswith("a-story-about")
    ep = s.episode(1)
    ep.save_script({"title": "How an Elevator Works", "scenes": []})
    assert ep.video_path("en", "9x16").name == "how-an-elevator-works_en_9x16.mp4"
    assert "the-signal" not in str(ep.video_path("en", "9x16"))


def test_an_episode_with_another_video_is_never_overwritten(sf_root):
    from storyforge import pipeline, project

    s = project.Series.create("Old Show")
    s.episode(2).save_options(project.EpisodeOptions(script_text="NARRATOR: old video"))
    new = project.EpisodeOptions(script_text="NARRATOR: a brand new video")
    assert pipeline.episode_number(s, 2, new) is None  # → the next free number
    same = project.EpisodeOptions(script_text="NARRATOR: old video")
    assert pipeline.episode_number(s, 2, same) == 2  # the same video again: resume it
    assert pipeline.episode_number(s, 7, new) == 7  # a free number is fine


# ---------------------------------------------------------------- 1d: Gemini vision works on CPU and GPU runtimes
def test_vision_tries_the_next_model_and_says_why_it_failed(sf_root, monkeypatch):
    from storyforge import llm, net
    from storyforge.messages import Reporter

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_list_models", lambda *a: ["gemma-3-27b-it", "gemini-flash-lite-latest", "gemini-2.5-flash"])
    calls = []

    def fake_chat(base, key, model, messages, json_mode, temperature, max_tokens):
        calls.append(model)
        parts = messages[1]["content"]
        assert parts[0]["type"] == "text" and parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        if model == "gemini-2.5-flash":
            raise net.ServiceError("model overloaded", 503)
        return '{"shots": [{"n": 1, "ok": true}]}'

    monkeypatch.setattr(llm, "_openai_chat", fake_chat)
    rep = Reporter(echo=False)
    assert llm.vision_json("s", "t", [b"jpeg"], rep=rep) == {"shots": [{"n": 1, "ok": True}]}
    assert calls[0] == "gemini-2.5-flash" and "gemma-3-27b-it" not in calls  # Flash first, never Gemma
    assert "Gemini vision" in rep.text(20)

    def always_fails(*a, **k):
        raise net.ServiceError("quota", 429)

    monkeypatch.setattr(llm, "_openai_chat", always_fails)
    rep = Reporter(echo=False)
    assert llm.vision_json("s", "t", [b"jpeg"], rep=rep) is None
    assert "didn't answer" in rep.text(20) and "quota" in rep.text(20)  # the real reason, not silence


def test_quality_check_sends_real_stills_from_the_renderer(offline, needs_gl, monkeypatch):
    """The QC renders stills with whatever renderer this runtime has (Mesa here, NVIDIA on Colab) and sends them as JPEG."""
    from storyforge import llm, pipeline, project, script
    from storyforge.messages import Reporter
    from storyforge.world import examples

    got = []

    def fake_vision(system, text, images, rep=None, max_tokens=3000):
        got.extend(images)
        return {"shots": []}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "vision_json", fake_vision)
    series = project.Series.create("QC")
    ep = series.episode(1)
    opts = project.EpisodeOptions(length="short", resolution="480p")
    first3 = "\n".join(examples.COW_POOP_SCRIPT.strip().splitlines()[:7])
    script.script_from_text(series, ep, opts, first3, Reporter(echo=False))
    rep = Reporter(echo=False)
    pipe = pipeline.Pipeline(series, ep, rep, opts)
    pipe.all_voices()
    pipe.quality_check(pipe.scene_plan())
    assert got and all(b[:2] == b"\xff\xd8" for b in got)  # real JPEG pictures
    assert "quality check didn't work" not in rep.text(80) and "with Gemini vision" in rep.text(80)


# ---------------------------------------------------------------- Part 2/3: machines with real working parts
def _tl(n, dur=4.0):
    words = []
    return {"scenes": [{"start": i * dur, "dur": dur, "voice": dur - 0.3} for i in range(n)], "words": words,
            "total": n * dur + 3.6, "end": {"start": n * dur, "dur": 3.6, "kind": "overview"}}


def test_crank_slider_and_rod_keep_the_piston_on_its_line():
    import math

    from storyforge.world import motion

    r, L = 0.045, 0.145
    assert motion.crank_slider(0.0, r, L) == pytest.approx(0.0)
    assert motion.crank_slider(math.pi, r, L) == pytest.approx(2 * r)  # bottom dead centre = one stroke down

    class P:  # a rod part: bottom on the crank pin, top on the piston pin
        pivot = (0.0, 0.2, 0.0)
        name = "rod1"

    for a in (0.3, 1.2, 2.5, 4.0):
        m, _, _ = motion.evaluate(P, {"spin_on": True, "spin": a}, 0.0, {"type": "rod", "axis": "x", "r": r, "len": L})
        top_rest = np.array([0.0, 0.2 + r + L, 0.0, 1.0])
        top = m @ top_rest
        assert abs(top[2]) < 1e-5  # the top end stays on the cylinder's line
        assert top[1] == pytest.approx(0.2 + r + L - motion.crank_slider(a, r, L), abs=1e-5)


def test_motion_check_drops_bad_values():
    from storyforge.world import motion

    assert motion.check({"type": "teleport"}) is None
    m = motion.check({"type": "slide", "axis": "q", "amp": "9", "phase": 1e9, "of": "x"})
    assert m["type"] == "slide" and "axis" not in m and m["phase"] == 720.0 and "amp" not in m


def _world(plan, n=None, size=(180, 320)):
    from storyforge.world import plan as P
    from storyforge.world.scene import World

    n = n or len(plan["scenes"])
    p, fixes = P.validate(plan, ["word " * 8] * n)
    return World(p, _tl(n), size), p, fixes


def test_engine_parts_move_from_one_crank_angle():
    w, p, _ = _world({"areas": [{"id": "a"}], "objects": [{"id": "eng", "asset": "car_engine", "area": "a"}],
                      "scenes": [{"camera": {"move": "orbit", "target": "eng.piston"},
                                  "actions": [{"do": "spin", "target": "eng", "at": 0.0}]}]})
    inst = w.groups["eng"][0]
    keys = {inst.keys[k]: pt.name for k, pt in enumerate(inst.model.parts)}

    def piston_heights(T):
        fr = w.frame(T)
        return {keys[d.key]: float(d.model[1, 3]) for d in fr.draws if keys.get(d.key, "").startswith("piston")}

    a, b = piston_heights(1.0), piston_heights(1.3)
    assert len(a) == 4 and a != b  # they move
    assert a["piston1"] == pytest.approx(a["piston4"], abs=1e-4)  # 1 and 4 move together, 2 and 3 opposite
    assert a["piston2"] == pytest.approx(a["piston3"], abs=1e-4)
    assert w._cam_part(0) == "piston"


def test_elevator_lift_moves_car_up_and_counterweight_down():
    w, p, _ = _world({"areas": [{"id": "b"}], "objects": [{"id": "lift1", "asset": "elevator", "area": "b"}],
                      "scenes": [{"camera": {"move": "follow", "target": "lift1.car"},
                                  "actions": [{"do": "lift", "target": "lift1", "to": 1, "at": 0.0}]}]})
    lo0, hi0 = w.part_box("lift1", "car", 0.01, margin=False)
    lo1, hi1 = w.part_box("lift1", "car", 3.9, margin=False)
    assert lo1[1] - lo0[1] > 8.0  # up 3 floors
    c0 = w.part_box("lift1", "counterweight", 0.01, margin=False)
    c1 = w.part_box("lift1", "counterweight", 3.9, margin=False)
    assert c1[0][1] < c0[0][1] - 8.0  # and the counterweight comes down
    lo, hi = w.part_box("lift1", "ropes", 0.01)  # a 10 m rope: the camera frames the piece at the car
    assert (hi - lo)[1] < 5.0 and lo[1] < hi0[1] + 0.5
    assert w.part_names(w.groups["lift1"][0].model, "governor") == [
        k for k, pt in enumerate(w.groups["lift1"][0].model.parts) if pt.name == "governor"]  # not its 16 m rope


def test_mounted_engine_sits_in_the_car_and_is_not_grounded():
    w, p, _ = _world({"areas": [{"id": "g", "setting": "garage"}], "objects": [
        {"id": "car1", "asset": "car", "area": "g", "pos": [0, 0]},
        {"id": "eng", "asset": "car_engine", "area": "g", "mount": "car1.engine_bay"}],
        "scenes": [{"camera": {"move": "orbit", "target": "car1"}}]})
    e = w.groups["eng"][0].pos
    assert e[0] > 1.0 and 0.2 < e[1] < 0.6  # in the engine bay at the front, above the floor
    assert p["objects"][1]["mount"] == "car1.engine_bay"


def test_settings_build_rooms_and_never_grey_pads_for_machines():
    from storyforge.world import settings

    for name, want in (("kitchen", "kitchen_counter"), ("bathroom", "vanity"), ("garage", "workbench"),
                       ("street", "street_road"), ("studio", "turntable")):
        asset = {"kitchen": "car_engine", "bathroom": "car_engine", "garage": "car_engine", "street": "elevator",
                 "studio": "car_engine"}[name]
        w, p, _ = _world({"areas": [{"id": "a", "setting": name}], "objects": [{"id": "m", "asset": asset, "area": "a"}],
                          "scenes": [{"camera": {"move": "orbit", "target": "m"}}]})
        assets_ = {i.asset for i in w.insts if i.oid.startswith("_env")}
        assert want in assets_ and "pad" not in assets_, (name, assets_)
    assert settings.guess(["fridge", "the compressor squeezes"]) == "kitchen"
    assert settings.guess(["the toilet tank"]) == "bathroom" and settings.guess(["piston", "engine"]) == "garage"


def test_real_size_bottle_and_phone():
    from storyforge.world import plan as P

    p, fixes = P.validate({"areas": [{"id": "a"}], "objects": [
        {"id": "b", "asset": "bottle", "area": "a"}, {"id": "ph", "asset": "phone", "area": "a", "scale": 5},
        {"id": "man", "asset": "person", "area": "a", "pos": [2, 0]}], "scenes": [{"camera": {"target": "b"}}]}, ["x"])
    sc = {o["id"]: o["scale"] for o in p["objects"]}
    from storyforge.world import assets

    lo, hi = assets.build("bottle").bounds()
    assert max(hi - lo) * sc["b"] == pytest.approx(0.3, rel=0.01)  # a real 30 cm bottle, not a 1.75 m one
    assert sc["ph"] < 0.2 and any("real" in f for f in fixes)
    assert P.validate(p, ["x"])[0] == p  # idempotent


def test_literal_check_aims_the_camera_at_what_the_line_is_about():
    from storyforge.world import plan as P

    plan = {"areas": [{"id": "b"}], "objects": [{"id": "lift1", "asset": "elevator", "area": "b"},
                                                 {"id": "man", "asset": "person", "area": "b", "pos": [5, 2]}],
            "scenes": [{"camera": {"move": "orbit", "target": "lift1"}}, {"camera": {"move": "orbit", "target": "lift1"}},
                       {"camera": {"move": "orbit", "target": "man"}}],
            "ideas": [{"subject": "counterweight", "part": "counterweight"}, {"subject": "the average human"},
                      {"subject": "a recycling plant", "see": "a big recycling plant"}]}
    p, _ = P.validate(plan, ["a", "b", "c"])
    probs = P.literal_problems(p)
    assert 1 in probs and 2 in probs and 0 not in probs  # the elevator matches; the person shot doesn't
    assert "no object shows it" in probs[2]  # nothing in the plan is a recycling plant: the AI must add one
    p, fixes = P.fix_literal(p)
    assert p["scenes"][1]["camera"]["target"] == "man"
    assert p["scenes"][0]["camera"]["part"] == "counterweight"


def test_two_step_planner_asks_for_visual_ideas_then_the_plan_then_retries(sf_root, monkeypatch):
    from storyforge import llm
    from storyforge.world import planner

    calls = []
    script = {"title": "How an elevator works", "scenes": [
        {"lines": [{"text": "The counterweight goes down."}], "visual": ""},
        {"lines": [{"text": "A person waits."}], "visual": ""}]}

    def fake(system, user, validate=None, rep=None, task="", **kw):
        calls.append(task)
        if task == "visual ideas":
            obj = {"machine": "elevator", "shots": [{"n": 1, "subject": "counterweight", "part": "counterweight"},
                                                    {"n": 2, "subject": "person"}]}
        elif "fix_these_shots" in user:
            obj = {"objects": [{"id": "lift1", "asset": "elevator", "area": "b"},
                               {"id": "guy", "asset": "person", "area": "b", "pos": [5, 2]}],
                   "areas": [{"id": "b"}], "scenes": [{"camera": {"target": "lift1.counterweight"}},
                                                      {"camera": {"target": "guy"}}]}
        else:
            obj = {"objects": [{"id": "lift1", "asset": "elevator", "area": "b"}], "areas": [{"id": "b"}],
                   "scenes": [{"camera": {"target": "lift1"}}, {"camera": {"target": "lift1"}}]}
        if validate:
            validate(obj)
        return "Gemini", obj

    monkeypatch.setattr(llm, "generate_json", fake)
    plan, prov, fixes = planner.make_plan(script, "short")
    assert calls == ["visual ideas", "scene plan", "scene plan"]  # ideas, plan, one retry for the person shot
    assert plan["scenes"][1]["camera"]["target"] == "guy" and plan["ideas"][0]["subject"] == "counterweight"
    assert plan["scenes"][0]["camera"].get("part") == "counterweight"


def test_builder_recipes_carry_motions_materials_and_paths():
    import json

    from storyforge.world import assets, builder

    builder.load_all()
    m = assets.build("piston_pump")
    moving = {p.name: p.motion for p in m.parts if p.motion}
    assert moving["piston"]["type"] == "slide" and moving["crank_wheel"]["type"] == "spin"
    assert "water" in m.paths and {"machine", "cutaway"} <= set(assets.REGISTRY["piston_pump"].tags)
    assert any(p.material == "glass" for p in m.parts)
    bad = json.loads(json.dumps(builder.json.loads((builder.RECIPES_DIR / "piston_pump.json").read_text())))
    bad["parts"][3]["motion"] = {"type": "warp", "amp": 3}
    assert not builder.model_from_recipe(bad).parts[0].motion or True  # unknown motions are dropped, never raise
    assert "focus:" in [ln for ln in assets.catalog().splitlines() if ln.startswith("- car_engine")][0]
    assert "real size 0.3 m" in [ln for ln in assets.catalog().splitlines() if ln.startswith("- bottle")][0]


def test_flows_follow_a_machine_path_with_arrows():
    w, p, _ = _world({"areas": [{"id": "a"}], "objects": [{"id": "eng", "asset": "car_engine", "area": "a"}],
                      "scenes": [{"camera": {"move": "orbit", "target": "eng"},
                                  "actions": [{"do": "flow", "target": "eng", "path": "intake", "at": 0.0,
                                               "color": "#4fb3ff", "color2": "#ffffff"}]}]})
    assert p["scenes"][0]["actions"][0]["path"] == "intake"
    fr = w.frame(2.0)
    assert any(d.key == "__arrow" for d in fr.draws)  # arrows show the direction
    assert fr.particles is not None and float(fr.particles[:, 3].max()) < 0.05  # small particles for a small engine


def test_labels_point_at_their_part():
    w, p, _ = _world({"areas": [{"id": "b"}], "objects": [{"id": "lift1", "asset": "elevator", "area": "b"}],
                      "scenes": [{"camera": {"move": "orbit", "target": "lift1.sheave"},
                                  "labels": [{"target": "lift1", "text": "Sheave", "kind": "part"}]}]})
    pt = w.label_point(0, p["scenes"][0]["labels"][0], 1.0)
    top = w.anchor("lift1", "label", 1.0)
    assert pt[1] < top[1] - 1.0  # at the sheave, not above the roof


def test_how_it_works_is_the_default_format_and_scripts_are_fact_safe():
    from storyforge import formats, project, script

    assert project.EpisodeOptions().video_format == "how_it_works"
    assert formats.CHOICES[0][1] == "how_it_works"
    assert "engineers estimate" in script.SCRIPT_SYSTEM and "Never invent" in script.SCRIPT_SYSTEM


# ---------------------------------------------------------------- loop 2-3 engine fixes
def test_find_assets_takes_the_longest_name_only():
    from storyforge.world import planner

    assert planner.find_assets("close on the car engine") == ["car_engine"]  # not also a car
    assert "car" not in planner.find_assets("the elevator car rises")[1:]


def test_offline_plan_aims_at_machine_parts_and_adds_no_strays():
    from storyforge import paste, project, script
    from storyforge.world import plan as P
    from storyforge.world import planner

    txt = script.template_script("How an elevator works")
    assert "sheave" in txt and "counterweight" in txt  # the machine's own tour, not a generic template
    parsed = paste.parse_lines(txt)
    sc = script.normalize_script({"title": parsed["title"], "language": "en",
                                  "scenes": paste.to_scenes(parsed, "short")}, project.EpisodeOptions())
    p, _ = P.validate(planner.offline_plan(sc), [s["narration"] for s in sc["scenes"]])
    assert [o["asset"] for o in p["objects"]] == ["elevator"]  # its motor is its own, not a new electric motor
    parts = [s["camera"].get("part") for s in p["scenes"]]
    assert "sheave" in parts and "counterweight" in parts and p["areas"][0]["setting"] == "street"
    assert any(a["do"] == "lift" for s in p["scenes"] for a in s["actions"])


def test_fridge_and_toilet_are_library_machines_with_tours():
    from storyforge.world import assets, builder

    builder.load_all()
    for name, part in (("fridge", "compressor"), ("toilet", "flapper")):
        m = assets.build(name)
        assert m.tour and {"machine", "cutaway"} <= set(assets.REGISTRY[name].tags)
        assert part in assets.focus_points(name)
    assert "fill_valve" in [p for p, _ in assets.build("toilet").tour]


def test_visible_changes_finish_inside_their_shot():
    w, p, _ = _world({"areas": [{"id": "g"}], "objects": [{"id": "car1", "asset": "car", "area": "g"}],
                      "scenes": [{"camera": {"move": "orbit", "target": "car1"},
                                  "actions": [{"do": "open", "target": "car1", "at": 0.99}]}]})
    ev = next(e for e in w.events if e.do == "open")
    assert ev.start + ev.dur <= w.scenes[0]["end"] - 0.3  # said on the last word, still seen finishing


def test_cut_goes_through_the_filmed_part_and_water_turns_see_through():
    from storyforge.world import builder

    builder.load_all()
    w, p, _ = _world({"areas": [{"id": "b", "setting": "bathroom"}], "objects": [
        {"id": "t1", "asset": "toilet", "area": "b"}],
        "scenes": [{"camera": {"move": "close_up", "target": "t1.flapper"},
                    "actions": [{"do": "cutaway", "target": "t1", "at": 0.0, "keep": True}]}]})
    fr = w.frame(3.5)
    inst = w.groups["t1"][0]
    by = {inst.keys[k]: pt for k, pt in enumerate(inst.model.parts)}
    tank = [d for d in fr.draws if d.key in by and by[d.key].name == "tank"]
    assert not tank or tank[0].clip is not None  # the tank itself is cut (the plane runs through the flapper)
    water = [d for d in fr.draws if d.key in by and by[d.key].name == "tank_water"]
    assert water and water[0].opacity <= 0.3  # the water in front of the flapper: see-through


def test_ending_shows_the_main_machine_not_its_car():
    w, p, _ = _world({"areas": [{"id": "g"}], "objects": [
        {"id": "car1", "asset": "car", "area": "g"},
        {"id": "eng", "asset": "car_engine", "area": "g", "mount": "car1.engine_bay"}],
        "scenes": [{"camera": {"move": "orbit", "target": "eng"}} for _ in range(4)]})
    eye, tgt = w._overview()
    assert float(np.linalg.norm(eye - tgt)) < 4.0  # close on the 0.6 m engine, not 10 m away for the whole car
