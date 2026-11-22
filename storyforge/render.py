"""Final assembly with FFmpeg: hard cuts, joined WITHOUT re-encoding.

Every scene clip (plus the 1 s cold open and the end card) is already encoded once at final
quality with its captions burned in, and saved to Drive (so a disconnect only loses the clip
being made). The final video = all clips joined (stream copy, a few seconds) + the audio.
Scene lengths are whole frames, so the 3D video and the voice never drift apart.
"""

from __future__ import annotations

from pathlib import Path

from . import media

FPS = 30
TRANSITION = 0.0  # hard cuts (no crossfades)
CHUNK_SCENES = 10


def frames(sec: float) -> int:
    return int(round(sec * FPS))


def snap(sec: float) -> float:
    """Round to a whole frame."""
    return frames(sec) / FPS


def _list_file(clips: list[Path], out: Path) -> Path:
    lst = out.with_name(out.stem + "_clips.txt")
    lst.write_text("".join(f"file '{str(Path(c).resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
                           for c in clips), encoding="utf-8")
    return lst


def mux(clips: list[Path], audio: Path, out: Path, total: float, title: str = "") -> Path:
    """Join finished clips (no re-encoding) and add the audio track."""
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = _list_file(clips, out)
    tmp = out.with_name(out.stem + ".part.mp4")
    media.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst, "-i", audio, "-map", "0:v", "-map", "1:a",
                      "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", 48000, "-t", f"{total:.3f}",
                      "-movflags", "+faststart", "-metadata", f"title={title}",
                      "-metadata", "comment=Low poly 3D animation, AI-assisted voice", tmp], "join the video parts")
    tmp.replace(out)
    lst.unlink(missing_ok=True)
    return out


def chunk_ranges(count: int, size: int | None = None) -> list[tuple[int, int]]:
    size = size or CHUNK_SCENES
    return [(a, min(count, a + size)) for a in range(0, count, size)]
