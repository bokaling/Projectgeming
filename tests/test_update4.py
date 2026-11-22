"""Update 4: script doctor, mood lock, fast editing, sound design, speed, upload order."""
import json
import os
import time

import numpy as np
import pytest
from PIL import Image

from storyforge import beats, captions, characters, doctor, gemini, media, paste, pipeline, project, publish
from storyforge.audio import align, music, tts
from storyforge.messages import Reporter
from storyforge.motion import cuts, effects

WEAK = """[TITLE] The Night Radio
[CHARACTER] MIRA: woman, 30s, short silver hair, yellow raincoat
[SCENE] a yellow taxi parked in the rain at 3 a.m., neon signs
NARRATOR: At exactly three in the morning, the old radio in the taxi turned itself on and started to play a very strange song.
MIRA: Who's there?
NARRATOR: She drove home. They lived happily ever after."""

STRONG = """[TITLE] The Night Radio
[STYLE] night, heavy rain, yellow taxi, green radio glow, horror thriller
NARRATOR: Her dead husband just called the taxi radio.
NARRATOR: Mira had buried him three years ago. Nobody else knew the code word.
MIRA: Who is this?
NARRATOR: But the voice knew her secret. It knew about the money. It knew where she hid the gun.
NARRATOR: Then the radio gave her an address. Forty minutes away. Ten minutes to get there, or her daughter dies.
NARRATOR: That's when she realized the voice was coming from the back seat.
NARRATOR: Who was sitting behind her?"""


# ---------------------------------------------------------------- A) script doctor
def test_doctor_scores_and_flags_weak_lines():
    weak, strong = doctor.score(WEAK), doctor.score(STRONG)
    assert set(weak.scores) == {k for k, _ in doctor.CATEGORIES} and 0 <= weak.total <= 100
    assert strong.total > weak.total + 20
    why = {w["no"]: " ".join(w["why"]) for w in weak.weak}
    assert "Slow intro" in why[4] and "Vague" in why[4]  # line 4 = the slow first line
    assert "closed" in why[6]  # "happily ever after"
    assert weak.scores["hook"] <= 3 and strong.scores["hook"] >= 8 and strong.scores["cliffhanger"] >= 8
    assert strong.has_style and strong.style_line.startswith("night, heavy rain")
    assert not weak.has_style and "night" in weak.style_line and "rain" in weak.style_line  # made from the script
    html = doctor.report_html(weak)
    assert "Line 4" in html and "/100" in html and "Mood lock" in html


def test_improve_keeps_format_and_never_dead_ends(sf_root, monkeypatch):
    from storyforge import llm

    def fake(messages, json_mode, temperature, max_tokens):
        orig = json.loads(messages[1]["content"])["original_script"]
        body = orig.replace("[TITLE] The Night Radio\n", "").replace(
            "NARRATOR: At exactly three in the morning, the old radio in the taxi turned itself on and started to play "
            "a very strange song.", "NARRATOR: The dead radio just said her name. Her husband's voice. He died three "
                                    "years ago.\nnarrator: At 3 a.m. Exactly.")
        body = body.replace("[CHARACTER] MIRA: woman, 30s, short silver hair, yellow raincoat", "[CHARACTER] MIRA: changed!")
        return json.dumps({"script": body, "changes": ["new hook"]})

    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])
    res = doctor.improve(WEAK)
    new = res["script"]
    assert res["ai"] and res["provider"] == "FakeAI" and "The dead radio just said her name." in new
    assert new.startswith("[TITLE] The Night Radio\n[CHARACTER] MIRA: woman, 30s, short silver hair, yellow raincoat")
    assert "changed!" not in new and "[SCENE] a yellow taxi" in new
    assert "NARRATOR: At 3 a.m. Exactly." in new  # speaker spelling fixed to yours
    # a rewrite with a new speaker is refused; with every AI busy you get a light polish, never an error
    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [
        ("BadAI", lambda *a: json.dumps({"script": WEAK.replace("MIRA:", "BOB:")}))])
    res2 = doctor.improve(WEAK)
    assert not res2["ai"] and "light polish" in res2["changes"][0]
    assert "NARRATOR: The old radio in the taxi turned itself on" in res2["script"]  # slow intro moved back
    assert "very " not in res2["script"]


