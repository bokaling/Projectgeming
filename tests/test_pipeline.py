"""End-to-end tests: the whole pipeline on CPU with fake AI and no internet."""
import pytest

from storyforge import media, pipeline, project
from storyforge.messages import Reporter

from conftest import FA, SCRIPT  # noqa: E402,F401


def make_episode(langs=("en",), formats=("9x16",)):
    series = project.Series.create("Test Show")
    ep = series.episode(series.next_episode_number())
    opts = project.EpisodeOptions(idea="radio", languages=list(langs), formats=list(formats), resolution="480p",
                                  scene_count=3, hero_count=2)
    return series, ep, opts


def test_full_episode_and_resume(offline):
    series, ep, opts = make_episode(langs=("en", "fa"), formats=("9x16", "16x9"))
    rep = Reporter(echo=False)
    pipe = pipeline.Pipeline(series, ep, rep, opts)
    pipe.write_script()
    result = pipe.make_video()
    assert len(result["videos"]) == 2  # 2 languages x 1 format (short = 9:16)
    for v in result["videos"]:
        assert media.has_audio(v) and media.duration(v) > 3
    assert media.video_size(ep.video_path("en", "9x16")) == (480, 854)
    meta = (ep.export_dir / "metadata.md").read_text(encoding="utf-8")
    assert "AI-generated" in meta and "Snapchat" in meta and "Farsi" in meta
    assert len(result["thumbnails"]) == 2
    assert series.data["episodes"]["1"]["title"] == "The Signal"  # remembered for the next episode
    # Resume: running again redoes nothing
    rep2 = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep2, opts).make_video()
    text = rep2.text(200)
    assert "Scene pictures" not in text and "Voiceover" not in text and "Final video" not in text


def test_edit_one_line_redoes_only_that_voice(offline):
    from storyforge import script as script_mod

    series, ep, opts = make_episode()
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), opts)
    pipe.write_script()
    pipe.make_video()
    sc = ep.load_script()
    sc["scenes"][1]["lines"] = [{"speaker": "NARRATOR", "text": "It knew her name, and her secret."}]
    script_mod.save_script(ep, sc)
    rep = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep, opts).make_video()
    text = rep.text(200)
    assert "Voiceover (English, 1 scenes, 1 voice," in text  # only the edited scene
    assert "Scene pictures" not in text  # pictures kept


def test_regenerate_and_upload_one_scene(offline, tmp_path):
    series, ep, opts = make_episode()
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), opts)
    pipe.write_script()
    pipe.make_video()
    before = ep.image_path("s02", "9x16").stat().st_mtime_ns
    pipe.regenerate("s02")
    assert ep.load_script()["scenes"][1]["regen"] == 1
    assert ep.image_path("s02", "9x16").stat().st_mtime_ns != before
    # replace scene 3 with your own video clip
    import subprocess

    clip = tmp_path / "mine.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:d=1:r=24",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    ep.set_upload("s03", clip)
    rep = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep, opts).make_video()
    assert "video clip" in rep.text(200)


def test_quick_test_end_to_end(offline):
    rep = Reporter(echo=False)
    result = pipeline.quick_test(rep)
    assert len(result["videos"]) == 1 and media.video_size(result["videos"][0]) == (720, 1280)
    parts = [p for _, p, _ in rep.summary]
    assert {"Script", "Pictures", "Final video"} <= set(parts)
    sc = project.Series("quick-test").episode(1).load_script()
    assert len(sc["scenes"]) == 3 and sc["scenes"][1]["lines"][-1]["speaker"] == "MIRA"  # narrator + character
    assert "Quick test results" in rep.text(200)


def test_missing_farsi_gives_friendly_error(offline):
    series, ep, opts = make_episode(langs=("fa",))
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), opts)
    sc_raw = dict(SCRIPT)
    from storyforge import script as script_mod

    script_mod.save_script(ep, script_mod.normalize_script(sc_raw, opts))
    with pytest.raises(Exception) as err:
        pipe.voices("fa")
    assert "Farsi" in str(err.value) and "Script step" in str(err.value)
