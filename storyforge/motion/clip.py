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
    args = (rgb, d, size, seconds, fps, camera, fx if extras else [], seed, shake_times, strength)
    how = "2.5D parallax" if d is not None else "Ken Burns"
    from . import gpu  # noqa: PLC0415

    if gpu.available():  # same picture, much faster on the GPU
        try:
            effects.write_video(gpu.frames(*args, grain=extras, vignette=True), out, size, fps)
            return how + " (GPU)"
        except Exception:  # noqa: BLE001 - e.g. GPU busy/out of memory: use the CPU instead
            pass
    effects.write_video(effects.frames(*args, grain=extras, vignette=True), out, size, fps)
    return how


def from_shots(shots: list[dict], out: Path, size: tuple[int, int], seconds: float, fps: int, extras: bool = True,
               use_gpu: bool | None = None) -> str:
    """One scene clip made of several shots (a new picture every 2-3 s), cut one after another."""
    import cv2  # noqa: PLC0415

    from . import gpu  # noqa: PLC0415

    total = max(1, int(round(seconds * fps)))
    n = len(shots)
    counts = [total // n + (1 if k < total % n else 0) for k in range(n)]
    use_gpu = gpu.available() if use_gpu is None else use_gpu
    kinds = []

    def all_frames():
        for shot, count in zip(shots, counts):
            bgr = cv2.imread(shot["image"], cv2.IMREAD_COLOR)
            if bgr is None:
                raise FileNotFoundError(f"picture missing: {shot['image']}")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            d = depth_mod.load_depth(Path(shot["depth"]), rgb.shape[:2]) if shot.get("depth") else None
            kinds.append("2.5D parallax" if d is not None else "Ken Burns")
            args = (rgb, d, size, count / fps, fps, shot["camera"], shot.get("fx") if extras else [], shot["seed"],
                    shot.get("shake") or [], shot.get("strength", 1.0))
            kw = {"grain": extras, "vignette": True, "punch": shot.get("punch", 0.0)}
            gen = gpu.frames(*args, **kw) if use_gpu else effects.frames(*args, **kw)
            yield from gen

    effects.write_video(all_frames(), out, size, fps)
    how = kinds[0] if kinds else "motion"
    return how + (f", {n} shots" if n > 1 else "") + (" (GPU)" if use_gpu else "")


def from_cuts(shots: list[dict], out: Path, size: tuple[int, int], fps: int, extras: bool = True,
              use_gpu: bool | None = None, vf: str = "") -> str:
    """One scene clip made of fast hard cuts (crops of the scene's pictures), captions burned in (vf)."""
    import cv2  # noqa: PLC0415

    from . import gpu  # noqa: PLC0415

    use_gpu = gpu.available() if use_gpu is None else use_gpu
    cache: dict = {}
    kinds = []

    def load(shot):
        key = (shot["image"], shot.get("depth") or "")
        if key not in cache:
            bgr = cv2.imread(shot["image"], cv2.IMREAD_COLOR)
            if bgr is None:
                raise FileNotFoundError(f"picture missing: {shot['image']}")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            d = depth_mod.load_depth(Path(shot["depth"]), rgb.shape[:2]) if shot.get("depth") else None
            cache.clear()  # keep only the current picture in memory
            cache[key] = (rgb, d)
        return cache[key]

    def all_frames():
        for shot in shots:
            rgb, d = load(shot)
            kinds.append("2.5D parallax" if d is not None else "Ken Burns")
            args = (rgb, d, size, shot["frames"] / fps, fps, shot["camera"], shot.get("fx") if extras else [],
                    shot["seed"], shot.get("shake") or [], shot.get("strength", 1.0))
            kw = {"grain": extras, "vignette": True, "punch_times": shot.get("punch") or [],
                  "flash_times": shot.get("flash") or [], "crop": tuple(shot["crop"]) if shot.get("crop") else None}
            gen = gpu.frames(*args, **kw) if use_gpu else effects.frames(*args, **kw)
            yield from gen

    effects.write_video(all_frames(), out, size, fps, quality="final", vf=vf)
    pictures = len({s["image"] for s in shots})
    return f"{kinds[0] if kinds else 'motion'}, {len(shots)} cuts from {pictures} picture(s)" + (" (GPU)" if use_gpu else "")


def end_card(image: Path, card_png: Path, out: Path, size: tuple[int, int], seconds: float, fps: int) -> str:
    """Last frame: the last picture, dark and soft, with "Part X 👀" (or "The End") popping in."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    W, H = size
    bgr = cv2.imread(str(image), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB) if bgr is not None else np.zeros((H, W, 3), np.uint8)
    bg = effects._cover(rgb, int(W * 1.08), int(H * 1.08))
    bg = (cv2.GaussianBlur(bg, (0, 0), max(4, W / 90)).astype(np.float32) * 0.42).astype(np.uint8)
    card = cv2.imread(str(card_png), cv2.IMREAD_UNCHANGED)
    card = cv2.cvtColor(card, cv2.COLOR_BGRA2RGBA)
    n = max(1, int(round(seconds * fps)))

    def gen():
        for i in range(n):
            t = i / fps
            z = 1.0 + 0.05 * i / max(1, n - 1)
            m = np.float32([[1 / z, 0, bg.shape[1] / 2 - W / 2 / z], [0, 1 / z, bg.shape[0] / 2 - H / 2 / z]])
            frame = cv2.warpAffine(bg, m, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP).astype(np.float32)
            k = min(1.0, t / 0.18)
            scale = 0.82 + 0.18 * (1 - (1 - k) ** 3) + 0.03 * np.sin(min(1.0, t / 0.35) * np.pi)  # small pop
            cw, ch = int(W * scale), int(H * scale)
            c = cv2.resize(card, (cw, ch), interpolation=cv2.INTER_AREA).astype(np.float32)
            x0, y0 = (W - cw) // 2, (H - ch) // 2
            layer = np.zeros((H, W, 4), np.float32)
            xs, ys = max(0, x0), max(0, y0)
            layer[ys:ys + min(ch, H), xs:xs + min(cw, W)] = c[ys - y0:ys - y0 + min(ch, H), xs - x0:xs - x0 + min(cw, W)]
            a = layer[..., 3:4] / 255 * k
            yield (frame * (1 - a) + layer[..., :3] * a).clip(0, 255).astype(np.uint8)

    effects.write_video(gen(), out, size, fps, quality="final")
    return "end card"


def render_job(job: dict) -> str:
    """One scene clip, in a separate process (used for parallel rendering on many-core machines)."""
    if job.get("kind") == "end":
        return end_card(Path(job["image"]), Path(job["card"]), Path(job["out"]), tuple(job["size"]), job["seconds"],
                        job["fps"])
    if job["video"]:
        return from_video(Path(job["video"]), Path(job["out"]), tuple(job["size"]), job["seconds"], job["fps"],
                          vf=job.get("vf", ""))
    if job.get("cuts"):
        try:
            return from_cuts(job["cuts"], Path(job["out"]), tuple(job["size"]), job["fps"], job.get("extras", True),
                             vf=job.get("vf", ""))
        except Exception:  # noqa: BLE001 - GPU busy or out of memory: same picture on the CPU
            return from_cuts(job["cuts"], Path(job["out"]), tuple(job["size"]), job["fps"], job.get("extras", True),
                             use_gpu=False, vf=job.get("vf", ""))
    if job.get("shots"):
        try:
            return from_shots(job["shots"], Path(job["out"]), tuple(job["size"]), job["seconds"], job["fps"],
                              job.get("extras", True))
        except Exception:  # noqa: BLE001 - GPU busy or out of memory: same picture on the CPU
            return from_shots(job["shots"], Path(job["out"]), tuple(job["size"]), job["seconds"], job["fps"],
                              job.get("extras", True), use_gpu=False)
    return from_image(Path(job["image"]), Path(job["depth"]) if job["depth"] else None, Path(job["out"]),
                      tuple(job["size"]), job["seconds"], job["fps"], job["camera"], job["fx"], job["seed"],
                      job["shake"], job["strength"], job["extras"])


def from_video(video: Path, out: Path, size: tuple[int, int], seconds: float, fps: int, max_slow: float = 1.5,
               vf: str = "") -> str:
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
    chain += (f";[v0]tpad=stop_mode=clone:stop_duration={seconds + 1:.2f},trim=duration={seconds:.3f}"
              + (f",{vf}" if vf else "") + ",format=yuv420p[v]")
    from .. import config  # noqa: PLC0415

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mp4")
    media.run_ffmpeg(["-i", video, "-filter_complex", chain, "-map", "[v]", "-an", "-r", fps,
                      *config.encoder_args("final"), "-movflags", "+faststart", tmp], "prepare your video clip")
    tmp.replace(out)
    return "video clip" if slow <= 1.01 else f"video clip (slowed {slow:.2f}x)"



def run_in_subprocess(job: dict) -> str:
    """Render one scene in its own Python process (safe parallelism: never re-runs the app itself)."""
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    from .. import config  # noqa: PLC0415

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(job, f)
        path = f.name
    env = dict(os.environ)
    env["PYTHONPATH"] = str(config.REPO_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["STORYFORGE_FORCE_CPU"] = "1"  # helpers use the CPU; the GPU path runs in the main process
    try:
        res = subprocess.run([sys.executable, "-m", "storyforge.motion.clip", path], capture_output=True, text=True,
                             env=env, timeout=3600)
    finally:
        os.unlink(path)
    if res.returncode != 0:
        tail = (res.stderr or "").strip().splitlines()
        raise RuntimeError("scene render failed: " + (tail[-1][:300] if tail else "unknown error"))
    lines = [ln for ln in res.stdout.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else "rendered"


if __name__ == "__main__":  # python -m storyforge.motion.clip job.json
    import json
    import sys

    import cv2

    cv2.setNumThreads(1)  # several helpers run at once: one core each
    with open(sys.argv[1], encoding="utf-8") as fh:
        print(render_job(json.load(fh)))
