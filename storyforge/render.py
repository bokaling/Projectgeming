"""Final assembly with FFmpeg: scene clips + transitions + captions + audio → upload-ready MP4."""

from __future__ import annotations

from pathlib import Path

from . import captions, config, media

TRANSITION = 0.35  # seconds of overlap between scenes
FPS = 30


def transition_for(scene: dict, index: int, count: int) -> str:
    """Pick an xfade transition from the scene's sound effects (variety helps against 'templated' looks)."""
    sfx = scene.get("sfx") or []
    if index == count - 1:
        return "fadeblack"
    if "impact" in sfx or "thunder" in sfx:
        return "fadewhite"
    if "whoosh" in sfx:
        return "smoothleft" if index % 2 else "smoothright"
    if "glitch" in sfx:
        return "pixelize"
    return "fade" if index % 3 else "dissolve"


def assemble(clips: list[Path], durations: list[float], transitions: list[str], audio: Path, ass: Path | None,
             out: Path, size: tuple[int, int], title: str = "", fps: int = FPS) -> Path:
    """clips[i] must be durations[i] + TRANSITION seconds long. transitions[i] is used going INTO clip i (i >= 1)."""
    if not clips or len(clips) != len(durations):
        raise ValueError("clips and durations don't match")
    W, H = size
    total = sum(durations) + TRANSITION
    args: list = []
    for c in clips:
        args += ["-i", c]
    args += ["-i", audio]
    parts = [f"[{i}:v]settb=AVTB,fps={fps},scale={W}:{H},setsar=1,format=yuv420p[v{i}]" for i in range(len(clips))]
    last = "v0"
    offset = 0.0
    for i in range(1, len(clips)):
        offset += durations[i - 1]
        name = f"x{i}"
        parts.append(f"[{last}][v{i}]xfade=transition={transitions[i]}:duration={TRANSITION}:offset={offset:.3f}[{name}]")
        last = name
    if ass is not None:
        parts.append(f"[{last}]{captions.ass_filter(ass)},format=yuv420p[vout]")
    else:
        parts.append(f"[{last}]format=yuv420p[vout]")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mp4")
    args += [
        "-filter_complex", ";".join(parts), "-map", "[vout]", "-map", f"{len(clips)}:a",
        *config.encoder_args("final"), "-r", fps, "-c:a", "aac", "-b:a", "192k", "-ar", 48000,
        "-t", f"{total:.3f}", "-movflags", "+faststart",
        "-metadata", f"title={title}", "-metadata", "comment=Contains AI-generated images and voice", tmp,
    ]
    media.run_ffmpeg(args, "put the final video together")
    tmp.replace(out)
    return out
