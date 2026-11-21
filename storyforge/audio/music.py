"""Music and sound effects (monetization safe).

* Built-in generated music beds for 10 moods (made in code: no licenses, no Content ID claims).
* Built-in generated sound effects (whoosh, impact, riser, heartbeat, wind, rain, thunder, glitch, sparkle, sting).
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
PRESETS = {
    "tense": dict(root=45, bpm=100, prog=[(0, "m"), (8, "M"), (5, "m"), (7, "M")], layers=["pad", "pulse", "ticks", "beat"], wet=0.3, bright=0.5),
    "mysterious": dict(root=50, bpm=72, prog=[(0, "m"), (1, "M"), (0, "m7"), (10, "M")], layers=["pad", "bells", "drone"], wet=0.45, bright=0.4),
    "sad": dict(root=48, bpm=66, prog=[(0, "m"), (8, "M"), (3, "M"), (10, "M")], layers=["pad", "piano"], wet=0.4, bright=0.35),
    "hopeful": dict(root=48, bpm=84, prog=[(0, "M"), (7, "M"), (9, "m"), (5, "M")], layers=["pad", "arp", "softkick"], wet=0.35, bright=0.55),
    "epic": dict(root=50, bpm=88, prog=[(0, "m"), (8, "M"), (3, "M"), (10, "M")], layers=["pad", "taiko", "octbass"], wet=0.35, bright=0.7),
    "calm": dict(root=53, bpm=64, prog=[(0, "M7"), (9, "m"), (5, "M"), (7, "sus")], layers=["pad", "piano"], wet=0.45, bright=0.35),
    "dark": dict(root=47, bpm=60, prog=[(0, "m"), (1, "M"), (0, "m"), (6, "dim")], layers=["drone", "pad", "pulse", "boom"], wet=0.4, bright=0.25),
    "action": dict(root=52, bpm=126, prog=[(0, "m"), (8, "M"), (10, "M"), (7, "m")], layers=["pad", "drive", "kick4", "snare", "hats"], wet=0.2, bright=0.6),
    "romantic": dict(root=55, bpm=72, prog=[(0, "M"), (4, "m"), (9, "m"), (5, "M")], layers=["pad", "arp"], wet=0.4, bright=0.45),
    "playful": dict(root=60, bpm=112, prog=[(0, "M"), (5, "M"), (7, "M"), (0, "M")], layers=["pluck8", "softkick", "snare", "bounce"], wet=0.2, bright=0.6),
}
SFX_GAIN = {"whoosh": 0.55, "impact": 0.8, "riser": 0.45, "heartbeat": 0.7, "wind": 0.25, "rain": 0.22,
            "thunder": 0.6, "glitch": 0.4, "sparkle": 0.35, "sting": 0.6}
AMBIENT = {"wind", "rain"}


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


def snare(rng) -> np.ndarray:
    n = int(0.3 * SR)
    noise = _bandpass(rng.normal(0, 1, n).astype(np.float32), 1200, 7000) * decay(n, 0.07)
    tone = osc(185, n, "sine") * decay(n, 0.05)
    return (noise * 1.2 + tone * 0.6).astype(np.float32)


def hat(rng, length=0.06) -> np.ndarray:
    n = int(length * 2 * SR)
    return (_highpass(rng.normal(0, 1, n).astype(np.float32), 7000) * decay(n, length / 2)).astype(np.float32)


def taiko(rng) -> np.ndarray:
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    f = 58 + 30 * np.exp(-t / 0.05)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * decay(n, 0.3)
    skin = _lowpass(rng.normal(0, 1, n).astype(np.float32), 900) * decay(n, 0.04)
    return np.tanh(1.3 * (body + skin * 0.5)).astype(np.float32)


def pluck(freq: float, seconds: float, shape="warm") -> np.ndarray:
    n = int(seconds * SR)
    return (osc(freq, n, shape) * decay(n, seconds / 3) * env(n, 0.004, 0.05)).astype(np.float32)


def bell(freq: float, seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    out = np.zeros(n, np.float32)
    for ratio, amp, dec in ((1, 1, 1.0), (2.76, 0.45, 0.5), (5.4, 0.25, 0.3), (8.93, 0.12, 0.15)):
        out += osc(freq * ratio, n, "sine") * amp * decay(n, seconds * dec / 2)
    return out * env(n, 0.002, 0.05)


def pad_chord(notes: list[float], seconds: float, bright: float, rng) -> np.ndarray:
    n = int(seconds * SR)
    out = np.zeros((n, 2), np.float32)
    for m in notes:
        for ch, det in ((0, -0.07), (1, 0.07)):
            for d in (det, det * 0.4):
                out[:, ch] += osc(midi_hz(m + d), n, "saw", rng.random()) * 0.33
    out = _lowpass(out, 500 + 2600 * bright)
    return out * env(n, min(0.8, seconds / 3), min(0.9, seconds / 3))[:, None] / max(1, len(notes))


def _reverb(x: np.ndarray, wet: float, rng, seconds: float = 2.4) -> np.ndarray:
    from scipy.signal import fftconvolve  # noqa: PLC0415

    n = int(seconds * SR)
    ir = rng.normal(0, 1, (n, 2)).astype(np.float32) * decay(n, seconds / 5)[:, None]
    ir = _lowpass(ir, 5000)
    ir /= np.sqrt((ir**2).sum(axis=0, keepdims=True)) + 1e-9
    tail = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1).astype(np.float32)
    return x * (1 - wet) + tail * wet * 1.4


def generate_music(mood: str, seconds: float, seed: int = 0) -> np.ndarray:
    """A loopable background bed for a mood. Stereo float32 at 44.1 kHz."""
    p = PRESETS.get(mood, PRESETS["tense"])
    rng = np.random.default_rng(seed)
    r = random.Random(seed)
    bpm = p["bpm"] * r.uniform(0.95, 1.05)
    beat = 60 / bpm
    bars_per_chord = 2 if bpm < 75 else 1
    chord_len = 4 * beat * bars_per_chord
    root = p["root"] + r.choice([0, 0, 2, -2, 3])  # a little variety between episodes
    prog = list(p["prog"])
    if r.random() < 0.4:
        prog = prog[2:] + prog[:2]
    n = int((seconds + 3) * SR)
    track = np.zeros((n, 2), np.float32)
    k_kick, k_snare = kick(rng), snare(rng)
    t, ci = 0.0, 0
    while t < seconds + 1:
        off, q = prog[ci % len(prog)]
        base = root + 12 + off
        notes = [base + iv for iv in CHORDS[q]]
        layers = p["layers"]
        if "pad" in layers:
            _add(track, t, pad_chord(notes, chord_len + 0.6, p["bright"], rng), 0.55)
        if "drone" in layers:
            ln = int(chord_len * SR)
            d = osc(midi_hz(root - 12), ln, "soft") * 0.5 + osc(midi_hz(root - 5), ln, "sine") * 0.25
            _add(track, t, d * env(ln, 0.3, 0.3), 0.35)
        steps = int(round(chord_len / beat))
        for b in range(steps):
            bt = t + b * beat
            if "pulse" in layers:
                for e8 in (0, 0.5):
                    _add(track, bt + e8 * beat, pluck(midi_hz(root + off), beat * 0.45, "warm"), 0.28)
            if "drive" in layers:
                for s16 in range(4):
                    _add(track, bt + s16 * beat / 4, pluck(midi_hz(root + off), beat * 0.22, "saw"), 0.18)
            if "octbass" in layers and b % 2 == 0:
                _add(track, bt, pluck(midi_hz(root + off - 12), beat * 1.8, "warm"), 0.4)
            if "bounce" in layers:
                _add(track, bt, pluck(midi_hz(root + off), beat * 0.3, "warm"), 0.3)
            if "arp" in layers:
                for e8 in (0, 0.5):
                    note = notes[(b * 2 + int(e8 * 2)) % len(notes)] + 12
                    _add(track, bt + e8 * beat, pluck(midi_hz(note), beat * 1.2), 0.16, pan=r.uniform(-0.4, 0.4))
            if "pluck8" in layers:
                for e8 in (0, 0.5):
                    _add(track, bt + e8 * beat, pluck(midi_hz(r.choice(notes) + 12), beat * 0.35, "soft"), 0.22, pan=r.uniform(-0.5, 0.5))
            if "piano" in layers:
                note = notes[b % len(notes)] + (12 if b % 4 == 3 else 0)
                _add(track, bt, pluck(midi_hz(note), beat * 3, "soft"), 0.25, pan=r.uniform(-0.3, 0.3))
            if "bells" in layers and r.random() < 0.35:
                _add(track, bt + r.choice([0, 0.5]) * beat, bell(midi_hz(r.choice(notes) + 24), 3.0), 0.12, pan=r.uniform(-0.6, 0.6))
            if "ticks" in layers:
                for s16 in range(4):
                    _add(track, bt + s16 * beat / 4, hat(rng, 0.03), 0.06 if s16 else 0.1, pan=0.3)
            if "hats" in layers:
                _add(track, bt + beat / 2, hat(rng), 0.12, pan=-0.2)
            if "beat" in layers and b % 2 == 0:
                _add(track, bt, k_kick, 0.45)
                _add(track, bt + beat * 0.28, k_kick, 0.3)
            if "kick4" in layers:
                _add(track, bt, k_kick, 0.55)
            if "softkick" in layers and b % 2 == 0:
                _add(track, bt, k_kick, 0.3)
            if "snare" in layers and b % 2 == 1:
                _add(track, bt, k_snare, 0.3)
            if "taiko" in layers and b in (0, 2, 3):
                _add(track, bt, taiko(rng), 0.5 if b == 0 else 0.32)
        if "boom" in layers and ci % 2 == 0:
            _add(track, t, make_sfx("impact", seed + ci)[:, 0], 0.25)
        t += chord_len
        ci += 1
    track = _reverb(_highpass(track, 35), p["wet"], rng)[: int(seconds * SR)]
    rms = np.sqrt((track**2).mean()) + 1e-9
    peak = np.abs(track).max() + 1e-9
    track *= min(0.12 / rms, 0.85 / peak)  # about -18 dBFS, never clipping
    fade_in, fade_out = min(len(track), int(1.0 * SR)), min(len(track), int(2.5 * SR))
    track[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    track[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return np.clip(track, -1, 1).astype(np.float32)


# ---------------------------------------------------------------------------
# Generated sound effects
# ---------------------------------------------------------------------------


def make_sfx(name: str, seed: int = 0) -> np.ndarray:
    """Stereo float32 sound effect."""
    rng = np.random.default_rng(seed + zlib.crc32(name.encode()) % 1000)
    noise = lambda sec: rng.normal(0, 1, int(sec * SR)).astype(np.float32)  # noqa: E731
    if name == "whoosh":
        n = int(0.9 * SR)
        x = np.zeros(n, np.float32)
        for k, (lo, hi) in enumerate(((300, 1200), (800, 3000), (2000, 7000))):
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
        sweep = np.sin(2 * np.pi * np.cumsum(180 * 2 ** (t * 1.4)) / SR) * 0.4
        hiss = _highpass(noise(2.6), 1500) * 0.5
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
        bed = _highpass(noise(5), 2500) * 0.35
        drops = np.zeros(n, np.float32)
        for i in rng.integers(0, n - 2000, 260):
            drops[i: i + 400] += rng.normal(0, 1, 400).astype(np.float32) * decay(400, 0.002) * rng.uniform(0.2, 0.8)
        out = np.stack([bed + drops, bed + np.roll(drops, 777)], 1)
    elif name == "thunder":
        n = int(4.5 * SR)
        rumble = _lowpass(noise(4.5), 180) * decay(n, 1.3) * 3
        crack = _bandpass(noise(4.5), 600, 4000) * decay(n, 0.12)
        out = _reverb(np.stack([rumble + crack, rumble * 0.9 + crack], 1), 0.3, rng, 2.0)
    elif name == "glitch":
        n = int(0.7 * SR)
        x = np.zeros(n, np.float32)
        for st in np.sort(rng.uniform(0, 0.6, 7)):
            i, ln = int(st * SR), int(rng.uniform(0.02, 0.07) * SR)
            seg = np.sign(osc(rng.uniform(200, 1800), ln, "sine")) * 0.5 + rng.normal(0, 0.3, ln)
            x[i: i + ln] += seg[: n - i].astype(np.float32)
        out = np.stack([x, np.roll(x, 300)], 1)
    elif name == "sparkle":
        n = int(1.6 * SR)
        x = np.zeros(n, np.float32)
        for k, m in enumerate((84, 88, 91, 96, 100)):
            b = bell(midi_hz(m), 1.2)
            i = int(k * 0.07 * SR)
            x[i: i + len(b)] += b[: n - i] * 0.5
        out = _reverb(np.stack([x, x], 1), 0.4, rng, 1.5)
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
    out = out.astype(np.float32)
    return out / (np.abs(out).max() + 1e-9) * 0.9


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
    fs = freesound_sfx(name)
    if fs is not None:
        return fs
    return make_sfx(name, seed), ""


# ---------------------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------------------


def duck_gain(voice: np.ndarray, depth: float = 0.6) -> np.ndarray:
    """Music volume follows the voice: quieter while someone speaks."""
    from scipy.ndimage import maximum_filter1d, uniform_filter1d  # noqa: PLC0415

    a = np.abs(voice)
    a = maximum_filter1d(a, size=int(0.05 * SR))
    a = uniform_filter1d(a, size=int(0.25 * SR))
    level = np.clip(a / 0.04, 0, 1)
    return (1 - depth * level).astype(np.float32)


def mix(voice: np.ndarray, total: float, music: np.ndarray | None, music_volume: float,
        sfx_events: list[tuple[float, np.ndarray, float, float]]) -> np.ndarray:
    """voice: mono at SR. sfx_events: (time, audio, gain, max_seconds). Returns stereo float32."""
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
        out += m * music_volume * 2.2 * duck_gain(v)[:, None]
    for t, audio, gain, max_sec in sfx_events:
        seg = audio[: int(max_sec * SR)] if max_sec else audio
        if max_sec and len(seg) > SR:  # fade out long ambience
            f = min(len(seg), int(0.6 * SR))
            seg = seg.copy()
            seg[-f:] *= np.linspace(1, 0, f)[:, None]
        _add(out, t, seg, gain)
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
    af = f"loudnorm=I={target}:TP=-1.5:LRA=11"
    p1 = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af", af + ":print_format=json", "-f", "null", "-"],
                        capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr or "", re.S)
    if m:
        js = json.loads(m.group(0))
        af = (f"{af}:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:"
              f"measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    media.run_ffmpeg(["-i", src, "-af", af, "-ar", SR, "-ac", 2, "-sample_fmt", "s16", dst], "balance the loudness")
