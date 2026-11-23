"""Render scenes of the 3D world straight into video files (no preview render, no image files).

Each scene becomes one clip, encoded once at final quality with its keyword captions burned in.
All clips use the same encoder settings, so they are joined later without re-encoding.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .. import config
from . import gl
from .labels import LabelMaker, card_image
from .scene import World

FPS = 30
RENDER_VERSION = "3d-8"  # change when the look changes, so finished clips are made again


def make_renderer(size: tuple[int, int]) -> tuple[gl.Renderer, tuple[int, int], str]:
    """GPU (NVIDIA through EGL) if possible, else CPU (Mesa llvmpipe).

    On the CPU the frames are drawn at 2/3 size with 2x smoothing and scaled up by FFmpeg: about 2x faster,
    still sharp for low poly. Returns (renderer, render size, label for the log).
    """
    ctx = gl.create_context()
    name = ctx.info.get("GL_RENDERER", "?")
    cpu = any(k in name.lower() for k in ("llvmpipe", "softpipe", "swrast", "swiftshader"))
    W, H = size
    if cpu and min(W, H) > 720:
        rw, rh = int(round(W * 2 / 3 / 2) * 2), int(round(H * 2 / 3 / 2) * 2)
    else:
        rw, rh = W, H
    r = gl.Renderer((rw, rh), msaa=2 if cpu else 4, shadow_size=1536 if cpu else 2048, ctx=ctx)
    how = f"{'CPU' if cpu else 'GPU'} · {name.split('(')[0].strip()} · {rw}×{rh}" + (f" → {W}×{H}" if (rw, rh) != (W, H) else "")
    return r, (rw, rh), how


class Writer:
    """Pipe RGB frames into FFmpeg (final quality, optional caption burn-in and upscale)."""

    def __init__(self, out: Path, in_size: tuple[int, int], out_size: tuple[int, int], fps: int = FPS, vf: str = ""):
        self.out = Path(out)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.tmp = self.out.with_name(self.out.stem + ".part.mp4")
        W, H = in_size
        filters = []
        if in_size != out_size:
            filters.append(f"scale={out_size[0]}:{out_size[1]}:flags=lanczos")
        if vf:
            filters.append(vf)
        cmd = [config.ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", *(["-vf", ",".join(filters)] if filters else []),
               *config.encoder_args("final"), "-r", str(fps), "-an", "-movflags", "+faststart", str(self.tmp)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="ignore")
        if self.proc.wait() != 0:
            self.tmp.unlink(missing_ok=True)
            raise RuntimeError(f"FFmpeg could not write the clip: {err[-300:]}")
        self.tmp.replace(self.out)

    def abort(self) -> None:
        try:
            self.proc.kill()
        finally:
            self.tmp.unlink(missing_ok=True)


def render_span(world: World, renderer: gl.Renderer, labels: LabelMaker, t0: float, t1: float, out: Path,
                out_size: tuple[int, int], vf: str = "", fps: int = FPS, card: dict | None = None,
                stop=None) -> int:
    """Frames from t0 to t1 (seconds of the whole video) → one clip. card = end card {'text', 'lang'}."""
    n = max(1, int(round((t1 - t0) * fps)))
    w = Writer(out, (renderer.W, renderer.H), out_size, fps, vf)
    card_img = None
    if card:
        card_img = card_image(card["text"], card.get("lang", "en"), (renderer.W, renderer.H))
    try:
        for k in range(n):
            if stop is not None and stop():
                raise InterruptedError("stopped")
            T = t0 + k / fps
            if card_img is not None:  # end card: the last moment, frozen and darkened, card pops in
                fr = world.frame(min(T, world.scenes[-1]["end"] - 1 / fps), labels)
                fr.labels = []
                u = k / max(1, n - 1)
                fr.fade = min(0.55, u * 3)
                k_in = min(1.0, (k / fps) / 0.25)
                fr.labels = [gl.Label("__card", card_img, renderer.W / 2, renderer.H / 2, scale=0.85 + 0.15 * k_in,
                                      alpha=k_in, anchor="center")]
            else:
                fr = world.frame(T, labels)
            w.write(renderer.render(fr))
        w.close()
    except BaseException:
        w.abort()
        raise
    return n


def render_still(world: World, renderer: gl.Renderer, labels: LabelMaker, T: float, out: Path) -> Path:
    from PIL import Image  # noqa: PLC0415

    img = renderer.render(world.frame(T, labels))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(out, quality=90)
    return out
