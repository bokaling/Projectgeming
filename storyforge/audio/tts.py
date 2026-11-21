"""Text to speech with word timings.

English: Kokoro (Apache 2.0, runs on CPU or GPU) → Edge TTS → Piper → espeak-ng.
Farsi:   Edge TTS fa-IR (natural, but Microsoft gives no commercial grant) → Piper fa_IR → espeak-ng.
Best for Farsi and for monetization: record your own voice and upload it.

Every engine writes a 44.1 kHz mono WAV and returns word timings for the
script words (see align.py).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import shutil
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

from .. import config, media
from ..messages import FriendlyError
from . import align

SR = 44100

KOKORO_VOICES = {
    "af_heart": "Heart (US woman, warm)", "af_bella": "Bella (US woman)", "af_nicole": "Nicole (US woman, soft)",
    "bf_emma": "Emma (UK woman)", "am_michael": "Michael (US man)", "am_fenrir": "Fenrir (US man, deep)",
    "am_puck": "Puck (US man, lively)", "bm_george": "George (UK man)", "bm_fable": "Fable (UK man, storyteller)",
}
EDGE_VOICES = {
    "en": {"en-US-AndrewMultilingualNeural": "Andrew (US man)", "en-US-AvaMultilingualNeural": "Ava (US woman)",
           "en-US-GuyNeural": "Guy (US man)", "en-GB-RyanNeural": "Ryan (UK man)", "en-GB-SoniaNeural": "Sonia (UK woman)"},
    "fa": {"fa-IR-FaridNeural": "Farid (man)", "fa-IR-DilaraNeural": "Dilara (woman)"},
}
PIPER_VOICES = {
    "en": {"en_US-ryan-high": "en/en_US/ryan/high", "en_GB-alan-medium": "en/en_GB/alan/medium",
           "en_US-lessac-medium": "en/en_US/lessac/medium"},
    "fa": {"fa_IR-amir-medium": "fa/fa_IR/amir/medium", "fa_IR-gyro-medium": "fa/fa_IR/gyro/medium"},
}
FEMALE = {"en-US-AvaMultilingualNeural", "en-GB-SoniaNeural", "fa-IR-DilaraNeural", "en_US-lessac-medium"}
# Backups keep the same gender, so a video never switches from a man's voice to a woman's.
FALLBACKS = {
    ("en", "male"): [("kokoro", "am_fenrir"), ("edge", "en-US-AndrewMultilingualNeural"), ("piper", "en_US-ryan-high")],
    ("en", "female"): [("kokoro", "af_heart"), ("edge", "en-US-AvaMultilingualNeural"), ("piper", "en_US-lessac-medium")],
    ("fa", "male"): [("edge", "fa-IR-FaridNeural"), ("piper", "fa_IR-amir-medium")],
    ("fa", "female"): [("edge", "fa-IR-DilaraNeural")],
}
# Voices for characters who speak (narrator voice is never reused for them when possible)
CHARACTER_POOL = {
    ("en", "male"): ["kokoro:am_michael", "kokoro:bm_george", "kokoro:am_puck", "kokoro:bm_fable", "kokoro:am_fenrir"],
    ("en", "female"): ["kokoro:af_heart", "kokoro:af_bella", "kokoro:bf_emma", "kokoro:af_nicole"],
    ("fa", "male"): ["piper:fa_IR-amir-medium", "piper:fa_IR-gyro-medium", "edge:fa-IR-FaridNeural"],
    ("fa", "female"): ["edge:fa-IR-DilaraNeural"],
}
DEFAULT_VOICE = {
    "en": {"engine": "kokoro", "voice": "am_fenrir", "speed": 1.0},
    "fa": {"engine": "edge", "voice": "fa-IR-FaridNeural", "speed": 1.0},
}
EDGE_WARNING = (
    "Edge TTS is free but Microsoft has not published a commercial license for these voices. "
    "For monetized videos, recording your own voice is the safest choice."
)


def voice_choices(lang: str, own: bool = True) -> list[tuple[str, str]]:
    """(label, value) pairs for the voice dropdown. value = 'engine:voice'. Men first."""
    out = []
    if lang == "en":
        items = sorted(KOKORO_VOICES.items(), key=lambda kv: kv[0][1] != "m")
        out += [(f"⭐ {v} · Kokoro", f"kokoro:{k}") for k, v in items]
    out += [(f"{v} · Edge (online)", f"edge:{k}") for k, v in EDGE_VOICES[lang].items()]
    out += [(f"{k} ({voice_gender('piper', k)}) · Piper (offline)", f"piper:{k}") for k in PIPER_VOICES[lang]]
    if own:
        out.append(("🎙️ My own recording (upload)", "own:own"))
    return out


def parse_voice(value: str | dict | None, lang: str) -> dict:
    if isinstance(value, dict):
        return {**DEFAULT_VOICE[lang], **value}
    if value and ":" in value:
        engine, voice = value.split(":", 1)
        return {"engine": engine, "voice": voice, "speed": 1.0}
    return dict(DEFAULT_VOICE[lang])


# ---------------------------------------------------------------------------
# WAV helpers
# ---------------------------------------------------------------------------


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr, n, ch, sw = wf.getframerate(), wf.getnframes(), wf.getnchannels(), wf.getsampwidth()
        raw = wf.readframes(n)
    if sw != 2:
        raise ValueError("expected 16-bit wav")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    tmp = path.with_name(path.stem + ".part.wav")
    with wave.open(str(tmp), "wb") as wf:
        wf.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    tmp.replace(path)


def to_wav(src: Path, dst: Path, sr: int = SR) -> None:
    """Any audio file → mono 16-bit WAV at `sr`."""
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    media.run_ffmpeg(["-i", src, "-vn", "-ac", 1, "-ar", sr, "-sample_fmt", "s16", dst], "read the audio file")


def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return x.astype(np.float32)
    from scipy.signal import resample_poly  # noqa: PLC0415

    g = np.gcd(SR, sr)
    return resample_poly(x, SR // g, sr // g).astype(np.float32)


def trim_silence(x: np.ndarray, sr: int, keep: float = 0.05) -> tuple[np.ndarray, float]:
    """Cut silence at both ends. Returns (audio, seconds removed at the start)."""
    s, e = align.speech_bounds(x, sr, -45)
    a = max(0, int((s - keep) * sr))
    b = min(len(x), int((e + keep) * sr))
    if b <= a:
        return x, 0.0
    return x[a:b], a / sr


# ---------------------------------------------------------------------------
# Engines (each returns (samples at SR, engine word timings [(s, e, text)]))
# ---------------------------------------------------------------------------

_kokoro: dict = {}


def kokoro(text: str, voice: str, speed: float = 1.0):
    import torch  # noqa: PLC0415
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from kokoro import KModel, KPipeline  # noqa: PLC0415

    s = config.get()
    repo, cache = config.MODELS["kokoro"], s.model_cache("kokoro")
    lang_code = "b" if voice.startswith("b") else "a"
    if "model" not in _kokoro:
        cfg = hf_hub_download(repo, "config.json", cache_dir=cache)
        weights = hf_hub_download(repo, "kokoro-v1_0.pth", cache_dir=cache)
        _kokoro["model"] = KModel(repo_id=repo, config=cfg, model=weights).to("cuda" if s.gpu.available else "cpu").eval()
    if lang_code not in _kokoro:
        _kokoro[lang_code] = KPipeline(lang_code=lang_code, repo_id=repo, model=_kokoro["model"])
    voice_file = hf_hub_download(repo, f"voices/{voice}.pt", cache_dir=cache)
    chunks, words, offset = [], [], 0.0
    with torch.no_grad():
        for result in _kokoro[lang_code](text, voice=voice_file, speed=speed):
            audio = result.audio
            if audio is None:
                continue
            audio = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            for tk in getattr(result, "tokens", None) or []:
                if tk.start_ts is not None and tk.end_ts is not None:
                    words.append((offset + tk.start_ts, offset + tk.end_ts, tk.text))
            chunks.append(audio)
            offset += len(audio) / 24000
    if not chunks:
        raise RuntimeError("Kokoro returned no audio")
    return _resample(np.concatenate(chunks), 24000), words


def _run_async(coro):
    """Run async code from any thread (Colab already has an event loop in the main thread)."""
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result(timeout=300)


def edge(text: str, voice: str, speed: float = 1.0):
    import edge_tts  # noqa: PLC0415

    rate = f"{int(round((speed - 1) * 100)):+d}%"

    async def go():
        try:
            comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        except TypeError:  # older edge-tts: word boundaries are the default
            comm = edge_tts.Communicate(text, voice, rate=rate)
        audio, words = bytearray(), []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                st = chunk["offset"] / 1e7
                words.append((st, st + chunk["duration"] / 1e7, chunk["text"]))
        return bytes(audio), words

    data, words = _run_async(go())
    if not data:
        raise RuntimeError("Edge TTS returned no audio")
    tmp_dir = config.get().temp_dir
    mp3, wav = tmp_dir / "edge.mp3", tmp_dir / "edge.wav"
    mp3.write_bytes(data)
    to_wav(mp3, wav)
    x, sr = read_wav(wav)
    return _resample(x, sr), words


_piper: dict = {}


def piper(text: str, voice: str, lang: str, speed: float = 1.0):
    from huggingface_hub import hf_hub_download  # noqa: PLC0415
    from piper import PiperVoice  # noqa: PLC0415

    if voice not in _piper:
        folder = PIPER_VOICES[lang].get(voice) or next(iter(PIPER_VOICES[lang].values()))
        name = folder.split("/")[1] + "-" + folder.split("/")[2] + "-" + folder.split("/")[3]
        cache = config.get().model_cache("piper_voices")
        onnx = hf_hub_download(config.MODELS["piper_voices"], f"{folder}/{name}.onnx", cache_dir=cache)
        hf_hub_download(config.MODELS["piper_voices"], f"{folder}/{name}.onnx.json", cache_dir=cache)
        _piper[voice] = PiperVoice.load(onnx)
    v = _piper[voice]
    out = config.get().temp_dir / "piper.wav"
    with wave.open(str(out), "wb") as wf:
        if hasattr(v, "synthesize_wav"):
            v.synthesize_wav(text, wf)
        else:  # piper-tts < 1.3
            v.synthesize(text, wf, length_scale=1.0 / max(speed, 0.5))
    x, sr = read_wav(out)
    return _resample(x, sr), []


def espeak(text: str, lang: str, speed: float = 1.0, variant: str = "m3"):
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng is not installed")
    out = config.get().temp_dir / "espeak.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    v = ("fa" if lang == "fa" else "en-us") + ("+f3" if variant == "f3" else "+m3")
    subprocess.run([exe, "-v", v, "-s", str(int(150 * speed)), "-w", str(out), text],
                   check=True, capture_output=True, timeout=120)
    tmp = out.with_name("espeak16.wav")
    to_wav(out, tmp)
    x, sr = read_wav(tmp)
    return _resample(x, sr), []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def voice_gender(engine: str, voice: str) -> str:
    if engine == "kokoro":
        return "female" if voice[:2] in ("af", "bf") else "male"
    if engine == "espeak":
        return "female" if voice.endswith("f3") else "male"
    return "female" if voice in FEMALE else "male"


def engine_order(lang: str, choice: dict) -> list[tuple[str, str]]:
    """Engines to try, starting with the user's choice; backups have the same gender."""
    order = []
    eng, voice = choice.get("engine"), choice.get("voice")
    gender = voice_gender(eng or "", voice or "") if eng in ("kokoro", "edge", "piper") else "male"
    if eng in ("kokoro", "edge", "piper") and not (eng == "kokoro" and lang != "en"):
        order.append((eng, voice))
    for d in FALLBACKS[(lang, gender)]:
        if d[0] not in [o[0] for o in order]:
            order.append(d)
    order.append(("espeak", "f3" if gender == "female" else "m3"))
    return order


