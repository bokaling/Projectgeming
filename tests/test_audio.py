import shutil

import numpy as np
import pytest

from storyforge import media
from storyforge.audio import align, music, tts

needs_espeak = pytest.mark.skipif(not shutil.which("espeak-ng"), reason="espeak-ng not installed")


def test_split_words_keeps_punctuation_and_fixes_arabic_letters():
    assert align.split_words("Run.  Now!") == ["Run.", "Now!"]
    assert align.split_words("كتاب علي") == ["کتاب", "علی"]
    assert align.core("Hello,") == "hello" and align.core("می‌روم.") == "میروم"


def test_proportional_covers_span_in_order():
    w = align.proportional(["A", "longer", "sentence."], 1.0, 3.0)
    assert w[0]["s"] == 1.0 and w[-1]["e"] == 3.0
    assert all(a["e"] <= b["s"] + 1e-6 for a, b in zip(w, w[1:]))
    assert (w[1]["e"] - w[1]["s"]) > (w[0]["e"] - w[0]["s"])  # longer word, longer time


def test_map_engine_timings_onto_script_words():
    script = ["It's", "2026,", "and", "Mira", "runs!"]
    engine = [(0.0, 0.3, "It's"), (0.3, 0.6, "twenty"), (0.6, 0.9, "twenty-six"), (1.0, 1.2, "and"),
              (1.2, 1.5, "Mira"), (1.5, 1.9, "runs")]
    out = align.map_timings(script, engine, 2.0)
    assert [o["w"] for o in out] == script
    assert out[3]["s"] == 1.2 and out[4]["e"] == 1.9
    assert out[1]["s"] >= 0.3 and out[1]["e"] <= 1.0  # "2026," gets the "twenty twenty-six" span


def test_ctc_viterbi_finds_tokens():
    # 3 tokens (ids 1,2,3) clearly spoken at frames 2-3, 6, 9-10; blank = 0
    T, V = 12, 4
    lp = np.full((T, V), -8.0)
    lp[:, 0] = -0.1
    for f, tok in ((2, 1), (3, 1), (6, 2), (9, 3), (10, 3)):
        lp[f, tok], lp[f, 0] = -0.05, -6
    spans = align.ctc_viterbi(lp, [1, 2, 3], blank=0)
    assert spans == [(2, 3), (6, 6), (9, 10)]


