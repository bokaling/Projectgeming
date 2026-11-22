"""Music and sound effects (monetization safe).

* Built-in gentle cinematic music for 10 moods (made in code: no licenses, no Content ID claims),
  lowpassed at 8 kHz so nothing sounds sharp.
* Built-in generated sound effects (whoosh, impact, riser, heartbeat, wind, rain, thunder, sting),
  all soft and lowpassed. Sound effects are OFF unless you switch them on.
* Your own music library on Drive: StoryForge/library/music/<mood>/ with licenses.csv
  (credits are added to the description automatically).
* Optional Freesound CC0 effects with a free FREESOUND_API_KEY.
* Mix: voice + music (ducked under the voice) + effects, then loudness to -14 LUFS.
"""

from __future__ import annotations

import csv
import json
import random
import re
import subprocess
import zlib
from pathlib import Path

import numpy as np

from .. import config, media, net

SR = 44100
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}

CHORDS = {"M": [0, 4, 7], "m": [0, 3, 7], "sus": [0, 2, 7], "dim": [0, 3, 6], "m7": [0, 3, 7, 10], "M7": [0, 4, 7, 11]}
# Gentle, soft cinematic beds only: warm pads, low soft piano, string swells, sub bass, muffled pulses.
# No bells, hi-hats, ticks, snares or bright arpeggios (they sounded sharp under a voice).
PRESETS = {
    # how-it-works videos: curious and steady, a soft muffled pulse that keeps things moving under the voice
    "explainer": dict(root=50, bpm=84, prog=[(0, "sus"), (5, "M"), (9, "m"), (7, "M")], layers=["pad", "sub", "pulse", "piano"], wet=0.38, cutoff=1300),
    "tense": dict(root=45, bpm=92, prog=[(0, "m"), (8, "M"), (5, "m"), (7, "M")], layers=["pad", "sub", "pulse"], wet=0.35, cutoff=1100),
    "mysterious": dict(root=50, bpm=66, prog=[(0, "m"), (1, "M"), (0, "m7"), (10, "M")], layers=["pad", "sub", "piano"], wet=0.45, cutoff=1000),
    "sad": dict(root=48, bpm=62, prog=[(0, "m"), (8, "M"), (3, "M"), (10, "M")], layers=["pad", "piano"], wet=0.45, cutoff=1200),
    "hopeful": dict(root=48, bpm=76, prog=[(0, "M"), (7, "M"), (9, "m"), (5, "M")], layers=["pad", "piano", "sub"], wet=0.4, cutoff=1600),
    "epic": dict(root=50, bpm=80, prog=[(0, "m"), (8, "M"), (3, "M"), (10, "M")], layers=["strings", "sub", "taiko"], wet=0.4, cutoff=1500),
    "calm": dict(root=53, bpm=60, prog=[(0, "M7"), (9, "m"), (5, "M"), (7, "sus")], layers=["pad", "piano"], wet=0.5, cutoff=1300),
    "dark": dict(root=47, bpm=58, prog=[(0, "m"), (1, "M"), (0, "m"), (6, "dim")], layers=["pad", "sub", "pulse"], wet=0.45, cutoff=800),
    "action": dict(root=52, bpm=104, prog=[(0, "m"), (8, "M"), (10, "M"), (7, "m")], layers=["strings", "sub", "pulse", "taiko"], wet=0.3, cutoff=1500),
    "romantic": dict(root=55, bpm=68, prog=[(0, "M"), (4, "m"), (9, "m"), (5, "M")], layers=["pad", "piano"], wet=0.5, cutoff=1400),
    "playful": dict(root=55, bpm=96, prog=[(0, "M"), (5, "M"), (7, "M"), (0, "M")], layers=["pad", "piano", "sub"], wet=0.35, cutoff=1700),
}
SFX_GAIN = {"whoosh": 0.35, "impact": 0.5, "riser": 0.3, "heartbeat": 0.5, "wind": 0.18, "rain": 0.16,
            "thunder": 0.4, "sting": 0.35, "low_whoosh": 0.17, "boom": 0.42, "soft_riser": 0.24,
            "hum": 0.12, "pour": 0.12, "bubbles": 0.14, "zap": 0.1, "click": 0.16, "pop": 0.12, "alarm_hum": 0.1,
            "rumble": 0.14, "steam": 0.07}
