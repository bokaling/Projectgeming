"""Final assembly with FFmpeg, in chunks (so long videos survive a disconnect).

Each chunk = up to 10 scenes joined with crossfades, captions burned in, saved to
Drive. The finished chunks are then joined without re-encoding and the audio is
added. Scene lengths are whole frames, so picture and voice never drift apart.
"""

from __future__ import annotations

from pathlib import Path

from . import captions, config, media

FPS = 30
TRANSITION = 10 / FPS  # 1/3 s of overlap between scenes
CHUNK_SCENES = 10


def frames(sec: float) -> int:
    return int(round(sec * FPS))


def snap(sec: float) -> float:
    """Round to a whole frame."""
    return frames(sec) / FPS


def transition_for(scene: dict, index: int, count: int) -> str:
    """Pick an xfade transition (variety helps against 'templated' looks)."""
    sfx = scene.get("sfx") or []
    if index == count - 1:
        return "fadeblack"
    if "impact" in sfx or "thunder" in sfx:
        return "fadewhite"
    if "whoosh" in sfx:
        return "smoothleft" if index % 2 else "smoothright"
    return ("fade", "dissolve", "fade", "smoothup")[index % 4]


def render_chunk(clips: list[Path], durations: list[float], transitions: list[str], ass: Path | None,
                 offset: float, out: Path, size: tuple[int, int], last: bool) -> Path:
    """Scenes → one silent chunk. clips[i] lasts durations[i] + TRANSITION. transitions[i] goes INTO clip i."""
    W, H = size
    args: list = []
    for c in clips:
        args += ["-i", c]
    parts = [f"[{i}:v]settb=AVTB,fps={FPS},scale={W}:{H},setsar=1,format=yuv420p[v{i}]" for i in range(len(clips))]
    last_label, t = "v0", 0.0
    for i in range(1, len(clips)):
        t += durations[i - 1]
        parts.append(f"[{last_label}][v{i}]xfade=transition={transitions[i]}:duration={TRANSITION:.6f}:"
                     f"offset={t:.6f}[x{i}]")
        last_label = f"x{i}"
    n_frames = frames(sum(durations) + (TRANSITION if last else 0.0))
    chain = f"[{last_label}]trim=end_frame={n_frames}"
    if ass is not None:  # shift time so the whole-video caption file lines up with this chunk
        chain += f",setpts=PTS+{offset:.6f}/TB,{captions.ass_filter(ass)},setpts=PTS-STARTPTS"
    parts.append(chain + ",format=yuv420p[vout]")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.mp4")
    args += ["-filter_complex", ";".join(parts), "-map", "[vout]", *config.encoder_args("final"), "-r", FPS,
             "-an", "-movflags", "+faststart", tmp]
    media.run_ffmpeg(args, "render a part of the video")
    tmp.replace(out)
    return out


def mux(chunks: list[Path], audio: Path, out: Path, total: float, title: str = "") -> Path:
    """Join finished chunks (no re-encoding) and add the audio track."""
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_name(out.stem + "_chunks.txt")
    lst.write_text("".join(f"file '{str(Path(c).resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
                           for c in chunks), encoding="utf-8")
    tmp = out.with_name(out.stem + ".part.mp4")
    media.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-i", audio, "-map", "0:v", "-map", "1:a",
                      "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", 48000, "-t", f"{total:.3f}",
                      "-movflags", "+faststart", "-metadata", f"title={title}",
                      "-metadata", "comment=Contains AI-generated images and voice", tmp], "join the video parts")
    tmp.replace(out)
    lst.unlink(missing_ok=True)
    return out


def chunk_ranges(count: int, size: int | None = None) -> list[tuple[int, int]]:
    size = size or CHUNK_SCENES
    return [(a, min(count, a + size)) for a in range(0, count, size)]


def assemble(clips: list[Path], durations: list[float], transitions: list[str], audio: Path, ass: Path | None,
             out: Path, size: tuple[int, int], title: str = "", work_dir: Path | None = None) -> Path:
    """Everything in one call (chunks go to work_dir)."""
    work_dir = work_dir or out.parent / (out.stem + "_parts")
    chunks, start = [], 0.0
    ranges = chunk_ranges(len(clips))
    for k, (a, b) in enumerate(ranges):
        path = work_dir / f"chunk_{k:03d}.mp4"
        render_chunk(clips[a:b], durations[a:b], transitions[a:b], ass, start, path, size, last=k == len(ranges) - 1)
        chunks.append(path)
        start += sum(durations[a:b])
    return mux(chunks, audio, out, sum(durations) + TRANSITION, title)