# ---------------------------------------------------------------- B) mood lock, expressions
def test_style_line_and_expressions_in_every_prompt(offline):
    series = project.Series.create("Mood")
    opts = project.EpisodeOptions(length="short")
    res = pipeline.gemini_prompts(series, opts, STRONG, Reporter(echo=False))
    ep = series.episode(res["episode"])
    sc = ep.load_script()
    assert sc["mood_lock"] == "night, heavy rain, yellow taxi, green radio glow, horror thriller"
    assert sc["hook_text"].startswith("Her dead husband just called")
    for s in gemini.slots(series, sc, "short"):
        assert "night, heavy rain, yellow taxi, green radio glow, horror thriller" in s.prompt
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), opts)
    flux_prompt, _ = characters.scene_prompt(series, sc["scenes"][0], False, mood_lock=sc["mood_lock"])
    assert "green radio glow" in flux_prompt and pipe
    # expressions follow the words and never smile unless the script says so
    assert beats.expression("She screamed and ran", "tense").startswith("terrified")
    assert "not smiling" in beats.expression("The radio spoke.", "mysterious")
    assert beats.expression("He smiled at her", "calm") == "smiling warmly"
    mira = [s for s in sc["scenes"] if "Mira" in s.get("characters", [])]
    assert mira and all(s.get("expression") for s in mira)
    assert all("smil" not in s["expression"] or "not smiling" in s["expression"] for s in mira)


def test_auto_mood_lock_and_hook_text():
    lock = beats.auto_mood_lock("At midnight the rain hit the lab windows. The radio glowed.", "dark")
    assert lock.startswith("night, heavy rain, lab") and "horror" in lock
    assert beats.hook_text("At exactly three in the morning, the radio in the old taxi turned itself on for no reason.") \
        .endswith("…")
    assert beats.hook_text("Nobody touched the radio.") == "Nobody touched the radio."


# ---------------------------------------------------------------- C) editing
def _words(text, start=0.0, total=6.0):
    return align.proportional(align.split_words(text), start, start + total)


def test_cut_plan_every_2_seconds_from_the_same_picture(tmp_path):
    img = tmp_path / "a.png"
    Image.new("RGB", (768, 1344), (90, 60, 120)).save(img)
    words = _words("Nobody touched the radio but at three it spoke her name and then it started to scream", 0, 6.0)
    focus = cuts.cached_focus(img)
    shots = cuts.plan([{"image": str(img), "depth": "", "camera": "push_in", "fx": [], "focus": focus}], 180, 30,
                      "short", [w["s"] for w in words], 7, "tense", hook=True,
                      events={"punch": [0.4], "flash": [4.1], "shake": [4.1]})
    lens = [s["frames"] / 30 for s in shots]
    assert sum(s["frames"] for s in shots) == 180 and len(shots) == 3  # 6 s → 3 cuts of ~2 s
    assert all(1.3 <= x <= 2.7 for x in lens)
    assert len({s["image"] for s in shots}) == 1 and len({s["framing"] for s in shots}) == 3  # crops, one picture
    assert shots[0]["framing"] == "subject" and shots[0]["punch"] == [0.4]  # the hook starts tight + punch-in
    assert any(s["flash"] for s in shots) and any(s["shake"] for s in shots)
    starts = {round(w["s"] * 30) for w in words}
    assert all(s["start"] in starts for s in shots[1:])  # cuts land on word starts
    long_shots = cuts.plan([{"image": str(img), "focus": focus}], 30 * 12, 30, "long", [], 1)
    assert all(3 * 0.85 <= s["frames"] / 30 <= 5.5 for s in long_shots)


def test_crop_looks_at_the_subject_and_flash():
    rgb = np.zeros((1344, 768, 3), np.uint8)
    rgb[100:300, 500:700] = 255  # bright thing in the top right
    m = effects.make_move("static", 1.0, rgb.shape, (90, 160), crop=(1.6, 0.78, 0.15))
    assert m.base_zoom == 1.6 and m.center[0] > 0 and m.center[1] < 0
    ov = effects.Overlay((90, 160), [], 1, 1.0, grain=False, vignette=False)
    _, z, _, px, py, _, _ = effects.camera_state(m, ov, 0, 30, 30)
    assert z >= 1.6 and 0 < px <= (effects.OVERSCAN - 1 / z) / 2 + 1e-6  # never past the edge
    assert effects.flash_amount([0.5], 0.5) > 0.6 and effects.flash_amount([0.5], 0.9) < 0.05
    frames = list(effects.frames(rgb, None, (90, 160), 0.5, 30, "push_fast", grain=False, flash_times=[0.0],
                                 crop=(1.4, 0.5, 0.4)))
    assert len(frames) == 15 and frames[0].mean() > frames[-1].mean() + 40  # white flash on the first frame


