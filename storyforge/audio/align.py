"""Word timings for captions.

Best to worst (research.md section 8):
1. Forced alignment of the known script to the audio (wav2vec2 CTC, Apache 2.0 models).
2. Word timings from the voice engine (Kokoro tokens, Edge WordBoundary).
3. Proportional timing by word length inside the speech part of the audio.

Captions always show *your script's words* (with punctuation); engine timings
are matched onto them, so Farsi captions are exactly what you wrote.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

import numpy as np

from .. import config

AR_TO_FA = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی", "ە": "ه", "ۀ": "ه"})
_PUNCT_PAUSE = {",": 0.6, "،": 0.6, ";": 0.8, "؛": 0.8, ":": 0.7, ".": 1.2, "!": 1.2, "?": 1.2, "؟": 1.2, "…": 1.4}


def normalize_fa(text: str) -> str:
    return (text or "").translate(AR_TO_FA)


def split_words(text: str) -> list[str]:
    """Words as shown in captions (punctuation stays attached)."""
    return [w for w in re.split(r"\s+", normalize_fa(text).strip()) if w]


def core(word: str) -> str:
    """Lowercase letters/digits only, for matching (works for Persian too)."""
    w = unicodedata.normalize("NFKC", normalize_fa(word)).lower()
    w = w.replace("‌", "")
    return "".join(ch for ch in w if ch.isalnum())


# ---------------------------------------------------------------------------
# Proportional timing
# ---------------------------------------------------------------------------


def speech_bounds(samples: np.ndarray, sr: int, thresh_db: float = -40.0) -> tuple[float, float]:
    """Start and end (seconds) of the part that isn't silence."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if len(samples) == 0:
        return 0.0, 0.0
    hop = max(1, int(sr * 0.01))
    n = len(samples) // hop
    if n == 0:
        return 0.0, len(samples) / sr
    frames = samples[: n * hop].reshape(n, hop).astype(np.float64)
    rms = np.sqrt((frames**2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-12) + 1e-12)
    voiced = np.where(db > thresh_db)[0]
    if len(voiced) == 0:
        return 0.0, len(samples) / sr
    return voiced[0] * hop / sr, min(len(samples), (voiced[-1] + 1) * hop) / sr


def proportional(words: list[str], start: float, end: float) -> list[dict]:
    """Spread words over [start, end] by their length, with small pauses after punctuation."""
    if not words:
        return []
    weights = []
    for w in words:
        base = 0.35 + len(core(w) or w) * 0.08
        weights.append(base)
    pauses = [_PUNCT_PAUSE.get(w[-1], 0.0) * 0.25 for w in words]
    total = sum(weights) + sum(pauses[:-1])
    scale = max(end - start, 0.05) / max(total, 1e-6)
    out, t = [], start
    for w, wt, pz in zip(words, weights, pauses):
        dur = wt * scale
        out.append({"w": w, "s": round(t, 3), "e": round(t + dur, 3)})
        t += dur + pz * scale
    out[-1]["e"] = round(end, 3)
    return out


# ---------------------------------------------------------------------------
# Map engine word timings onto script words
# ---------------------------------------------------------------------------