def test_snap_to_silence_finds_the_gap():
    sr = 16000
    x = np.concatenate([np.random.default_rng(0).normal(0, 0.3, sr), np.zeros(sr // 4), np.random.default_rng(1).normal(0, 0.3, sr)])
    cut = align.snap_to_silence(x, sr, 0.9, window=0.5)
    assert 1.0 <= cut <= 1.25


def _high_energy_db(x, hz):
    x = x.mean(axis=1) if x.ndim == 2 else x
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / music.SR)
    return 10 * np.log10(spec[f > hz].sum() / spec.sum() + 1e-15)


def test_music_generated_for_each_mood_without_clipping():
    for mood in music.PRESETS:
        x = music.generate_music(mood, 6, seed=1)
        assert x.shape == (6 * music.SR, 2) and np.abs(x).max() <= 0.71 and np.sqrt((x**2).mean()) > 0.02


def test_music_is_gentle_no_sharp_highs():
    """Regression for "the mix hurts my ears": almost no energy above 4 kHz, none above 8 kHz."""
    for mood in music.PRESETS:
        x = music.generate_music(mood, 12, seed=2)
        assert _high_energy_db(x, 4000) < -55, mood
        assert _high_energy_db(x, 8000) < -75, mood
    for name in music.SFX_GAIN:
        assert _high_energy_db(music.make_sfx(name, 3), 8000) < -28, name


def test_each_sfx_is_valid():
    for name in music.SFX_GAIN:
        y = music.make_sfx(name, 2)
        assert y.ndim == 2 and y.shape[1] == 2 and not np.isnan(y).any() and 0.5 < np.abs(y).max() <= 0.91


def test_music_choice_prefers_library_with_credit(sf_root):
    from storyforge import config

    music.ensure_library_readme()
    assert music.choose_music("tense", 1)["kind"] == "generated"
    track = config.get().music_dir / "tense" / "song.wav"
    music.write_stereo(track, music.generate_music("tense", 2, 1))
    with open(config.get().music_dir / "licenses.csv", "a", encoding="utf-8") as f:
        f.write('tense/song.wav,Song,Me,mine,,CC0,"Song by Me"\n')
    pick = music.choose_music("tense", 1)
    assert pick["kind"] == "library" and pick["credit"] == "Song by Me"
    assert music.load_audio(track).shape[1] == 2


def test_mix_ducks_music_under_voice_and_loudnorm(sf_root, tmp_path):
    sr = music.SR
    voice = np.zeros(sr * 4, np.float32)
    voice[sr: sr * 2] = 0.3 * np.sin(np.arange(sr) / sr * 2 * np.pi * 220)
    bed = np.full((sr * 2, 2), 0.1, np.float32)
    out = music.mix(voice, 4.0, bed, 0.2, [(3.0, music.make_sfx("whoosh"), 0.5, 0)])
    assert out.shape == (sr * 4, 2)
    quiet = np.abs(out[int(0.3 * sr): int(0.6 * sr)]).mean()
    during = np.abs(out[int(1.3 * sr): int(1.6 * sr)] - voice[int(1.3 * sr): int(1.6 * sr), None]).mean()
    assert during < quiet * 0.7  # music is ducked while the voice speaks
    src, dst = tmp_path / "m.wav", tmp_path / "n.wav"
    music.write_stereo(src, out)
    music.loudnorm(src, dst)
    assert abs(media.duration(dst) - 4.0) < 0.1


@needs_espeak
@pytest.mark.parametrize("lang,text", [("en", "The radio woke up at midnight. Nobody touched it."),
                                       ("fa", "رادیو نیمه شب روشن شد. هیچ‌کس به آن دست نزد.")])
def test_speak_falls_back_to_espeak_offline(sf_root, tmp_path, monkeypatch, lang, text):
    def broken(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(tts, "kokoro", broken)
    monkeypatch.setattr(tts, "edge", broken)
    monkeypatch.setattr(tts, "piper", broken)
    out = tmp_path / f"{lang}.wav"
    engine, words = tts.speak(text, lang, tts.DEFAULT_VOICE[lang], out)
    assert engine.startswith("espeak")
    assert [w["w"] for w in words] == align.split_words(text)
    total = media.duration(out)
    assert total > 1.0 and words[-1]["e"] <= total + 0.05 and words[0]["s"] < 0.5


@needs_espeak
def test_own_recording_split_into_scenes(sf_root, tmp_path):
    texts = ["Mira opened the door.", "The hallway was empty and cold.", "Then the lights went out."]
    parts = []
    for i, t in enumerate(texts):
        p = tmp_path / f"p{i}.wav"
        tts.espeak(t, "en")  # warm up
        x, _ = tts.espeak(t, "en")
        parts += [x, np.zeros(int(tts.SR * 0.6), np.float32)]
    full = np.concatenate(parts)
    rec = tmp_path / "own_voice.wav"
    tts.write_wav(rec, full)
    method, scenes = tts.split_own_recording(rec, texts, "en", tmp_path / "out")
    assert len(scenes) == 3
    lengths = [media.duration(w) for w, _ in scenes]
    assert all(0.8 < d < 4.0 for d in lengths), lengths
    assert scenes[1][1][0]["w"] == "The" and scenes[2][1][-1]["w"] == "out."


def test_voice_choices_and_engine_order():
    labels = [v for _, v in tts.voice_choices("fa")]
    assert "edge:fa-IR-FaridNeural" in labels and not any(v.startswith("kokoro") for v in labels)
    order = tts.engine_order("en", {"engine": "edge", "voice": "en-GB-RyanNeural"})
    assert order[0] == ("edge", "en-GB-RyanNeural") and order[-1][0] == "espeak"
    assert tts.engine_order("fa", {"engine": "kokoro", "voice": "x"})[0][0] == "edge"  # Kokoro has no Farsi