def test_pop_captions_hook_text_and_scene_slices():
    w = _words("Nobody touched the radio. But at 3 a.m. it spoke her name", 0, 5)
    ev = captions.caption_events(w, (1080, 1920), "9x16", "en", style="pop")
    groups = captions.group_pop(w, "9x16", "en")
    assert all(1 <= len(g) <= 3 for g in groups) and len(ev) == len(groups)
    assert all("\\t(" in e[3] for e in ev)  # pop animation
    assert any("&H0000E6FF" in e[3] for e in ev)  # key word highlighted
    full = captions.build_ass(w, (1080, 1920), "9x16", "en", style="pop", hook="Nobody touched the radio")
    assert "Style: Hook," in full and ",Hook,," in full and "NOBODY TOUCHED THE RADIO" in full
    sl = captions.slice_events([captions.hook_event("X", "en")] + ev, 2.0, 4.0)
    assert all(0 <= s < e <= 2.0 + 1e-6 for s, e, _, _ in sl) and sl[0][2] == "Hook"
    fa = captions.build_ass(_words("هیچ‌کس به رادیو دست نزد", 0, 3), (1080, 1920), "9x16", "fa", style="pop",
                            hook="هیچ‌کس دست نزد")
    events = [ln for ln in fa.splitlines() if ln.startswith("Dialogue:")]
    assert all(captions.RLE in e and captions.PDF in e for e in events)  # Farsi rules kept
    style = [ln for ln in fa.splitlines() if ln.startswith("Style: Main")][0].split(",")
    assert style[1] == "Vazirmatn" and style[13] == "0" and style[-1] == "-1"


def test_end_card_text_and_picture(tmp_path):
    assert publish.end_card_text(1, "en", False) == "PART 2" and publish.end_card_text(2, "en", False) == "PART 3"
    assert publish.end_card_text(4, "en", True) == "THE END" and publish.end_card_text(1, "fa", False) == "قسمت ۲"
    png = publish.end_card_png("PART 2", "en", (360, 640), tmp_path / "c.png")
    a = np.asarray(Image.open(png))
    assert a.shape == (640, 360, 4) and a[..., 3].max() == 255 and a[..., 3].min() == 0  # transparent around


# ---------------------------------------------------------------- D) sound
def test_music_builds_and_drops_out_before_reveals():
    env, hits = music.tension_envelope(20.0, [10.0], hits=True)
    at = lambda t: env[int(t * music.SR)]  # noqa: E731
    assert at(2.0) < at(8.0)  # builds
    assert at(9.7) == 0.0 and at(10.5) > at(8.0)  # silent right before the reveal, back with a lift
    assert hits == [10.0]
    for name in ("low_whoosh", "boom", "soft_riser"):
        x = music.make_sfx(name, 1)
        spec = np.abs(np.fft.rfft(x[:, 0]))
        freqs = np.fft.rfftfreq(len(x), 1 / music.SR)
        assert spec[freqs > 8000].sum() / spec.sum() < 0.01, name  # soft: nothing above 8 kHz


def test_pause_before_reveals_and_narrator_speed(offline):
    assert pipeline.split_for_pauses("She opened the door. That's when she realized it was him.") == [
        "She opened the door.", "That's when she realized it was him."]
    assert pipeline.split_for_pauses("One. Two.") == ["One. Two."]
    series = project.Series.create("Speed")
    ep = series.episode(1)
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), project.EpisodeOptions())
    assert pipe.voice_choice("en")["speed"] == paste.NARRATOR_SPEED == 1.1