_resolved: dict = {}


def reset_resolved() -> None:
    """Forget engine choices (at the start of each voice step, a voice that is back online is used again)."""
    _resolved.clear()


def resolve(lang: str, choice: dict, rep=None) -> tuple[str, str]:
    """Find ONE engine that works for this voice and remember it (the whole video uses it)."""
    key = (lang, choice.get("engine"), choice.get("voice"))
    if key in _resolved:
        return _resolved[key]
    test = "آماده." if lang == "fa" else "Ready."
    errors = []
    for eng, voice in engine_order(lang, choice):
        try:
            _synth(eng, voice, test, lang, 1.0)
            _resolved[key] = (eng, voice)
            if errors and rep is not None:
                rep.warn(f"Your chosen voice isn't available right now, so the whole video uses "
                         f"{ENGINE_NAMES[eng]} ({voice}) instead.")
            return eng, voice
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{ENGINE_NAMES[eng]}: {str(exc)[:80]}")
    raise FriendlyError("No voice engine worked.", "Check the internet, run the Setup cell again, or upload your own recording.")


def _synth(eng: str, voice: str, text: str, lang: str, speed: float):
    if eng == "kokoro":
        return kokoro(text, voice, speed)
    if eng == "edge":
        return edge(text, voice, speed)
    if eng == "piper":
        return piper(text, voice, lang, speed)
    return espeak(text, lang, speed, variant=voice)


