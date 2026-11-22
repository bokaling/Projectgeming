"""End-to-end: the whole 3D pipeline on CPU with fake AI and no internet."""
import numpy as np
import pytest
from PIL import Image

from storyforge import media, pipeline, project
from storyforge.messages import Reporter

TINY = """[TITLE] The Tank That Breathes
[SCENE] cows in a barn
NARRATOR: These 40 cows make a mountain of manure.
[SCENE] the storage tank fills up
NARRATOR: It all flows into a giant tank. Then the gas starts.
[SCENE] houses light up
NARRATOR: And suddenly, 12 houses have power.
"""


def make(name="Test Show", **kw):
    series = project.Series.create(name)
    opts = project.EpisodeOptions(length="short", resolution="480p", **kw)
    return series, opts


def test_full_short_and_resume(offline, needs_gl):
    series, opts = make()
    rep = Reporter(echo=False)
    res = pipeline.generate(series, opts, TINY, rep)
    ep = series.episode(1)
    video = res["videos"][0]
    tl = project.read_json(ep.audio_dir("en") / "timeline.json")
    assert media.has_audio(video) and abs(media.duration(video) - tl["total"]) < 0.1  # picture and sound line up
    assert media.video_size(video) == (480, 854)
    plan = ep.load_plan()
    assert len(plan["scenes"]) == 3 and {o["asset"] for o in plan["objects"]} >= {"cow", "tank", "house"}
    text = rep.text(400)
    assert "Built-in planner (no AI)" in text and "3D render" in text and "Timing report" in text
    assert "joined without re-encoding" in text
    assert res["thumbnails"] and (ep.export_dir / "metadata.md").exists()
    # every scene lasts exactly as long as its voice line (+ a short breath)
    for s in tl["scenes"][:-1]:
        assert 0 < s["dur"] - s["voice"] < 0.4
    assert tl["scenes"][-1]["dur"] - tl["scenes"][-1]["voice"] < 0.75  # a slightly longer breath before the end
    # resume: nothing is made again
    rep2 = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep2, ep.load_options()).make_video()
    t2 = rep2.text(200)
    assert "3D render (" not in t2.split("Timing report")[0] and "Voiceover" not in t2 and "Scene plan (" not in t2


def test_changing_one_line_redoes_only_that_voice_and_later_shots(offline, needs_gl):
    from storyforge import script as script_mod

    series, opts = make("Edit Show")
    pipeline.generate(series, opts, TINY, Reporter(echo=False))
    ep = series.episode(1)
    sc = ep.load_script()
    sc["scenes"][2]["lines"] = [{"speaker": "NARRATOR", "text": "And suddenly, 99 houses have power."}]
    sc["scenes"][2]["narration"] = sc["scenes"][2]["lines"][0]["text"]
    script_mod.save_script(ep, sc)
    rep = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep, ep.load_options()).make_video()
    text = rep.text(200)
    assert "Voiceover (English, 1 scenes" in text
    assert "Scene 3/3" in text and "Scene 1/3" not in text  # shot 1 and 2 kept


def test_plan_first_makes_stills(offline, needs_gl):
    series, opts = make("Plan Show")
    rep = Reporter(echo=False)
    pipeline.prepare(series, opts, TINY, rep)
    ep = series.episode(1)
    stills = sorted((ep.dir / "stills").glob("s*_9x16.jpg"))
    assert len(stills) == 3
    a = np.asarray(Image.open(stills[1]))
    assert a.std() > 10  # a real picture, not an empty frame
    assert "The plan is ready" in rep.text(100)


def test_quick_test_uses_the_demo(offline, needs_gl):
    rep = Reporter(echo=False)
    res = pipeline.quick_test(rep)
    assert res["videos"] and media.duration(res["videos"][0]) > 3
    assert "Built-in example plan" in rep.text(300)  # the cow demo's first 3 shots


def test_topic_without_any_ai_still_makes_a_video(offline, needs_gl):
    series, opts = make("Topic Show", idea="how a dam makes electricity", source="ai")
    res = pipeline.generate(series, opts, "", Reporter(echo=False))
    assert res["videos"]
    assert "[TITLE] How a dam makes electricity" in series.episode(1).load_options().script_text


def test_empty_script_is_a_friendly_error(offline):
    from storyforge.messages import FriendlyError

    series, opts = make("Empty")
    with pytest.raises(FriendlyError):
        pipeline.generate(series, opts, "   ", Reporter(echo=False))
