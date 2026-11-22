"""Script doctor, keyword/pop captions, end card, sound design, narrator speed (kept from update 4)."""
import json
import os
import time

import numpy as np
import pytest
from PIL import Image

from storyforge import beats, captions, doctor, paste, pipeline, project, publish
from storyforge.audio import align, music, tts
from storyforge.messages import Reporter

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
def test_auto_mood_lock_and_hook_text():
    lock = beats.auto_mood_lock("At midnight the rain hit the lab windows. The radio glowed.", "dark")
    assert lock.startswith("night, heavy rain, lab") and "horror" in lock
    assert beats.hook_text("At exactly three in the morning, the radio in the old taxi turned itself on for no reason.") \
        .endswith("…")
    assert beats.hook_text("Nobody touched the radio.") == "Nobody touched the radio."


# ---------------------------------------------------------------- C) editing
def _words(text, start=0.0, total=6.0):
    return align.proportional(align.split_words(text), start, start + total)


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