ENGINE_NAMES = {"kokoro": "Kokoro", "edge": "Edge TTS", "piper": "Piper", "espeak": "espeak-ng (robotic, emergency)"}


def _speak_samples(text: str, lang: str, eng: str, voice: str, speed: float, retries: int = 3):
    """Speak with exactly this engine (a few retries, never a different voice). Returns (samples, words)."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            x, ew = _synth(eng, voice, text, lang, speed)
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 + attempt * 4)
    else:
        raise FriendlyError(f"The voice ({ENGINE_NAMES[eng]}) stopped working in the middle.",
                            "Press Generate again in a minute: finished scenes are kept and the same voice continues.") from last
    x, cut = trim_silence(x, SR)
    ew = [(s - cut, e - cut, t) for s, e, t in ew]
    total = len(x) / SR
    script_words = align.split_words(text)
    words = align.map_timings(script_words, ew, total) if ew else align.align_audio(x, SR, text, lang)[0]
    return x, words


def label(eng: str, voice: str) -> str:
    return ENGINE_NAMES[eng] + ("" if eng == "espeak" else f" ({voice})")


def speak(text: str, lang: str, choice: dict, out_wav: Path, rep=None) -> tuple[str, list[dict]]:
    """Make speech for one piece of text with one voice. Returns (engine label, word timings)."""
    text = align.normalize_fa(text).strip()
    if not text:
        write_wav(out_wav, np.zeros(int(SR * 0.5), np.float32))
        return "silence", []
    eng, voice = resolve(lang, choice, rep)
    x, words = _speak_samples(text, lang, eng, voice, float(choice.get("speed") or 1.0))
    write_wav(out_wav, x)
    return label(eng, voice), words


def speak_lines(lines: list[tuple[str, dict]], lang: str, out_wav: Path, rep=None, gap: float = 0.25) -> tuple[list[str], list[dict]]:
    """A scene with several speakers: [(text, voice_choice), ...] → one WAV. Returns (engine labels, words)."""
    parts, words, engines, t = [], [], [], 0.0
    for text, choice in lines:
        text = align.normalize_fa(text).strip()
        if not text:
            continue
        eng, voice = resolve(lang, choice, rep)
        x, w = _speak_samples(text, lang, eng, voice, float(choice.get("speed") or 1.0))
        if parts:
            parts.append(np.zeros(int(SR * gap), np.float32))
            t += gap
        words += [{"w": d["w"], "s": round(d["s"] + t, 3), "e": round(d["e"] + t, 3)} for d in w]
        parts.append(x)
        t += len(x) / SR
        if label(eng, voice) not in engines:
            engines.append(label(eng, voice))
    write_wav(out_wav, np.concatenate(parts) if parts else np.zeros(int(SR * 0.5), np.float32))
    return engines, words


def split_own_recording(recording: Path, texts: list[str], lang: str, out_dir: Path) -> tuple[str, list[tuple[Path, list[dict]]]]:
    """Cut one recording of the whole episode into scenes using forced alignment.

    Returns (method, [(scene_wav, words_relative_to_scene), ...]).
    """
    full = out_dir / "own_voice_full.wav"
    to_wav(recording, full)
    x, sr = read_wav(full)
    all_text = " ".join(texts)
    words, method = align.align_audio(x, sr, all_text, lang)
    counts = [len(align.split_words(t)) for t in texts]
    results, idx = [], 0
    bounds = []
    for c in counts:
        seg = words[idx: idx + c]
        bounds.append((seg[0]["s"] if seg else (bounds[-1][1] if bounds else 0.0), seg[-1]["e"] if seg else 0.0))
        idx += c
    cuts = [0.0]
    for k in range(1, len(bounds)):
        mid = (bounds[k - 1][1] + bounds[k][0]) / 2
        cuts.append(align.snap_to_silence(x, sr, mid, window=max(0.2, (bounds[k][0] - bounds[k - 1][1]) / 2 + 0.15)))
    cuts.append(len(x) / sr)
    idx = 0
    for k, c in enumerate(counts):
        a, b = int(cuts[k] * sr), int(cuts[k + 1] * sr)
        seg_audio, trimmed = trim_silence(x[a:b], sr)
        offset = a / sr + trimmed
        seg_words = [{"w": w["w"], "s": round(max(0.0, w["s"] - offset), 3), "e": round(max(0.05, w["e"] - offset), 3)}
                     for w in words[idx: idx + c]]
        idx += c
        wav = out_dir / f"own_{k:02d}.wav"
        write_wav(wav, _resample(seg_audio, sr))
        results.append((wav, seg_words))
    return method, results