def test_voice_speed_keeps_captions_in_sync(sf_root, monkeypatch, tmp_path):
    """The engine makes speech at 1.1x and gives word times for THAT audio: captions follow it."""
    calls = []

    def fake_kokoro(text, voice, speed=1.0):
        calls.append(speed)
        n = len(text.split())
        dur = n * 0.4 / speed
        words = [(k * 0.4 / speed, (k + 1) * 0.4 / speed, w) for k, w in enumerate(text.split())]
        return (np.ones(int(dur * tts.SR), np.float32) * 0.1), words

    monkeypatch.setattr(tts, "kokoro", fake_kokoro)
    tts.reset_resolved()
    choice = {"engine": "kokoro", "voice": "am_fenrir", "speed": 1.1}
    used, words = tts.speak_lines([("One two three.", choice), ("Then it spoke.", choice, 0.4)], "en", tmp_path / "x.wav")
    x, sr = tts.read_wav(tmp_path / "x.wav")
    assert 1.1 in calls and abs(words[-1]["e"] - len(x) / sr) < 0.12  # last word ends with the audio
    assert words[3]["s"] >= words[2]["e"] + 0.35  # the pause before the reveal is in the timings too


# ---------------------------------------------------------------- E) speed + whole video
def test_whole_short_cold_open_end_card_timing_report(offline):
    series = project.Series.create("Viral")
    opts = project.EpisodeOptions(length="short", resolution="480p")
    rep = Reporter(echo=False)
    res = pipeline.generate(series, opts, STRONG, rep)
    ep = series.episode(1)
    tl = project.read_json(ep.audio_dir("en") / "timeline.json")
    assert tl["cold"] == 1.0 and tl["scenes"][0]["start"] == 1.0 and tl["end"]["dur"] == 1.6
    assert tl["beats"]["reveal"] and tl["beats"]["punch"]  # "That's when she realized…" + hook words
    video = res["videos"][0]
    assert abs(media.duration(video) - tl["total"]) < 0.1
    edit = project.read_json(ep.dir / "render" / "edit_en_9x16.json")
    all_cuts = [c for s in edit["scenes"] for c in s["cuts"]]
    voice = sum(s["dur"] for s in tl["scenes"])
    assert len(all_cuts) >= voice / 2.6  # a new shot about every 2 s
    pictures = {c["image"] for c in all_cuts}
    assert len(pictures) <= voice / 4  # but only about one picture per 5 s
    assert edit["cold"]["flash"] == [0.0] and edit["end"]["text"] == "PART 2"
    text = rep.text(400)
    assert "Timing report" in text and "Voice (made at the same time)" in text and "Total" in text
    result = project.read_json(ep.export_dir / "result.json")
    assert result["timings"] and any("Scene clips" in n for n, _ in result["timings"])
    # the last frame is the end card: dark background with a big white "PART 2"
    frame = ep.dir / "end.png"
    media.run_ffmpeg(["-sseof", "-0.2", "-i", video, "-frames:v", "1", frame], "grab the last frame")
    a = np.asarray(Image.open(frame).convert("L")).astype(int)
    assert (a > 230).mean() > 0.01 and np.median(a) < 90


def test_final_episode_and_no_end_card(offline):
    series = project.Series.create("Final")
    opts = project.EpisodeOptions(length="short", resolution="480p", final_episode=True, cold_open=False)
    pipeline.generate(series, opts, STRONG, Reporter(echo=False))
    ep = series.episode(1)
    edit = project.read_json(ep.dir / "render" / "edit_en_9x16.json")
    assert edit["end"]["text"] == "THE END" and edit["cold"] is None
    tl = project.read_json(ep.audio_dir("en") / "timeline.json")
    assert tl["cold"] == 0 and tl["scenes"][0]["start"] == 0.0


def test_gemini_mode_loads_no_image_model(offline, monkeypatch, tmp_path):
    from storyforge import images
    from storyforge.motion import depth

    series = project.Series.create("NoModels")
    opts = project.EpisodeOptions(length="short", resolution="480p")
    res = pipeline.gemini_prompts(series, opts, STRONG, Reporter(echo=False))
    ep = series.episode(res["episode"])
    files = []
    for n in range(res["pictures"]):
        p = tmp_path / f"{n + 1}.png"
        Image.new("RGB", (300, 520), (40 + 20 * n, 30, 90)).save(p)
        files.append(p)
    gemini.add_images(ep, files, res["pictures"])

    def boom(*a, **k):
        raise AssertionError("an image model was used")

    monkeypatch.setattr(images, "generate_batch", boom)
    monkeypatch.setattr(depth, "make_depth", boom)
    monkeypatch.setattr(depth, "_load", boom)
    o = ep.load_options()
    o.image_source = "mine"
    out = pipeline.Pipeline(series, ep, Reporter(echo=False), o).make_video()
    assert out["videos"] and not list(ep.dir.glob("scenes/*/depth_*.png"))