def map_timings(script_words: list[str], engine: list[tuple[float, float, str]], total: float) -> list[dict]:
    """engine = [(start, end, text), ...] from the voice engine. Returns [{'w','s','e'}] for script words."""
    if not script_words:
        return []
    eng = [(s, e, core(t)) for s, e, t in engine if core(t)]
    if not eng:
        return proportional(script_words, 0.0, total)
    a = [core(w) for w in script_words]
    b = [t for _, _, t in eng]
    times: list[tuple[float, float] | None] = [None] * len(a)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (eng[j1 + k][0], eng[j1 + k][1])
        elif tag == "replace":  # e.g. "2026" spoken as several words: share the span
            s, e = eng[j1][0], eng[j2 - 1][1]
            n = i2 - i1
            for k in range(n):
                times[i1 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
    return _fill_gaps(script_words, times, total)


def _fill_gaps(words: list[str], times: list, total: float) -> list[dict]:
    n = len(words)
    i = 0
    while i < n:
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        start = times[i - 1][1] if i > 0 else 0.0
        end = times[j][0] if j < n else max(start + 0.3 * (j - i), total)
        for k, item in enumerate(proportional(words[i:j], start, max(end, start + 0.1))):
            times[i + k] = (item["s"], item["e"])
        i = j
    out = []
    for w, (s, e) in zip(words, times):
        out.append({"w": w, "s": round(float(s), 3), "e": round(float(max(e, s + 0.05)), 3)})
    for k in range(1, n):  # keep order
        if out[k]["s"] < out[k - 1]["s"]:
            out[k]["s"] = out[k - 1]["s"]
            out[k]["e"] = max(out[k]["e"], out[k]["s"] + 0.05)
    return out


# ---------------------------------------------------------------------------
# CTC forced alignment (for your own recordings)
# ---------------------------------------------------------------------------


def ctc_viterbi(log_probs: np.ndarray, tokens: list[int], blank: int) -> list[tuple[int, int]]:
    """CTC forced alignment. log_probs: (T, V). Returns (first_frame, last_frame) per target token."""
    T, J = log_probs.shape[0], len(tokens)
    if J == 0 or T < J:
        raise ValueError("audio too short for this text")
    tok = np.asarray(tokens)
    trellis = np.full((T + 1, J + 1), -np.inf, dtype=np.float64)
    trellis[0, 0] = 0.0
    moved = np.zeros((T, J), dtype=bool)  # entered token j at frame t
    tok_emit = np.zeros((T, J), dtype=bool)  # while staying on token j, the token (not blank) was heard
    for t in range(T):
        blank_s = log_probs[t, blank]
        tok_s = log_probs[t, tok]
        stay = trellis[t, 1:] + np.maximum(blank_s, tok_s)
        move = trellis[t, :-1] + tok_s
        go = move > stay
        trellis[t + 1, 1:] = np.where(go, move, stay)
        trellis[t + 1, 0] = trellis[t, 0] + blank_s
        moved[t] = go
        tok_emit[t] = tok_s > blank_s
    first, last = [-1] * J, [-1] * J
    j = J
    for t in range(T - 1, -1, -1):
        if j == 0:
            break
        if moved[t, j - 1]:
            first[j - 1] = t
            if last[j - 1] < 0:
                last[j - 1] = t
            j -= 1
        elif tok_emit[t, j - 1] and last[j - 1] < 0:
            last[j - 1] = t
    return [(max(0, f), max(f, e)) for f, e in zip(first, last)]


_ctc_cache: dict = {}


def _load_ctc(lang: str):
    if lang in _ctc_cache:
        return _ctc_cache[lang]
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor  # noqa: PLC0415

    s = config.get()
    key = "align_fa" if lang == "fa" else "align_en"
    mid = config.MODELS[key]
    proc = Wav2Vec2Processor.from_pretrained(mid, cache_dir=s.model_cache(key))
    model = Wav2Vec2ForCTC.from_pretrained(mid, cache_dir=s.model_cache(key)).eval()
    if s.gpu.available:
        model = model.to("cuda")
    _ctc_cache[lang] = (proc, model)
    return proc, model


def ctc_align(samples: np.ndarray, sr: int, words: list[str], lang: str) -> list[dict]:
    import torch  # noqa: PLC0415

    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample_poly  # noqa: PLC0415

        samples = resample_poly(samples, 16000, sr)
        sr = 16000
    proc, model = _load_ctc(lang)
    vocab = proc.tokenizer.get_vocab()
    blank = proc.tokenizer.pad_token_id
    sep = vocab.get("|")
    upper = lang != "fa"
    tokens, owner = [], []
    for wi, w in enumerate(words):
        chars = [c for c in (core(w).upper() if upper else core(w)) if c in vocab]
        if tokens and sep is not None and chars:
            tokens.append(sep)
            owner.append(-1)
        for c in chars:
            tokens.append(vocab[c])
            owner.append(wi)
    logits = []
    chunk = sr * 30
    for i in range(0, len(samples), chunk):
        part = samples[i: i + chunk]
        if len(part) < sr * 0.2:
            continue
        inp = proc(part, sampling_rate=sr, return_tensors="pt").input_values.to(model.device)
        with torch.no_grad():
            logits.append(torch.log_softmax(model(inp).logits[0].float(), dim=-1).cpu().numpy())
    lp = np.concatenate(logits, axis=0)
    frame_sec = len(samples) / sr / lp.shape[0]
    spans = ctc_viterbi(lp, tokens, blank)
    times: list = [None] * len(words)
    for (s, e), wi in zip(spans, owner):
        if wi < 0:
            continue
        st, en = s * frame_sec, (e + 1) * frame_sec
        times[wi] = (st, en) if times[wi] is None else (min(times[wi][0], st), max(times[wi][1], en))
    return _fill_gaps(words, times, len(samples) / sr)


def align_audio(samples: np.ndarray, sr: int, text: str, lang: str) -> tuple[list[dict], str]:
    """Timings for `text` spoken in `samples`. Returns (words, method)."""
    words = split_words(text)
    try:
        return ctc_align(samples, sr, words, lang), "forced alignment"
    except Exception:
        s, e = speech_bounds(samples, sr)
        return proportional(words, s, e), "estimated timing"


def snap_to_silence(samples: np.ndarray, sr: int, t: float, window: float = 0.8) -> float:
    """Move a cut point to the quietest moment nearby (so we never cut a word in half)."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    hop = int(sr * 0.01)
    a, b = max(0, int((t - window) * sr)), min(len(samples), int((t + window) * sr))
    seg = samples[a:b]
    if len(seg) < hop * 3:
        return t
    n = len(seg) // hop
    rms = np.sqrt((seg[: n * hop].reshape(n, hop).astype(np.float64) ** 2).mean(axis=1))
    rms = np.convolve(rms, np.ones(5) / 5, mode="same")
    dist = np.abs(np.arange(n) * hop + a - t * sr) / (window * sr)
    best = int(np.argmin(rms / (rms.max() + 1e-9) + 0.15 * dist))
    return (a + best * hop) / sr
