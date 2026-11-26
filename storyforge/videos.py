"""📂 Your finished videos in ONE easy folder: MyDrive/StoryForge Videos.

Every finished video is copied there as "2026-11-23 How an elevator works (Short 9x16).mp4", with a matching .txt
(title, description, hashtags and ready captions for YouTube, TikTok, Instagram, Facebook) and the thumbnail .jpg.
The project folders stay as they are (resume, fixing a shot). "Posted ✅" moves a video into the Posted folder.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from . import config

FOLDER = "StoryForge Videos"
POSTED = "Posted"


def folder() -> Path:
    """MyDrive/StoryForge Videos on Colab (next to MyDrive/StoryForge), else next to the StoryForge folder."""
    root = Path(config.get().root)
    out = root.parent / FOLDER
    out.mkdir(parents=True, exist_ok=True)
    return out


def drive_link(path: Path | None = None) -> str:
    """A clickable Google Drive link to the folder (Colab: the folder's Drive id), or '' when it isn't on Drive."""
    p = Path(path or folder())
    if not str(p).startswith("/content/drive"):
        return ""
    for cmd in (["xattr", "-p", "user.drive.id", str(p)], ["getfattr", "--only-values", "-n", "user.drive.id", str(p)]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            fid = out.stdout.strip()
            if out.returncode == 0 and re.fullmatch(r"[\w-]{10,}", fid):
                return f"https://drive.google.com/drive/folders/{fid}"
        except Exception:  # noqa: BLE001
            continue
    return "https://drive.google.com/drive/my-drive"


def nice_name(title: str, fmt: str, lang: str = "en", day: date | None = None) -> str:
    """'2026-11-23 How an elevator works (Short 9x16)' (safe for every file system)."""
    t = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", title or "My video").strip()
    t = re.sub(r"\s+", " ", t)[:80] or "My video"
    kind = "Short 9x16" if fmt == "9x16" else "Long 16x9"
    return f"{(day or date.today()).isoformat()} {t} ({kind}{', Farsi' if lang == 'fa' else ''})"


def captions_text(title: str, meta: dict) -> str:
    """Ready-to-paste text for YouTube, TikTok, Instagram and Facebook."""
    titles = meta.get("titles") or [title]
    desc = str(meta.get("description") or "").strip()
    tags = meta.get("hashtags") or {}
    yt, tt, ig = (" ".join(tags.get(k, [])[:n]) for k, n in (("youtube", 5), ("tiktok", 5), ("instagram", 10)))
    first = desc.split("\n\n")[0] if desc else title
    out = [f"TITLE: {titles[0]}", ""]
    if len(titles) > 1:
        out += ["Other title ideas:"] + [f"- {t}" for t in titles[1:]] + [""]
    out += ["===== YouTube (Shorts) =====", f"Title: {titles[0]}", "Description:", desc, "", f"Hashtags: {yt}", "",
            "===== TikTok =====", f"{titles[0]} {tt}".strip(), "",
            "===== Instagram (Reels) =====", f"{first}", "", ig, "",
            "===== Facebook (Reels) =====", f"{titles[0]}", "", desc, ""]
    return "\n".join(out).strip() + "\n"


def add(video: Path, title: str, fmt: str, lang: str, meta: dict, thumbnail: Path | None = None,
        day: date | None = None) -> Path:
    """Copy a finished video (+ .txt + thumbnail .jpg) into the folder. Returns the new video path.
    Made again (same title, same day): the old copy is replaced, never a second copy."""
    base = nice_name(title, fmt, lang, day)
    dst = folder()
    out = dst / f"{base}.mp4"
    tmp = out.with_name(out.name + ".part")
    shutil.copyfile(video, tmp)
    tmp.replace(out)
    (dst / f"{base}.txt").write_text(captions_text(title, meta), encoding="utf-8")
    if thumbnail and Path(thumbnail).exists():
        shutil.copyfile(thumbnail, dst / f"{base}.jpg")
    return out


def mark_posted(video: Path) -> Path:
    """Move the video (+ its .txt and .jpg) into 'StoryForge Videos/Posted'."""
    video = Path(video)
    posted = video.parent / POSTED
    posted.mkdir(parents=True, exist_ok=True)
    for ext in (".mp4", ".txt", ".jpg"):
        src = video.with_suffix(ext)
        if src.exists():
            shutil.move(str(src), str(posted / src.name))
    return posted / video.name


def listing() -> list[Path]:
    """Videos in the folder that are not posted yet (newest first)."""
    try:
        return sorted(folder().glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