MUSIC_LOWPASS = 8000  # Hz: nothing sharp above this
SFX_LOWPASS = 6000
AMBIENT = {"wind", "rain"}
DESIGN_SFX = {"low_whoosh", "boom", "soft_riser", "hum", "pour", "bubbles", "zap", "click", "pop", "alarm_hum",
              "rumble", "steam"}
LOOPED = {"hum", "pour", "bubbles", "alarm_hum", "rumble", "steam"}  # last as long as the action (machines running, liquid flowing)


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


# ---------------------------------------------------------------------------
# Tiny synthesizer
# ---------------------------------------------------------------------------

_TABLE = 4096


def _wavetable(harmonics: int, rolloff: float) -> np.ndarray:
    ph = np.arange(_TABLE) / _TABLE * 2 * np.pi
    w = sum(np.sin(ph * h) * (rolloff ** (h - 1)) / h for h in range(1, harmonics + 1))
    return (w / np.abs(w).max()).astype(np.float32)


_TABLES = {"saw": _wavetable(10, 0.82), "warm": _wavetable(6, 0.6), "sine": _wavetable(1, 1.0), "soft": _wavetable(3, 0.4)}


def osc(freq: float, n: int, shape: str = "saw", phase: float = 0.0) -> np.ndarray:
    idx = ((np.arange(n) * (freq / SR) + phase) % 1.0 * _TABLE).astype(np.int32)
    return _TABLES[shape][idx]


