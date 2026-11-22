"""One consistent narrator voice, gender-safe backups, character voices."""
import numpy as np
import pytest

from storyforge import characters, project
from storyforge.audio import tts
from storyforge.messages import FriendlyError


def test_backups_keep_the_same_gender():
    for lang in ("en", "fa"):
        male = tts.engine_order(lang, tts.DEFAULT_VOICE[lang])
        assert all(tts.voice_gender(e, v) == "male" for e, v in male), male
    fem = tts.engine_order("en", {"engine": "kokoro", "voice": "af_heart"})
    assert all(tts.voice_gender(e, v) == "female" for e, v in fem), fem
    assert tts.DEFAULT_VOICE["en"]["voice"].startswith("am_")  # ONE male narrator by default


def fake_engine(monkeypatch, behaviour):
    """behaviour(engine, voice, text) -> samples or raises."""
    calls = []

    def synth(eng, voice, text, lang, speed):
        calls.append((eng, voice, text))
        x = behaviour(eng, voice, text)
        return x, [(0.0, len(x) / tts.SR, w) for w in text.split()[:1]]

    monkeypatch.setattr(tts, "_synth", synth)
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    tts.reset_resolved()
    return calls


def tone(sec=0.6):
    return (0.3 * np.sin(np.arange(int(tts.SR * sec)) / tts.SR * 2 * np.pi * 180)).astype(np.float32)


def test_resolve_once_then_never_switch_mid_video(sf_root, tmp_path, monkeypatch):
    state = {"kokoro_ok": False}

    def behaviour(eng, voice, text):
        if eng == "kokoro" and not state["kokoro_ok"]:
            raise RuntimeError("kokoro broken")
        return tone()

    calls = fake_engine(monkeypatch, behaviour)
    eng, voice = tts.resolve("en", tts.DEFAULT_VOICE["en"])
    assert (eng, voice) == ("kokoro_onnx", "am_fenrir")  # the same voice from the ONNX backup, chosen once
    tts.speak("Scene one.", "en", tts.DEFAULT_VOICE["en"], tmp_path / "a.wav")
    state["kokoro_ok"] = True  # Kokoro comes back: this video still keeps the same voice
    tts.speak("Scene two.", "en", tts.DEFAULT_VOICE["en"], tmp_path / "b.wav")
    assert [c[0] for c in calls if c[2].startswith("Scene")] == ["kokoro_onnx", "kokoro_onnx"]


def test_both_kokoros_broken_falls_back_to_a_male_edge_voice(sf_root, monkeypatch):
    fake_engine(monkeypatch, lambda eng, voice, text: (_ for _ in ()).throw(RuntimeError("no")) if eng.startswith(
        "kokoro") else tone())
    assert tts.resolve("en", tts.DEFAULT_VOICE["en"]) == ("edge", "en-US-AndrewMultilingualNeural")


def test_voice_failing_in_the_middle_stops_instead_of_switching(sf_root, tmp_path, monkeypatch):
    count = {"n": 0}

    def behaviour(eng, voice, text):
        count["n"] += 1
        if count["n"] > 2:
            raise RuntimeError("network down")
        return tone()

    fake_engine(monkeypatch, behaviour)
    tts.speak("One.", "en", tts.DEFAULT_VOICE["en"], tmp_path / "a.wav")
    with pytest.raises(FriendlyError) as err:  # never a silent switch inside one scene…
        tts.speak("Two.", "en", tts.DEFAULT_VOICE["en"], tmp_path / "b.wav")
    assert isinstance(err.value, tts.VoiceFailed) and "network down" in err.value.what
    assert ("kokoro", "am_fenrir") in tts._broken  # …the pipeline then redoes the WHOLE video with the backup


def test_two_speakers_in_one_scene(sf_root, tmp_path, monkeypatch):
    fake_engine(monkeypatch, lambda e, v, t: tone(0.5))
    narr = tts.DEFAULT_VOICE["en"]
    mira = tts.parse_voice("kokoro:af_heart", "en")
    used, words = tts.speak_lines([("The radio spoke.", narr), ("Who is there?", mira)], "en", tmp_path / "s.wav")
    assert used == ["Kokoro (am_fenrir)", "Kokoro (af_heart)"]
    assert words[-1]["s"] >= 0.5  # the second speaker starts after the first + a short pause
    x, sr = tts.read_wav(tmp_path / "s.wav")
    assert abs(len(x) / sr - 1.2) < 0.05  # 0.5 + 0.2 pause + 0.5


def test_character_voices_are_different_and_remembered(sf_root):
    s = project.Series.create("Voices")
    characters.add_character(s, "Mira", "", "female")
    characters.add_character(s, "Leo", "", "male")
    characters.add_character(s, "Sam", "", "")
    narr = "kokoro:am_fenrir"
    v_mira = characters.voice_for(s, "MIRA", "en", narr)
    v_leo = characters.voice_for(s, "Leo", "en", narr)
    v_sam = characters.voice_for(s, "Sam", "en", narr)
    assert v_mira["voice"] == "af_heart" and v_leo["voice"] == "am_michael" and v_sam["voice"] == "bm_george"
    assert project.Series(s.slug).character("Leo")["voice_en"] == "kokoro:am_michael"  # saved for the series
    assert characters.voice_for(s, "Stranger", "en", narr)["voice"] == "am_fenrir"  # unknown speaker = narrator
