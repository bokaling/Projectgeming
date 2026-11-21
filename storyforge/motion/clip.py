"""Make one silent scene clip of an exact length from any source:
a picture (motion engine), a hero clip (Wan 2.2) or your own uploaded video."""

from __future__ import annotations

import math
from pathlib import Path

from .. import media
from . import depth as depth_mod
from . import effects


def from_image(image: Path, depth_path: Path | None, out: Path, size: tuple[int, int], seconds: float, fps: int,
               camera: str, fx, seed: int, shake_times=(), strength: float = 1.0, extras: bool = True) -> str:
    import cv2  # noqa: PLC0415

    bgr = cv2.imread(str(image), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"picture missing: {image}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    d = depth_mod.load_depth(depth_path, rgb.shape[:2]) if depth_path else None
    frames = effects.frames(rgb, d, size, seconds, fps, camera, fx if extras else [], seed, shake_times, strength,
                            grain=extras, vignette=True)
    effects.write_video(frames, out, size, fps)
    return "2.5D parallax" if d is not None else "Ken Burns"


def from_video(video: Path, out: Path, size: tuple[int, int], seconds: float, fps: int, max_slow: float = 1.5) -> str:
    """Fit a video into the frame and make it exactly `seconds` long (slow down a little, then hold the last frame)."""
    W, H = size
    src_len = media.duration(video) or seconds
    slow = min(max_slow, max(1.0, seconds / max(src_len, 0.1)))
    vw, vh = media.video_size(video)
    similar = vw and vh and abs(math.log((vw / vh) / (W / H))) < 0.35
    base = f"setpts={slow:.4f}*PTS,fps={fps}"
    if similar:
        chain = f"[0:v]{base},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v0]"
    else:  # very different shape: blurred background + the whole clip on top
        chain = (
            f"[0:v]{base},split[a][b];"
            f"[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
            f"boxblur=10:2,scale={W}:{H},eq=brightness=-0.12[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]"
        )
    chain += f";[v0]tpad=stop_mode=clone:stop_duration={seconds + 1:.2f},trim=duration={seconds:.3f},format=yuv420p[v]"
    from .. import config  # noqa: PLC0415

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mp4")
    media.run_ffmpeg(["-i", video, "-filter_complex", chain, "-map", "[v]", "-an", "-r", fps,
                      *config.encoder_args("work"), "-movflags", "+faststart", tmp], "prepare your video clip")
    tmp.replace(out)
    return "video clip" if slow <= 1.01 else f"video clip (slowed {slow:.2f}x)"

