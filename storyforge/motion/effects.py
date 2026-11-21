"""The motion engine: turns one still picture into a moving shot.

Every frame is a smooth float "remap" of the picture (no FFmpeg zoompan jitter).
With a depth map, near pixels move more than far ones: that's the 2.5D parallax
look. On top we draw procedural effects (all generated in code, no licenses):
dust, snow, rain, embers, fireflies, fog, light leaks, god rays, flicker,
film grain, vignette and camera shake.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

OVERSCAN = 1.22  # extra picture around the frame so the camera can move


def ease(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, t)))


@dataclass
class Move:
    zoom: tuple[float, float] = (1.0, 1.08)
    pan: tuple[tuple[float, float], tuple[float, float]] = ((0, 0), (0, 0))  # fraction of frame
    par: tuple[tuple[float, float], tuple[float, float]] = ((0, 0), (0, 0))  # parallax, fraction of width
    dolly: tuple[float, float] = (0.0, 0.0)  # extra zoom difference between near and far
    handheld: float = 0.0  # continuous shake (fraction of frame)


def camera_move(name: str, strength: float = 1.0) -> Move:
    s = strength
    a, q = 0.055 * s, 0.05 * s
    moves = {
        "push_in": Move(zoom=(1.0, 1.0 + 0.13 * s), dolly=(0.0, 0.09 * s)),
        "pull_out": Move(zoom=(1.0 + 0.14 * s, 1.0), dolly=(0.09 * s, 0.0)),
        "pan_left": Move(zoom=(1.07, 1.07), pan=((a, 0), (-a, 0)), par=((q, 0), (-q, 0))),
        "pan_right": Move(zoom=(1.07, 1.07), pan=((-a, 0), (a, 0)), par=((-q, 0), (q, 0))),
        "tilt_up": Move(zoom=(1.07, 1.07), pan=((0, a), (0, -a)), par=((0, q * 0.6), (0, -q * 0.6))),
        "tilt_down": Move(zoom=(1.07, 1.07), pan=((0, -a), (0, a)), par=((0, -q * 0.6), (0, q * 0.6))),
        "orbit_left": Move(zoom=(1.06, 1.1), pan=((0.012 * s, 0), (-0.012 * s, 0)), par=((-0.07 * s, 0), (0.07 * s, 0))),
        "orbit_right": Move(zoom=(1.06, 1.1), pan=((-0.012 * s, 0), (0.012 * s, 0)), par=((0.07 * s, 0), (-0.07 * s, 0))),
        "dolly_zoom": Move(zoom=(1.04, 1.04 + 0.12 * s), dolly=(0.0, -0.24 * s)),
        "handheld": Move(zoom=(1.08, 1.1), pan=((-0.006, 0), (0.006, 0)), handheld=0.0055 * s),
        "static": Move(zoom=(1.02, 1.06), pan=((-0.004, 0), (0.004, 0)), par=((0.008, 0), (-0.008, 0))),
    }
    return moves.get(name, moves["push_in"])


# ---------------------------------------------------------------------------
# Canvas preparation
# ---------------------------------------------------------------------------


def _resize(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    import cv2  # noqa: PLC0415

    w, h = size
    interp = cv2.INTER_AREA if w < img.shape[1] else cv2.INTER_LANCZOS4
    return cv2.resize(img, (w, h), interpolation=interp)


def _cover(img: np.ndarray, w: int, h: int, focus_y: float = 0.45) -> np.ndarray:
    ih, iw = img.shape[:2]
    scale = max(w / iw, h / ih)
    nw, nh = max(w, round(iw * scale)), max(h, round(ih * scale))
    big = _resize(img, (nw, nh))
    x0 = (nw - w) // 2
    y0 = int((nh - h) * focus_y)  # slightly above center: faces are usually in the upper half
    return big[y0:y0 + h, x0:x0 + w]


def prepare_canvas(rgb: np.ndarray, depth: np.ndarray | None, size: tuple[int, int]):
    """Fit the picture to the frame (+overscan). Very different shapes get a blurred background fill."""
    import cv2  # noqa: PLC0415

    W, H = size
    Ww, Hw = int(round(W * OVERSCAN)), int(round(H * OVERSCAN))
    ih, iw = rgb.shape[:2]
    if abs(math.log((iw / ih) / (W / H))) < 0.35:
        canvas = _cover(rgb, Ww, Hw)
        dcanvas = _cover(depth, Ww, Hw) if depth is not None else None
    else:  # e.g. a 9:16 picture in a 16:9 video
        small = _cover(rgb, Ww // 4, Hw // 4)
        bg = cv2.GaussianBlur(small, (0, 0), 12)
        bg = _resize(bg, (Ww, Hw)).astype(np.float32) * 0.72
        scale = min(Ww / iw, Hw / ih) * 0.96
        fw, fh = int(iw * scale), int(ih * scale)
        fg = _resize(rgb, (fw, fh))
        x0, y0 = (Ww - fw) // 2, (Hw - fh) // 2
        shadow = np.zeros((Hw, Ww), np.float32)
        shadow[y0:y0 + fh, x0:x0 + fw] = 1.0
        shadow = cv2.GaussianBlur(shadow, (0, 0), max(Ww, Hw) / 60)
        canvas = (bg * (1 - 0.6 * shadow[..., None])).astype(np.uint8)
        canvas[y0:y0 + fh, x0:x0 + fw] = fg
        dcanvas = np.full((Hw, Ww), 0.05, np.float32)
        if depth is not None:
            dcanvas[y0:y0 + fh, x0:x0 + fw] = 0.25 + 0.75 * _resize(depth, (fw, fh))
        else:
            dcanvas[y0:y0 + fh, x0:x0 + fw] = 0.6
    # gentle sharpening after upscaling
    blur = cv2.GaussianBlur(canvas, (0, 0), 1.2)
    canvas = cv2.addWeighted(canvas, 1.35, blur, -0.35, 0)
    if dcanvas is not None:
        dcanvas = dcanvas.astype(np.float32)
    return np.ascontiguousarray(canvas), dcanvas


# ---------------------------------------------------------------------------
# Procedural effects
# ---------------------------------------------------------------------------


class Particles:
    """Deterministic particles: position depends only on time, so any frame can be drawn alone."""

    def __init__(self, kind: str, size: tuple[int, int], rng: np.random.Generator):
        W, H = size
        self.kind, self.W, self.H = kind, W, H
        scale = W / 1080
        n = {"dust": 70, "snow": 170, "rain": 230, "embers": 60, "fireflies": 26}[kind]
        self.p0 = rng.random((n, 2)).astype(np.float32)
        self.phase = rng.random(n).astype(np.float32) * 6.283
        self.depth = rng.random(n).astype(np.float32)  # 0 far .. 1 near
        if kind == "dust":
            self.vel = (rng.random((n, 2)) - 0.5).astype(np.float32) * [0.02, 0.02]
            self.rad = (1.5 + 3.5 * self.depth) * scale
            self.color, self.alpha = (255, 236, 210), 0.55
        elif kind == "snow":
            self.vel = np.stack([0.02 + 0.03 * rng.random(n), 0.06 + 0.12 * self.depth], 1).astype(np.float32)
            self.rad = (1.5 + 4 * self.depth) * scale
            self.color, self.alpha = (255, 255, 255), 0.85
        elif kind == "rain":
            self.vel = np.stack([np.full(n, 0.12), 1.4 + 1.2 * self.depth], 1).astype(np.float32)
            self.rad = (1 + 1.5 * self.depth) * scale
            self.color, self.alpha = (200, 215, 235), 0.35
        elif kind == "embers":
            self.vel = np.stack([(rng.random(n) - 0.5) * 0.04, -(0.05 + 0.12 * self.depth)], 1).astype(np.float32)
            self.rad = (1.5 + 3 * self.depth) * scale
            self.color, self.alpha = (255, 140, 40), 0.95
        else:  # fireflies
            self.vel = (rng.random((n, 2)) - 0.5).astype(np.float32) * 0.03
            self.rad = (2.5 + 3 * self.depth) * scale
            self.color, self.alpha = (210, 255, 120), 1.0

    def layer(self, t: float) -> np.ndarray:
        """Additive light layer (H/2, W/2, 3) float32 for time t (seconds)."""
        import cv2  # noqa: PLC0415

        w2, h2 = self.W // 2, self.H // 2
        out = np.zeros((h2, w2, 3), np.float32)
        p = self.p0 + self.vel * t
        sway = 0.012 * np.sin(t * 1.3 + self.phase) if self.kind in ("snow", "embers", "fireflies", "dust") else 0
        x = ((p[:, 0] + sway) % 1.1 - 0.05) * w2
        y = (p[:, 1] % 1.1 - 0.05) * h2
        if self.kind == "fireflies":
            bright = 0.5 + 0.5 * np.sin(t * 2.2 + self.phase * 3)
        elif self.kind == "embers":
            bright = 0.6 + 0.4 * np.sin(t * 5 + self.phase * 2)
        else:
            bright = 0.5 + 0.5 * self.depth
        col = np.array(self.color, np.float32)
        for i in range(len(x)):
            c = tuple(float(v) for v in col * bright[i] * self.alpha)
            if self.kind == "rain":
                dx, dy = self.vel[i] * 0.035 * w2
                cv2.line(out, (int(x[i]), int(y[i])), (int(x[i] + dx), int(y[i] + dy)), c,
                         max(1, int(self.rad[i] / 2)), cv2.LINE_AA)
            else:
                cv2.circle(out, (int(x[i]), int(y[i])), max(1, int(self.rad[i] / 2)), c, -1, cv2.LINE_AA)
        if self.kind in ("embers", "fireflies", "dust"):
            glow = cv2.GaussianBlur(out, (0, 0), 3.0 * self.W / 1080 + 1)
            out = out + glow * (2.2 if self.kind != "dust" else 1.0)
        return out


class Overlay:
    """All per-frame extras for one scene."""

    def __init__(self, size: tuple[int, int], effects, seed: int, duration: float, grain=True, vignette=True,
                 shake_times=(), handheld=0.0):
        import cv2  # noqa: PLC0415

        self.W, self.H = size
        self.duration = duration
        self.rng = np.random.default_rng(seed)
        self.effects = [e for e in (effects or []) if e]
        self.particles = [Particles(e, size, self.rng) for e in self.effects if e in ("dust", "snow", "rain", "embers", "fireflies")]
        W, H = size
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
        vig = (1 - 0.32 * np.clip(r2 / 2, 0, 1) ** 1.3).astype(np.float32)
        self.vignette = cv2.merge([vig, vig, vig]) if vignette else None
        self.grain = None
        if grain:  # 4 full-size grain frames made once (grain looks best slightly soft)
            self.grain = []
            for _ in range(4):
                g = cv2.resize(self.rng.normal(0, 6, (H // 2, W // 2)).astype(np.float32), (W, H),
                               interpolation=cv2.INTER_LINEAR)
                self.grain.append(cv2.merge([g, g, g]))
        if "fog" in self.effects:
            fog = self.rng.random((max(4, H // 90), max(8, (W * 2) // 90))).astype(np.float32)
            fog = cv2.resize(fog, (W * 2, H), interpolation=cv2.INTER_CUBIC)
            self.fog = cv2.GaussianBlur(fog, (0, 0), W / 25)
            self.fog = (self.fog - self.fog.min()) / (np.ptp(self.fog) + 1e-6)
        if "god_rays" in self.effects:
            ang = np.arctan2(yy + H * 0.25, xx - W * 0.3)
            rays = np.zeros_like(ang)
            for k, amp in ((9, 0.5), (23, 0.3), (47, 0.2)):
                rays += amp * (0.5 + 0.5 * np.sin(ang * k + self.rng.random() * 6.28))
            fall = np.exp(-np.sqrt((xx - W * 0.3) ** 2 + (yy + H * 0.25) ** 2) / (H * 0.9))
            self.rays = (rays * fall).astype(np.float32)[..., None] * np.array([255, 235, 190], np.float32)
        self.flashes = sorted(self.rng.uniform(0.15, 0.85, 2) * duration) if "flicker" in self.effects else []
        self.shake_times = list(shake_times)
        self.handheld = handheld
        self.shake_phase = self.rng.random(6) * 6.28

    def shake(self, t: float) -> tuple[float, float]:
        """Camera shake offset (fraction of frame) at time t."""
        dx = dy = 0.0
        ph = self.shake_phase
        if self.handheld:
            dx += self.handheld * (math.sin(t * 1.7 + ph[0]) + 0.5 * math.sin(t * 4.1 + ph[1]))
            dy += self.handheld * (math.sin(t * 1.3 + ph[2]) + 0.5 * math.sin(t * 3.7 + ph[3]))
        for th in self.shake_times:
            if 0 <= t - th < 0.7:
                env = math.exp(-(t - th) * 6.0) * 0.012
                dx += env * math.sin((t - th) * 55 + ph[4])
                dy += env * math.sin((t - th) * 47 + ph[5])
        return dx, dy

    def apply(self, frame: np.ndarray, t: float, index: int) -> np.ndarray:
        import cv2  # noqa: PLC0415

        f = frame.astype(np.float32)
        W, H = self.W, self.H
        if "fog" in self.effects:
            off = int((t * 0.03 * W) % W)
            fog = self.fog[:, off:off + W]
            f = 255 - (255 - f) * (1 - 0.22 * fog[..., None])
        if "god_rays" in self.effects:
            f = f + self.rays * (0.16 + 0.05 * math.sin(t * 0.8))
        if "light_leak" in self.effects:
            f = f + cv2.resize(light_leak_small(t, W, H), (W, H), interpolation=cv2.INTER_CUBIC)
        if self.particles:
            light = sum(p.layer(t) for p in self.particles)
            f = f + cv2.resize(light, (W, H), interpolation=cv2.INTER_LINEAR)
        if "flicker" in self.effects:
            f = f * flicker_gain(self, t)
        if self.vignette is not None:
            f = cv2.multiply(f, self.vignette)
        if self.grain is not None:
            f = cv2.add(f, self.grain[index % len(self.grain)])
        np.clip(f, 0, 255, out=f)
        return f.astype(np.uint8)


# ---------------------------------------------------------------------------
# Frame generator
# ---------------------------------------------------------------------------


def camera_state(move: Move, overlay: "Overlay", i: int, n: int, fps: int):
    """Zoom, dolly, pan and parallax for frame i (shared by the CPU and GPU renderers)."""
    t = i / fps
    e = ease(i / max(1, n - 1))
    z = move.zoom[0] + (move.zoom[1] - move.zoom[0]) * e
    k = move.dolly[0] + (move.dolly[1] - move.dolly[0]) * e
    px = move.pan[0][0] + (move.pan[1][0] - move.pan[0][0]) * e
    py = move.pan[0][1] + (move.pan[1][1] - move.pan[0][1]) * e
    qx = move.par[0][0] + (move.par[1][0] - move.par[0][0]) * e
    qy = move.par[0][1] + (move.par[1][1] - move.par[0][1]) * e
    sx, sy = overlay.shake(t)
    return t, z, k, px + sx, py + sy, qx, qy


def light_leak_small(t: float, W: int, H: int) -> np.ndarray:
    lw, lh = (32, 18) if W > H else (18, 32)  # tiny grid, scaled up = soft light
    yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32)
    cx = lw * (0.5 + 0.6 * math.sin(t * 0.35 + 1))
    cy = lh * (0.3 + 0.5 * math.sin(t * 0.27))
    blob = np.exp(-(((xx - cx) / (lw * 0.45)) ** 2 + ((yy - cy) / (lh * 0.5)) ** 2))
    return (blob[..., None] * np.array([255, 110, 170], np.float32) * (0.22 + 0.1 * math.sin(t * 0.9))).astype(np.float32)


def flicker_gain(overlay: "Overlay", t: float) -> float:
    k = 1 + 0.04 * math.sin(t * 23) * math.sin(t * 7)
    for fl in overlay.flashes:
        if 0 <= t - fl < 0.5:
            k += 0.9 * math.exp(-(t - fl) * 9)
    return k


def frames(rgb: np.ndarray, depth: np.ndarray | None, size: tuple[int, int], duration: float, fps: int = 30,
           camera: str = "push_in", effects=(), seed: int = 0, shake_times=(), strength: float = 1.0,
           grain: bool = True, vignette: bool = True):
    """Yield RGB uint8 frames for one scene."""
    import cv2  # noqa: PLC0415

    W, H = size
    canvas, dcanvas = prepare_canvas(rgb, depth, size)
    Hw, Ww = canvas.shape[:2]
    move = camera_move(camera, strength)
    if dcanvas is None:  # no depth: plain Ken Burns, keep the same camera path
        move.par = ((0, 0), (0, 0))
        move.dolly = (0.0, 0.0)
    overlay = Overlay(size, effects, seed, duration, grain, vignette, shake_times, move.handheld)
    # The warp map is smooth, so we compute it at half size and scale it up (4x less math).
    h2, w2 = (H + 1) // 2, (W + 1) // 2
    X = (np.arange(w2, dtype=np.float32) * (W / w2) - W / 2 + 0.5)[None, :]
    Y = (np.arange(h2, dtype=np.float32) * (H / h2) - H / 2 + 0.5)[:, None]
    cx, cy = Ww / 2, Hw / 2
    n = max(1, int(round(duration * fps)))
    for i in range(n):
        t, z, k, px, py, qx, qy = camera_state(move, overlay, i, n, fps)
        if dcanvas is not None:
            bx = np.broadcast_to(cx + X / z + px * W, (h2, w2)).astype(np.float32)
            by = np.broadcast_to(cy + Y / z + py * H, (h2, w2)).astype(np.float32)
            d = cv2.remap(dcanvas, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT) - 0.5
            zf = z * (1 + k * d)
            mx = cv2.resize((cx + X / zf + px * W + qx * W * d).astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
            my = cv2.resize((cy + Y / zf + py * H + qy * W * d).astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
            frame = cv2.remap(canvas, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        else:  # affine is faster without depth
            m = np.float32([[1 / z, 0, cx + px * W - (W / 2) / z], [0, 1 / z, cy + py * H - (H / 2) / z]])
            frame = cv2.warpAffine(canvas, m, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                   borderMode=cv2.BORDER_REFLECT)
        yield overlay.apply(frame, t, i)


def write_video(frame_iter, out: Path, size: tuple[int, int], fps: int = 30, quality: str = "work") -> None:
    """Pipe raw frames into FFmpeg."""
    from .. import config  # noqa: PLC0415

    W, H = size
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mp4")
    cmd = [config.ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", *config.encoder_args(quality), "-r", str(fps),
           "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for fr in frame_iter:
            proc.stdin.write(np.ascontiguousarray(fr).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="ignore")
        if proc.wait() != 0:
            raise RuntimeError(f"FFmpeg could not write the clip: {err[-300:]}")
    except BaseException:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
