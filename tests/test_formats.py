"""Short/long formats, chunked rendering with resume, chapters, batch mode."""
import pytest

from storyforge import media, pipeline, project, publish, render
from storyforge.messages import Reporter

STORY = " ".join(f"Part {i} of the night was colder than the one before it, and the radio kept talking." for i in range(14))


@pytest.fixture()
def small_chunks(monkeypatch):
    monkeypatch.setattr(render, "CHUNK_SCENES", 4)


def test_snap_and_ranges():
    assert render.snap(1.234) == 37 / 30 and render.TRANSITION == 0.0  # hard cuts
    assert render.chunk_ranges(10, 4) == [(0, 4), (4, 8), (8, 10)]


def test_paste_video_joined_without_reencoding_and_resumed_per_clip(offline):
    series = project.Series.create("Chunks")
    opts = project.EpisodeOptions(length="short", resolution="480p", hero_count=0)
    rep = Reporter(echo=False)
    res = pipeline.generate(series, opts, STORY, rep)
    ep = series.episode(1)
    n = len(ep.load_script()["scenes"])
    clips = [ep.clip_path(sc["id"], "9x16", "en") for sc in ep.load_script()["scenes"]]
    assert n > 8 and all(c.exists() for c in clips)
    assert (ep.dir / "render" / "cold_9x16_en.mp4").exists() and (ep.dir / "render" / "end_9x16_en.mp4").exists()
    video = res["videos"][0]
    tl = project.read_json(ep.audio_dir("en") / "timeline.json")
    assert abs(media.duration(video) - tl["total"]) < 0.1  # picture and sound line up
    assert media.video_size(video) == (480, 854)
    assert "joined without re-encoding" in rep.text(400) and "Timing report" in rep.text(400)
    # "disconnect": one finished scene clip is lost; only that clip is made again
    clips[1].unlink()
    rep2 = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep2, ep.load_options()).make_video()
    text = rep2.text(300)
    assert "1 clips" in text and "Scene pictures" not in text and "Voiceover" not in text


def test_long_format_has_chapters(offline, small_chunks, monkeypatch):
    series = project.Series.create("Long one")
    opts = project.EpisodeOptions(length="long", resolution="480p", hero_count=0)
    marked = "[CHAPTER] The call\n" + STORY[:400] + "\n[CHAPTER] The road\n" + STORY[400:800] + \
             "\n[CHAPTER] The door\n" + STORY[800:]
    res = pipeline.generate(series, opts, marked, Reporter(echo=False))
    assert media.video_size(res["videos"][0]) == (854, 480)  # 16:9
    meta = project.read_json(series.episode(1).export_dir / "metadata.json")
    chs = meta["languages"]["en"]["chapters"]
    assert chs[0]["time"] == "0:00" and len(chs) == 3 and chs[1]["title"] == "The road"
    assert "Chapters:\n0:00" in meta["languages"]["en"]["description"]


def test_auto_chapters_every_90_seconds():
    scenes = [{"narration": f"Scene {i} begins here now", "chapter": ""} for i in range(60)]
    tl = {"scenes": [{"start": i * 10.0} for i in range(60)], "total": 600.0}
    chs = publish.make_chapters({"scenes": scenes}, tl, "en")
    assert len(chs) == 7 and chs[0]["time"] == "0:00" and chs[1]["time"] == "1:30"


def test_batch_makes_every_script_and_survives_a_bad_one(offline, monkeypatch):
    series = project.Series.create("Batch")
    opts = project.EpisodeOptions(length="short", resolution="480p", hero_count=0)
    text = "[TITLE] One\nNARRATOR: The first story starts.\n=====\n[TITLE] Two\n[SCENE] x\n=====\n" \
           "[TITLE] Three\nNARRATOR: The third story ends."
    rep = Reporter(echo=False)
    res = pipeline.generate(series, opts, text, rep)
    assert res["episodes"] == [1, 3] and res["failed"] == [2]  # script 2 has no lines
    assert rep.finished and "2 of 3 videos" in rep.text(400)
    assert series.episode(3).load_script()["title"] == "Three"
