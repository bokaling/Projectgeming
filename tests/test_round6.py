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
    story = pipeline.auto_series(project.EpisodeOptions(idea="A story about a lost robot", source="ai"))
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
