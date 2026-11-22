"""Short/long formats, per-shot clips with resume, chapters, batch mode."""
from storyforge import media, pipeline, project, publish, render
from storyforge.messages import Reporter

STORY = " ".join(f"Part {i}: the tank filled and the pipe carried gas to the generator." for i in range(5))


def test_snap_and_ranges():
    assert render.snap(1.234) == 37 / 30 and render.TRANSITION == 0.0  # hard cuts
    assert render.chunk_ranges(10, 4) == [(0, 4), (4, 8), (8, 10)]


def test_clips_joined_without_reencoding_and_resumed_per_clip(offline, needs_gl):
    series = project.Series.create("Chunks")
    opts = project.EpisodeOptions(length="short", resolution="480p")
    rep = Reporter(echo=False)
    res = pipeline.generate(series, opts, STORY, rep)
    ep = series.episode(1)
    clips = [ep.clip_path(sc["id"], "9x16", "en") for sc in ep.load_script()["scenes"]]
    assert len(clips) >= 3 and all(c.exists() for c in clips) and ep.clip_path("end", "9x16", "en").exists()
    video = res["videos"][0]
    tl = project.read_json(ep.audio_dir("en") / "timeline.json")
    assert abs(media.duration(video) - tl["total"]) < 0.1  # picture and sound line up
    # "disconnect": one finished shot clip is lost; only that clip is made again
    clips[1].unlink()
    rep2 = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep2, ep.load_options()).make_video()
    text = rep2.text(300)
    assert "1 clip(s)" in text and "Scene 2/" in text and "Voiceover" not in text


def test_long_format_has_chapters(offline, needs_gl):
    series = project.Series.create("Long one")
    opts = project.EpisodeOptions(length="long", resolution="480p", end_card=False)
    marked = ("[CHAPTER] The tank\nNARRATOR: The tank fills with slurry.\nNARRATOR: It takes all night.\n"
              "[CHAPTER] The pipe\nNARRATOR: A pipe carries the gas away.\nNARRATOR: It hisses.\n"
              "[CHAPTER] The power\nNARRATOR: The generator hums.\nNARRATOR: The houses light up.")
    res = pipeline.generate(series, opts, marked, Reporter(echo=False))
    assert media.video_size(res["videos"][0]) == (854, 480)  # 16:9
    meta = project.read_json(series.episode(1).export_dir / "metadata.json")
    assert "chapters" in meta["languages"]["en"]  # too short for YouTube's 10 s rule here; see the next test
    sc = series.episode(1).load_script()
    assert [s["chapter"] for s in sc["scenes"]][:1] == ["The tank"]
    tl = {"scenes": [{"start": i * 20.0} for i in range(len(sc["scenes"]))], "total": 20.0 * len(sc["scenes"])}
    chs = publish.make_chapters(sc, tl, "en")
    assert chs[0]["time"] == "0:00" and [c["title"] for c in chs] == ["The tank", "The pipe", "The power"]


def test_auto_chapters_every_90_seconds():
    scenes = [{"narration": f"Scene {i} begins here now", "chapter": ""} for i in range(60)]
    tl = {"scenes": [{"start": i * 10.0} for i in range(60)], "total": 600.0}
    chs = publish.make_chapters({"scenes": scenes}, tl, "en")
    assert len(chs) == 7 and chs[0]["time"] == "0:00" and chs[1]["time"] == "1:30"


def test_batch_makes_every_script_and_survives_a_bad_one(offline, needs_gl):
    series = project.Series.create("Batch")
    opts = project.EpisodeOptions(length="short", resolution="480p", end_card=False)
    text = "[TITLE] One\nNARRATOR: The first story starts.\n=====\n[TITLE] Two\n[SCENE] x\n=====\n" \
           "[TITLE] Three\nNARRATOR: The third story ends."
    rep = Reporter(echo=False)
    res = pipeline.generate(series, opts, text, rep)
    assert res["episodes"] == [1, 3] and res["failed"] == [2]  # script 2 has no lines
    assert rep.finished and "2 of 3 videos" in rep.text(400)
    assert series.episode(3).load_script()["title"] == "Three"