def env(n: int, attack: float, release: float, sustain: float = 1.0) -> np.ndarray:
    e = np.full(n, sustain, np.float32)
    a, r = min(n, int(attack * SR)), min(n, int(release * SR))
    if a:
        e[:a] = np.linspace(0, sustain, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def decay(n: int, seconds: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (seconds * SR)).astype(np.float32)


def _lowpass(x: np.ndarray, hz: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt  # noqa: PLC0415

    sos = butter(2, min(hz, SR / 2 - 100), "low", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def _highpass(x: np.ndarray, hz: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt  # noqa: PLC0415

    sos = butter(2, hz, "high", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def _bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, sosfilt  # noqa: PLC0415

    sos = butter(2, [lo, min(hi, SR / 2 - 100)], "band", fs=SR, output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def _add(track: np.ndarray, start: float, sig: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
    i = int(start * SR)
    if i >= len(track) or len(sig) == 0:
        return
    sig = sig[: len(track) - i]
    if sig.ndim == 1:
        left, right = np.sqrt(0.5 * (1 - pan)), np.sqrt(0.5 * (1 + pan))
        track[i: i + len(sig), 0] += sig * gain * left * 1.41
        track[i: i + len(sig), 1] += sig * gain * right * 1.41
    else:
        track[i: i + len(sig)] += sig * gain


def kick(rng) -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 70 * np.exp(-t / 0.035)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * decay(n, 0.16)
    click = rng.normal(0, 1, n).astype(np.float32) * decay(n, 0.004) * 0.3
    return np.tanh(1.6 * (body + click)).astype(np.float32)


def taiko(rng) -> np.ndarray:
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    f = 58 + 30 * np.exp(-t / 0.05)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * decay(n, 0.3)
    skin = _lowpass(rng.normal(0, 1, n).astype(np.float32), 900) * decay(n, 0.04)
    return np.tanh(1.3 * (body + skin * 0.5)).astype(np.float32)


def pad_chord(notes: list[float], seconds: float, bright: float, rng, cutoff: float | None = None) -> np.ndarray:
    """A warm pad: detuned soft waves, filtered low, slow attack and release."""
    n = int(seconds * SR)
    out = np.zeros((n, 2), np.float32)
    for m in notes:
        for ch, det in ((0, -0.07), (1, 0.07)):
            for d in (det, det * 0.4):
                out[:, ch] += osc(midi_hz(m + d), n, "warm", rng.random()) * 0.33
    out = _lowpass(out, cutoff or (500 + 2600 * bright))
    return out * env(n, min(1.5, seconds / 3), min(1.5, seconds / 3))[:, None] / max(1, len(notes))


def _reverb(x: np.ndarray, wet: float, rng, seconds: float = 2.4) -> np.ndarray:
    from scipy.signal import fftconvolve  # noqa: PLC0415

    n = int(seconds * SR)
    ir = rng.normal(0, 1, (n, 2)).astype(np.float32) * decay(n, seconds / 5)[:, None]
    ir = _lowpass(ir, 3500)
    ir /= np.sqrt((ir**2).sum(axis=0, keepdims=True)) + 1e-9
    tail = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1).astype(np.float32)
    return x * (1 - wet) + tail * wet * 1.4


def soft_piano(freq: float, seconds: float) -> np.ndarray:
    """A soft, felt-piano-like note: few harmonics, gentle attack, slow decay."""
    n = int(seconds * SR)
    x = osc(freq, n, "sine") + 0.25 * osc(freq * 2, n, "sine") + 0.06 * osc(freq * 3, n, "sine")
    return (x * decay(n, seconds / 2.5) * env(n, 0.012, 0.3)).astype(np.float32)


def strings_chord(notes: list[float], seconds: float, cutoff: float, rng) -> np.ndarray:
    """Slow swelling strings: detuned warm waves with soft vibrato, filtered low."""
    n = int(seconds * SR)
    out = np.zeros((n, 2), np.float32)
    t = np.arange(n) / SR
    for m in notes:
        for ch, det in ((0, -0.06), (1, 0.06)):
            f = midi_hz(m + det) * (1 + 0.0025 * np.sin(2 * np.pi * 5.2 * t + rng.random() * 6))
            phase = np.cumsum(f) / SR
            out[:, ch] += _TABLES["warm"][((phase % 1.0) * _TABLE).astype(np.int32)] * 0.3
    swell = np.sin(np.pi * np.clip(t / seconds, 0, 1)) ** 1.5
    return _lowpass(out, cutoff) * swell[:, None] / max(1, len(notes))


def soft_pulse(rng) -> np.ndarray:
    """A muffled low heartbeat-like pulse (lowpassed kick)."""
    return _lowpass(kick(rng) * 0.8, 140)


def soft_taiko(rng) -> np.ndarray:
    return _lowpass(taiko(rng), 600)


def generate_music(mood: str, seconds: float, seed: int = 0) -> np.ndarray:
    """A gentle, soft cinematic bed for a mood. Stereo float32 at 44.1 kHz, nothing sharp above 8 kHz."""
    p = PRESETS.get(mood, PRESETS["mysterious"])
    rng = np.random.default_rng(seed)
    r = random.Random(seed)
    bpm = p["bpm"] * r.uniform(0.95, 1.05)
    beat = 60 / bpm
    bars_per_chord = 2 if bpm < 80 else 1
    chord_len = 4 * beat * bars_per_chord
    root = p["root"] + r.choice([0, 0, 2, -2, 3])  # a little variety between episodes
    prog = list(p["prog"])
    if r.random() < 0.4:
        prog = prog[2:] + prog[:2]
    n = int((seconds + 3) * SR)
    track = np.zeros((n, 2), np.float32)
    pulse, drum = soft_pulse(rng), soft_taiko(rng)
    cutoff = p["cutoff"]
    t, ci = 0.0, 0
    while t < seconds + 1:
        off, q = prog[ci % len(prog)]
        base = root + 12 + off  # chords sit around C3-C4: warm, never shrill
        notes = [base + iv for iv in CHORDS[q]]
        layers = p["layers"]
        if "pad" in layers:
            _add(track, t, pad_chord(notes, chord_len + 1.2, 0.0, rng, cutoff), 0.6)
        if "strings" in layers:
            _add(track, t, strings_chord(notes, chord_len + 0.8, cutoff, rng), 0.7)
        if "sub" in layers:
            ln = int(chord_len * SR)
            sub = osc(midi_hz(root - 12 + off), ln, "sine") * env(ln, 0.4, 0.6)
            _add(track, t, sub, 0.22)
        steps = int(round(chord_len / beat))
        for b in range(steps):
            bt = t + b * beat
            if "piano" in layers and (b % 2 == 0 or r.random() < 0.3):
                note = notes[(b // 2 + r.randrange(2)) % len(notes)]  # same octave as the chord: low and soft
                _add(track, bt + r.choice([0, 0.5]) * beat, soft_piano(midi_hz(note), beat * 3.5), 0.18,
                     pan=r.uniform(-0.25, 0.25))
            if "pulse" in layers and b % 2 == 0:
                _add(track, bt, pulse, 0.32)
                _add(track, bt + beat * 0.3, pulse, 0.2)
            if "taiko" in layers and b in (0, 2):
                _add(track, bt, drum, 0.3 if b == 0 else 0.18)
        t += chord_len
        ci += 1
    track = _reverb(_highpass(track, 35), p["wet"], rng)[: int(seconds * SR)]
    track = _lowpass(_lowpass(track, MUSIC_LOWPASS), MUSIC_LOWPASS)  # 4th order: no sharp highs at all
    rms = np.sqrt((track**2).mean()) + 1e-9
    peak = np.abs(track).max() + 1e-9
    track *= min(0.1 / rms, 0.7 / peak)  # about -20 dBFS, never clipping
    fade_in, fade_out = min(len(track), int(2.0 * SR)), min(len(track), int(3.0 * SR))
    track[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    track[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return np.clip(track, -1, 1).astype(np.float32)


# ---------------------------------------------------------------------------
# Generated sound effects
# ---------------------------------------------------------------------------


def _loopable(x: np.ndarray, sec: float = 0.3) -> np.ndarray:
    """Blend the end into the start, so a sound repeats without a click (machines running, liquid flowing)."""
    k = min(int(sec * SR), len(x) // 3)
    if k < 2:
        return x
    w = np.linspace(0, 1, k, dtype=np.float32)[:, None]
    out = x[:-k].copy()
    out[:k] = x[:k] * w + x[-k:] * (1 - w)
    return out


def make_sfx(name: str, seed: int = 0) -> np.ndarray:
    """Stereo float32 sound effect."""
    rng = np.random.default_rng(seed + zlib.crc32(name.encode()) % 1000)
    noise = lambda sec: rng.normal(0, 1, int(sec * SR)).astype(np.float32)  # noqa: E731
    if name == "whoosh":
        n = int(0.9 * SR)
        x = np.zeros(n, np.float32)
        for k, (lo, hi) in enumerate(((200, 900), (500, 2000), (1200, 4000))):
            peak = 0.35 + 0.12 * k
            shape = np.exp(-(((np.arange(n) / SR) - peak) / 0.16) ** 2)
            x += _bandpass(noise(0.9), lo, hi) * shape
        pan = np.linspace(-0.8, 0.8, n)
        out = np.stack([x * np.sqrt(0.5 * (1 - pan)), x * np.sqrt(0.5 * (1 + pan))], 1)
    elif name == "impact":
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 50 * np.exp(-t / 0.08)) / SR) * decay(n, 0.45)
        crack = _lowpass(noise(1.6), 3000) * decay(n, 0.05)
        x = np.tanh(2.2 * (boom + 0.6 * crack))
        out = _reverb(np.stack([x, x], 1), 0.25, rng, 1.5)
    elif name == "riser":
        n = int(2.6 * SR)
        t = np.arange(n) / SR
        sweep = np.sin(2 * np.pi * np.cumsum(110 * 2 ** (t * 0.9)) / SR) * 0.4  # rises to ~550 Hz only
        hiss = _bandpass(noise(2.6), 400, 2500) * 0.4
        x = (sweep + hiss) * (t / t[-1]) ** 2
        out = np.stack([x, x * 0.95], 1)
    elif name == "heartbeat":
        beat = kick(rng)[: int(0.3 * SR)] * 0.9
        x = np.zeros(int(1.8 * SR), np.float32)
        for st, g in ((0.0, 1.0), (0.24, 0.7), (0.9, 1.0), (1.14, 0.7)):
            i = int(st * SR)
            x[i: i + len(beat)] += _lowpass(beat, 160)[: len(x) - i] * g
        out = np.stack([x, x], 1)
    elif name == "wind":
        n = int(5 * SR)
        lfo = 0.6 + 0.4 * np.sin(np.arange(n) / SR * 2 * np.pi * 0.23)
        out = np.stack([_bandpass(noise(5), 150, 900) * lfo, _bandpass(noise(5), 150, 900) * lfo[::-1]], 1)
    elif name == "rain":
        n = int(5 * SR)
        bed = _bandpass(noise(5), 300, 2800) * 0.35
        drops = np.zeros(n, np.float32)
        for i in rng.integers(0, n - 2000, 260):
            drops[i: i + 400] += rng.normal(0, 1, 400).astype(np.float32) * decay(400, 0.002) * rng.uniform(0.2, 0.8)
        out = np.stack([bed + drops, bed + np.roll(drops, 777)], 1)
    elif name == "thunder":
        n = int(4.5 * SR)
        rumble = _lowpass(noise(4.5), 180) * decay(n, 1.3) * 3
        crack = _bandpass(noise(4.5), 600, 4000) * decay(n, 0.12)
        out = _reverb(np.stack([rumble + crack, rumble * 0.9 + crack], 1), 0.3, rng, 2.0)
    elif name == "low_whoosh":  # soft air movement on a scene change (no hiss)
        n = int(0.7 * SR)
        t = np.arange(n) / SR
        shape = np.exp(-((t - 0.3) / 0.13) ** 2)
        x = _bandpass(noise(0.7), 120, 1400) * shape
        pan = np.linspace(-0.6, 0.6, n)
        out = np.stack([x * np.sqrt(0.5 * (1 - pan)), x * np.sqrt(0.5 * (1 + pan))], 1)
        out = _lowpass(out, 2500)
    elif name == "boom":  # low cinematic hit on a reveal: felt more than heard
        n = int(2.2 * SR)
        t = np.arange(n) / SR
        sub = np.sin(2 * np.pi * np.cumsum(42 + 30 * np.exp(-t / 0.06)) / SR) * decay(n, 0.7)
        body = _lowpass(noise(2.2), 400) * decay(n, 0.12) * 0.5
        x = np.tanh(1.6 * (sub + body))
        out = _reverb(np.stack([x, x], 1), 0.3, rng, 2.0)
        out = _lowpass(out, 2500)
    elif name == "soft_riser":  # tension before the cliffhanger: rises and stops
        n = int(2.6 * SR)
        t = np.arange(n) / SR
        tone = np.sin(2 * np.pi * np.cumsum(70 * 2 ** (t * 0.75)) / SR) * 0.5
        air = _bandpass(noise(2.6), 200, 1800) * 0.35
        x = (tone + air) * (t / t[-1]) ** 2.2
        x[-int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
        out = np.stack([x, x * 0.96], 1)
        out = _lowpass(out, 3000)
    elif name == "hum":  # a machine running: low motor hum with a slow wobble (loops)
        n = int(4.0 * SR)
        t = np.arange(n) / SR
        f0 = 55.0
        x = sum(np.sin(2 * np.pi * f0 * h * t + h) / h for h in (1, 2, 3, 4, 6))
        x = x * (0.85 + 0.15 * np.sin(2 * np.pi * 0.7 * t)) + _lowpass(noise(4.0), 300) * 0.3
        out = np.stack([x, x], 1)
        out = _lowpass(out, 900)
    elif name == "rumble":  # a vehicle driving / a big engine: low, round, slowly wobbling (loops)
        n = int(4.0 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 42 * t) * (0.7 + 0.3 * np.sin(2 * np.pi * 3.5 * t)) + _lowpass(noise(4.0), 180) * 0.8
        out = _lowpass(np.stack([x, x], 1), 400)
    elif name == "steam":  # smoke or steam: soft airy hiss, kept low (no sharp highs)
        n = int(4.0 * SR)
        x = _bandpass(noise(4.0), 400, 2200) * (0.8 + 0.2 * np.sin(np.arange(n) / SR * 2 * np.pi * 0.9))
        out = np.stack([x, np.roll(x, 2200)], 1)
    elif name == "alarm_hum":  # a low warning pulse (danger), never shrill
        n = int(4.0 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 110 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.6 * t)) ** 2
        out = np.stack([x, x], 1)
        out = _lowpass(out, 600)
    elif name == "pour":  # liquid flowing through a pipe (soft, filtered noise, loops)
        n = int(4.0 * SR)
        lfo = 0.75 + 0.25 * np.sin(np.arange(n) / SR * 2 * np.pi * 1.3)
        x = _bandpass(noise(4.0), 150, 1200) * lfo
        out = np.stack([x, np.roll(x, 3000)], 1)
    elif name == "bubbles":  # low soft bloops (loops)
        n = int(4.0 * SR)
        x = np.zeros(n, np.float32)
        for st in rng.uniform(0, 3.8, 26):
            ln = int(rng.uniform(0.05, 0.12) * SR)
            tt = np.arange(ln) / SR
            f = rng.uniform(180, 420) * (1 + 3 * tt)
            i = int(st * SR)
            x[i: i + ln] += (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.03))[: n - i] * rng.uniform(0.4, 1)
        out = np.stack([x, np.roll(x, 900)], 1)
        out = _lowpass(out, 2000)
    elif name == "zap":  # electricity: a soft low crackle (no hiss)
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        x = _bandpass(noise(0.6), 200, 2500) * (np.sin(2 * np.pi * 50 * t) > 0.6) * decay(n, 0.25)
        out = np.stack([x, x], 1)
    elif name == "click":  # a light switch / relay, muffled
        n = int(0.25 * SR)
        x = _lowpass(noise(0.25), 1800) * decay(n, 0.012)
        x += np.sin(2 * np.pi * 140 * np.arange(n) / SR) * decay(n, 0.04) * 0.6
        out = np.stack([x, x], 1)
    elif name == "pop":  # something appears: a soft low pop
        n = int(0.3 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * np.cumsum(260 - 400 * t) / SR) * decay(n, 0.05)
        out = np.stack([x, x], 1)
    else:  # "sting": dark orchestral hit
        n = int(2.4 * SR)
        x = np.zeros((n, 2), np.float32)
        for m in (38, 45, 50, 51, 57):
            for ch, det in ((0, -0.1), (1, 0.1)):
                x[:, ch] += osc(midi_hz(m + det), n, "saw") * decay(n, 0.7)
        hit = make_sfx("impact", seed)[:n]
        x = _lowpass(x, 1800) * 0.3
        x[: len(hit)] += hit * 0.6
        out = _reverb(x, 0.35, rng, 2.2)
    out = _lowpass(_lowpass(out.astype(np.float32), SFX_LOWPASS), SFX_LOWPASS)  # soft, never sharp
    if name in LOOPED:
        out = _loopable(out)
    return (out / (np.abs(out).max() + 1e-9) * 0.9).astype(np.float32)


# ---------------------------------------------------------------------------
# Your own library and Freesound (optional)
# ---------------------------------------------------------------------------


def read_licenses(folder: Path) -> dict[str, dict]:
    path = folder / "licenses.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("file"):
                out[row["file"].strip()] = {k: (v or "").strip() for k, v in row.items()}
    return out


def ensure_library_readme() -> None:
    s = config.get()
    readme = s.music_dir / "README.txt"
    if readme.exists():
        return
    for mood in PRESETS:
        (s.music_dir / mood).mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "Put your own music here, in a folder named after the mood (tense, sad, epic, ...).\n"
        "Safe sources: YouTube Audio Library (YouTube only), Freesound CC0, Incompetech (CC BY, needs credit).\n"
        "Add one line per track to licenses.csv so credits go into your video descriptions automatically:\n"
        "file,title,artist,source,url,license,credit\n"
        "tense/Cipher.mp3,Cipher,Kevin MacLeod,Incompetech,https://incompetech.com,CC BY 4.0,"
        "\"Cipher\" Kevin MacLeod (incompetech.com) Licensed under Creative Commons: By Attribution 4.0\n",
        encoding="utf-8",
    )
    lic = s.music_dir / "licenses.csv"
    if not lic.exists():
        lic.write_text("file,title,artist,source,url,license,credit\n", encoding="utf-8")


def library_tracks(mood: str) -> list[Path]:
    root = config.get().music_dir
    found = []
    for folder in (root / mood, root / "any"):
        if folder.is_dir():
            found += sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
    return found


def choose_music(mood: str, seed: int, avoid: list[str] = ()) -> dict:
    """Pick a track from your library (not used in the last episodes), else generated music."""
    tracks = [t for t in library_tracks(mood) if t.name not in set(avoid)] or library_tracks(mood)
    if tracks:
        pick = random.Random(seed).choice(tracks)
        lic = read_licenses(config.get().music_dir)
        rel = str(pick.relative_to(config.get().music_dir)).replace("\\", "/")
        row = lic.get(rel) or lic.get(pick.name) or {}
        return {"kind": "library", "path": str(pick), "name": pick.name, "credit": row.get("credit", ""),
                "license": row.get("license", "")}
    return {"kind": "generated", "name": f"generated-{mood}-{seed % 1000}", "mood": mood, "seed": seed, "credit": ""}


def load_audio(path: Path) -> np.ndarray:
    """Any audio file → stereo float32 at 44.1 kHz."""
    tmp = config.get().temp_dir / f"lib_{zlib.crc32(str(path).encode())}.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    media.run_ffmpeg(["-i", path, "-vn", "-ac", 2, "-ar", SR, "-sample_fmt", "s16", tmp], "read a music file")
    import wave  # noqa: PLC0415

    with wave.open(str(tmp), "rb") as wf:
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return data.reshape(-1, 2)


def freesound_sfx(name: str) -> tuple[np.ndarray, str] | None:
    """A CC0 effect from Freesound (needs a free FREESOUND_API_KEY). Cached on Drive."""
    key = config.secret("FREESOUND_API_KEY")
    if not key:
        return None
    folder = config.get().sfx_dir / "freesound"
    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / f"{name}.json"
    audio_path = folder / f"{name}.mp3"
    try:
        if not audio_path.exists():
            res = net.request("GET", "https://freesound.org/apiv2/search/text/", timeout=30, retries=1, params={
                "query": name, "filter": 'license:"Creative Commons 0" duration:[0.3 TO 6]',
                "fields": "id,name,username,license,previews", "page_size": 5, "token": key,
            }).json().get("results", [])
            if not res:
                return None
            hit = res[0]
            net.download(hit["previews"]["preview-hq-mp3"], audio_path, params={"token": key})
            meta_path.write_text(json.dumps({"name": hit["name"], "by": hit["username"], "license": "CC0"}), encoding="utf-8")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return load_audio(audio_path), f"\"{meta.get('name', name)}\" by {meta.get('by', '?')} (Freesound, CC0)"
    except Exception:
        return None


def get_sfx(name: str, seed: int) -> tuple[np.ndarray, str]:
    """Your own sfx folder > Freesound CC0 (if key) > generated. Returns (audio, credit)."""
    own = config.get().sfx_dir / name
    if own.is_dir():
        files = sorted(p for p in own.iterdir() if p.suffix.lower() in AUDIO_EXT)
        if files:
            return load_audio(random.Random(seed).choice(files)), ""
    fs = freesound_sfx(name) if name not in DESIGN_SFX else None  # editing sounds: always our soft ones
    if fs is not None:
        return fs
    return make_sfx(name, seed), ""


# ---------------------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------------------


def duck_gain(voice: np.ndarray, depth: float = 0.75) -> np.ndarray:
    """Music volume follows the voice: quieter while someone speaks."""
    from scipy.ndimage import maximum_filter1d, uniform_filter1d  # noqa: PLC0415

    a = np.abs(voice)
    a = maximum_filter1d(a, size=int(0.05 * SR))
    a = uniform_filter1d(a, size=int(0.25 * SR))
    level = np.clip(a / 0.04, 0, 1)
    return (1 - depth * level).astype(np.float32)


def tension_envelope(total: float, reveals: list[float], hits: bool = False) -> tuple[np.ndarray, list[float]]:
    """Music volume over time: builds slowly, drops out right before each reveal, comes back on it.

    Returns (gain per sample, times of the music 'hits' when the music comes back).
    """
    n = int(total * SR)
    t = np.arange(n, dtype=np.float32) / SR
    env = (0.75 + 0.4 * (t / max(total, 1e-3))).astype(np.float32)  # tension builds over the video
    for tr in reveals:
        a, b = tr - 0.9, tr - 0.45
        fall = (t >= a) & (t < b)
        env[fall] *= np.clip((b - t[fall]) / (b - a), 0, 1)  # fade out
        env[(t >= b) & (t < tr)] = 0.0  # silence just before the reveal
        after = t >= tr
        env[after] *= 1 + 0.3 * np.exp(-(t[after] - tr) / 1.2)  # back with a lift
        rise = (t >= tr) & (t < tr + 0.03)
        env[rise] *= (t[rise] - tr) / 0.03
    return env, (list(reveals) if hits else [])


def mix(voice: np.ndarray, total: float, music: np.ndarray | None, music_volume: float,
        sfx_events: list[tuple[float, np.ndarray, float, float]], music_env: np.ndarray | None = None) -> np.ndarray:
    """voice: mono at SR. sfx_events: (time, audio, gain, max_seconds). Returns stereo float32.

    music_env: extra music volume curve (tension, drop-outs). Music and sound effects duck under the voice.
    """
    n = int(total * SR)
    out = np.zeros((n, 2), np.float32)
    v = np.zeros(n, np.float32)
    v[: min(n, len(voice))] = voice[:n]
    out += v[:, None]
    if music is not None and len(music):
        reps = int(np.ceil(n / len(music)))
        m = np.tile(music, (reps, 1))[:n] if reps > 1 else music[:n]
        if len(m) < n:
            m = np.pad(m, ((0, n - len(m)), (0, 0)))
        fade = min(n, int(1.5 * SR))
        m = m.copy()
        m[-fade:] *= np.linspace(1, 0, fade)[:, None]
        gain = duck_gain(v)
        if music_env is not None:
            e = np.ones(n, np.float32)
            e[: min(n, len(music_env))] = music_env[:n]
            gain = gain * e
        out += _lowpass(m, MUSIC_LOWPASS) * music_volume * 2.0 * gain[:, None]
    fx = np.zeros((n, 2), np.float32)
    for t, audio, gain, max_sec in sfx_events:
        if max_sec and len(audio) < int(max_sec * SR):  # loops (machines running) last as long as the action
            audio = np.tile(audio, (int(np.ceil(max_sec * SR / max(1, len(audio)))), 1))
        seg = audio[: int(max_sec * SR)] if max_sec else audio
        if max_sec and len(seg) > SR:  # soft start, fade out long sounds
            f_in = min(len(seg), int(0.15 * SR))
            seg = seg.copy()
            seg[:f_in] *= np.linspace(0, 1, f_in)[:, None]
            f = min(len(seg), int(0.6 * SR))
            seg = seg.copy()
            seg[-f:] *= np.linspace(1, 0, f)[:, None]
        _add(fx, t, seg, gain)
    out += _lowpass(fx, MUSIC_LOWPASS) * duck_gain(v, 0.45)[:, None]  # quiet under the voice
    peak = np.abs(out).max()
    if peak > 0.98:
        out *= 0.98 / peak
    return out


def write_stereo(path: Path, x: np.ndarray) -> None:
    import wave  # noqa: PLC0415

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def loudnorm(src: Path, dst: Path, target: float = -14.0) -> None:
    """Two-pass FFmpeg loudness normalization (YouTube/TikTok level)."""
    ff = config.ffmpeg_path()
    af = f"loudnorm=I={target}:TP=-2.0:LRA=11"  # 0.5 dB spare: the AAC encoder adds a little
    p1 = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af", af + ":print_format=json", "-f", "null", "-"],
                        capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr or "", re.S)
    if m:
        js = json.loads(m.group(0))
        af = (f"{af}:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:"
              f"measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    af += ",alimiter=limit=0.79:level=false"  # safety: about -2 dB here, so the final AAC file stays under -1.5 dB
    media.run_ffmpeg(["-i", src, "-af", af, "-ar", SR, "-ac", 2, "-sample_fmt", "s16", dst], "balance the loudness")
