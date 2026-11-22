"""Fast editing: a hard cut every 1.5-2.5 s (Shorts) or 3-5 s (long videos).

The extra shots are zooms and crops into different parts of the SAME picture (wide → punch in on
the face → a detail → the other side…), so you don't need more pictures. Cuts land on word starts.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from ..paste import CUT_SECONDS

# framing name: (zoom, where it looks)
FRAMINGS = {
    "full": (1.0, "middle"),
    "subject": (1.38, "primary"),  # punch in on the main subject (a face if one is found)
    "tight": (1.72, "primary"),  # very close on the subject
    "detail": (1.6, "secondary"),  # another interesting part of the picture
    "side": (1.25, "side"),  # the other side of the picture
}
PATTERN = ["subject", "detail", "tight", "side", "subject", "full"]
CALM_MOVES = ["push_in", "pull_out", "pan_left", "push_fast", "pan_right", "tilt_up"]
TENSE_MOVES = ["push_fast", "handheld", "pull_out", "push_in", "pan_right", "push_fast", "pan_left"]
TENSE_MOODS = {"dark", "tense", "action", "mysterious"}


def focus_points(rgb: np.ndarray, depth: np.ndarray | None = None) -> dict:
    """Where to look in a picture: primary (a face, or the nearest/most detailed thing), secondary, side.

    Values are fractions of the picture (0..1). No AI model: OpenCV face finder + detail map (+ depth if made).
    """
    import cv2  # noqa: PLC0415

    h, w = rgb.shape[:2]
    small = cv2.resize(rgb, (160, max(1, int(160 * h / w))), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)
    detail = np.abs(cv2.Laplacian(gray, cv2.CV_32F)) + 0.5 * np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 1))
    detail = cv2.GaussianBlur(detail, (0, 0), 6)
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    center = np.exp(-(((xx / sw - 0.5) / 0.38) ** 2 + ((yy / sh - 0.45) / 0.42) ** 2))
    sal = detail / (detail.max() + 1e-6) * (0.55 + 0.45 * center)
    if depth is not None:
        d = cv2.resize(depth.astype(np.float32), (sw, sh), interpolation=cv2.INTER_AREA)
        sal = sal * (0.4 + 0.6 * d)  # near things are more likely the subject
    face = _face(rgb)
    if face is not None:
        primary = face
    else:
        y, x = np.unravel_index(int(np.argmax(sal)), sal.shape)
        primary = ((x + 0.5) / sw, (y + 0.5) / sh)
    far = np.sqrt((xx / sw - primary[0]) ** 2 + (yy / sh - primary[1]) ** 2)
    y2, x2 = np.unravel_index(int(np.argmax(sal * np.clip(far / 0.35, 0, 1))), sal.shape)
    secondary = ((x2 + 0.5) / sw, (y2 + 0.5) / sh)
    side = (0.27 if primary[0] > 0.5 else 0.73, 0.45)
    r = lambda p: (round(float(min(0.95, max(0.05, p[0]))), 3), round(float(min(0.95, max(0.05, p[1]))), 3))  # noqa: E731
    return {"primary": r(primary), "secondary": r(secondary), "side": r(side), "middle": (0.5, 0.45),
            "face": face is not None, "size": [int(w), int(h)]}


def _face(rgb: np.ndarray):
    """The biggest face (OpenCV's built-in finder; often misses painted faces, that's fine)."""
    try:
        import cv2  # noqa: PLC0415

        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if not path.exists():
            return None
        h, w = rgb.shape[:2]
        scale = 640 / max(h, w)
        small = cv2.resize(rgb, (int(w * scale), int(h * scale)))
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY))
        faces = cv2.CascadeClassifier(str(path)).detectMultiScale(gray, 1.15, 6, minSize=(40, 40))
        if len(faces) == 0:
            return None
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        return ((x + fw / 2) / small.shape[1], (y + fh * 0.55) / small.shape[0])
    except Exception:  # noqa: BLE001
        return None


def cached_focus(image: str | Path, depth: str | Path | None = None) -> dict:
    """focus_points, saved next to the picture (made once)."""
    import cv2  # noqa: PLC0415

    image = Path(image)
    st = image.stat()
    path = image.with_name(f"focus_{image.stem}.json")
    sig = f"{st.st_size}-{int(st.st_mtime)}-{bool(depth)}"
    try:
        data = json.loads(path.read_text())
        if data.get("sig") == sig:
            return data
    except Exception:  # noqa: BLE001
        pass
    bgr = cv2.imread(str(image), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    d = None
    if depth and Path(depth).exists():
        from . import depth as depth_mod  # noqa: PLC0415

        d = depth_mod.load_depth(Path(depth), rgb.shape[:2])
    data = {**focus_points(rgb, d), "sig": sig}
    try:
        path.write_text(json.dumps(data))
    except OSError:
        pass
    return data


def _snap(frame: int, word_frames: list[int], window: int) -> int:
    near = [w for w in word_frames if abs(w - frame) <= window]
    return min(near, key=lambda w: abs(w - frame)) if near else frame


def split(total: int, parts: int, word_frames: list[int], window: int, min_len: int, rng: random.Random,
          jitter: float = 0.0) -> list[int]:
    """Boundaries (frame numbers, without 0 and total) for `parts` pieces, snapped to word starts."""
    if parts <= 1:
        return []
    base = total / parts
    cuts, last = [], 0
    for k in range(1, parts):
        f = int(round(k * base + (rng.uniform(-jitter, jitter) * base if jitter else 0)))
        f = _snap(f, word_frames, window)
        f = max(last + min_len, min(f, total - min_len * (parts - k)))
        cuts.append(f)
        last = f
    return [c for c in cuts if 0 < c < total]


def plan(images: list[dict], frames_total: int, fps: int, length: str, word_starts: list[float], seed: int,
         mood: str = "", hook: bool = False, events: dict | None = None) -> list[dict]:
    """Cut one scene into shots. images: [{"image", "depth", "camera", "fx", "focus"}, …] (one per picture).

    Returns shots: {"image", "depth", "frames", "crop": (zoom, fx, fy), "camera", "fx", "seed",
    "punch": [s], "shake": [s], "flash": [s], "start": frame offset in the scene}.
    """
    rng = random.Random(seed)
    events = events or {}
    lo, hi = CUT_SECONDS.get(length, CUT_SECONDS["short"])
    word_frames = sorted({int(round(t * fps)) for t in word_starts if 0 < t * fps < frames_total})
    # 1) the scene's time is shared by its pictures (cut on a word)
    bounds = [0] + split(frames_total, len(images), word_frames, int(0.5 * fps), int(0.8 * fps), rng) + [frames_total]
    moves = TENSE_MOVES if mood in TENSE_MOODS else CALM_MOVES
    shots, prev_framing, prev_cam = [], None, None
    for i, img in enumerate(images):
        a, b = bounds[i], bounds[i + 1] if i + 1 < len(bounds) else frames_total
        seg = b - a
        if seg <= 0:
            continue
        # 2) a hard cut every lo..hi seconds inside this picture
        n = max(1, round(seg / fps / ((lo + hi) / 2)))
        while n > 1 and seg / n < lo * fps * 0.85:
            n -= 1
        local_words = [w - a for w in word_frames if a < w < b]
        inner = split(seg, n, local_words, int(0.3 * fps), int(lo * fps * 0.75), rng, jitter=0.18)
        edges = [0] + inner + [seg]
        focus = img.get("focus") or {"primary": (0.5, 0.4), "secondary": (0.5, 0.6), "side": (0.3, 0.45),
                                     "middle": (0.5, 0.45), "size": [1080, 1920]}
        small = min(focus.get("size") or [1080, 1920]) < 900  # small picture: don't zoom in too far (blurry)
        for j in range(len(edges) - 1):
            if hook and i == 0 and j == 0:
                name = "subject"
            elif j == 0:
                name = "full"
            else:
                name = PATTERN[(j - 1 + i) % len(PATTERN)]
            if name == prev_framing:
                name = PATTERN[(PATTERN.index(name) + 1) % len(PATTERN)] if name in PATTERN else "subject"
            zoom, where = FRAMINGS[name]
            if small:
                zoom = min(zoom, 1.45)
            fx, fy = focus.get(where, (0.5, 0.45))
            cam = img.get("camera") if (j == 0 and img.get("camera")) else moves[(i * 3 + j + seed) % len(moves)]
            if cam == prev_cam:
                cam = moves[(moves.index(cam) + 1) % len(moves)] if cam in moves else moves[0]
            s0, s1 = a + edges[j], a + edges[j + 1]

            def inside(key, s0=s0, s1=s1):
                return [round((t * fps - s0) / fps, 3) for t in events.get(key, []) if s0 <= t * fps < s1]

            shots.append({"image": img["image"], "depth": img.get("depth", ""), "frames": int(s1 - s0),
                          "start": int(s0), "crop": [round(zoom, 3), fx, fy], "camera": cam, "framing": name,
                          "fx": img.get("fx") or [], "seed": seed + 31 * len(shots),
                          "punch": inside("punch"), "shake": inside("shake"), "flash": inside("flash"),
                          "picture": i})
            prev_framing, prev_cam = name, cam
    return shots


def picture_changes(shots: list[dict], fps: int, offset: float) -> list[float]:
    """Times (s) where a new picture starts (for the whoosh sound)."""
    out, last = [], None
    for sh in shots:
        if sh["image"] != last and sh["start"] > 0:
            out.append(round(offset + sh["start"] / fps, 3))
        last = sh["image"]
    return out