# ---------------------------------------------------------------- F) upload order
def test_upload_order_by_time_character_sheets_first(offline, tmp_path):
    series = project.Series.create("Order")
    res = pipeline.gemini_prompts(series, project.EpisodeOptions(length="short"), STRONG, Reporter(echo=False))
    ep = series.episode(res["episode"])
    total = res["pictures"]
    names = [f"Gemini_Generated_Image_{c * 6}.jfif" for c in "abcdefghij"[: total + 1]]
    order = list(reversed(names))  # made in reverse alphabetical order
    times = {n: 1000 + 60 * order.index(n) for n in names}
    files = []
    for n in names:
        p = tmp_path / n
        Image.new("RGB", (60, 100), (10, 10, 10)).save(p, format="JPEG")
        files.append(p)
    msgs = gemini.add_images(ep, files, total, times, n_chars=1)
    data = project.read_json(ep.dir / "my_images.json")
    assert data["characters"]["C1"] == order[0].replace(".jfif", ".png")  # the oldest = the character sheet
    assert [data["slots"][str(k)] for k in range(1, total + 1)] == [o.replace(".jfif", ".png") for o in order[1:]]
    assert any("by the time they were made" in m for m in msgs)
    # ⬆️ on scene 1 swaps it with the character sheet
    gemini.step(ep, "1", -1, total, 1)
    data2 = project.read_json(ep.dir / "my_images.json")
    assert data2["characters"]["C1"] == data["slots"]["1"] and data2["slots"]["1"] == data["characters"]["C1"]


def test_upload_order_without_times_and_numbers_win(offline, tmp_path):
    series = project.Series.create("Order2")
    res = pipeline.gemini_prompts(series, project.EpisodeOptions(length="short"), STRONG, Reporter(echo=False))
    ep = series.episode(res["episode"])
    total = res["pictures"]
    files = []
    for n in ["zz_Gemini_Generated_Image_q.png", "2.png", "Gemini_Generated_Image_a.png", "C1.png"]:
        p = tmp_path / n
        Image.new("RGB", (60, 100), (10, 10, 10)).save(p)
        files.append(p)
    msgs = gemini.add_images(ep, files, total, times=None, n_chars=1)
    data = project.read_json(ep.dir / "my_images.json")
    assert data["slots"]["2"] == "2.png" and data["characters"]["C1"] == "C1.png"  # numbers in the name win
    assert data["slots"]["1"] == "zz_Gemini_Generated_Image_q.png"  # then the order you picked them in
    assert data["slots"]["3"] == "Gemini_Generated_Image_a.png"
    assert any("order you selected" in m for m in msgs)
    assert gemini._number("IMG_20261122_1430.jpg") is None and gemini._number("download (2).png") is None
    assert gemini._number("03_taxi.png") == ("", 3) and gemini._number("scene-12.webp") == ("", 12)


def test_drive_folder_uses_drive_file_times(offline):
    series = project.Series.create("Drive")
    res = pipeline.gemini_prompts(series, project.EpisodeOptions(length="short"), STRONG, Reporter(echo=False))
    ep = series.episode(res["episode"])
    d = gemini.folder(ep)
    now = time.time()
    for k, n in enumerate(["x.jpg", "a.jpg", "m.jpg"]):  # made in this order (x oldest)
        Image.new("RGB", (60, 100), (10, 10, 10)).save(d / n)
        os.utime(d / n, (now - 300 + k * 60, now - 300 + k * 60))
    gemini.scan_folder(ep, res["pictures"], 0)
    data = project.read_json(ep.dir / "my_images.json")
    assert [data["slots"][k] for k in ("1", "2", "3")] == ["x.png", "a.png", "m.png"]
    assert (d / "originals" / "x.jpg").exists()
