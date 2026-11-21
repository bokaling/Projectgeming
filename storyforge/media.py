"""Small FFmpeg / FFprobe helpers shared by motion, audio and render."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import config
from .messages import FriendlyError


def run_ffmpeg(args: list[str], what: str = "process the video", timeout: float | None = None) -> None:
    cmd = [config.ffmpeg_path(), "-y", "-hide_banner", "-loglevel", "error", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise FriendlyError(f"FFmpeg couldn't {what}.", "Details: " + " | ".join(tail)[:400])


def probe(path: str | Path) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,duration",
         "-of", "json", str(path)], capture_output=True, text=True,
    )
    try:
        return json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def duration(path: str | Path) -> float:
    info = probe(path)
    try:
        return float(info.get("format", {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def has_audio(path: str | Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


def video_size(path: str | Path) -> tuple[int, int]:
    for s in probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return int(s.get("width") or 0), int(s.get("height") or 0)
    return 0, 0
