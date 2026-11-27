"""Series and episode folders on Drive, plus `state.json` for resuming.

How resume works: every finished step is saved in state.json together with a
"fingerprint" (a short hash of everything that step used). When you run again,
a step is skipped if its fingerprint is the same and its files still exist.
Change one scene and only that scene's 3D clip is rendered again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import config

FORMATS = {"9x16": "9:16 (Shorts, TikTok, Reels, Snapchat)", "16x9": "16:9 (YouTube)"}
LANGUAGES = {"en": "English", "fa": "Farsi"}


def dims(fmt: str, resolution: str = "1080p") -> tuple[int, int]:
    """(width, height) for a format key."""
    short, long_ = {"720p": (720, 1280), "480p": (480, 854)}.get(resolution, (1080, 1920))
    return (short, long_) if fmt == "9x16" else (long_, short)


# ---------------------------------------------------------------------------
# JSON helpers (atomic writes so a disconnect never leaves half a file)
# ---------------------------------------------------------------------------


def read_json(path: str | os.PathLike, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: str | os.PathLike, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        path.write_text(text, encoding="utf-8")  # some network drives dislike rename
        tmp.unlink(missing_ok=True)


def fingerprint(*parts) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def slugify(name: str, fallback: str = "series") -> str:
    slug = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower(), flags=re.UNICODE)
    slug = re.sub(r"-{2,}", "-", slug).strip("-_")
    return slug[:60] or fallback


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data = read_json(self.path, None) or {"steps": {}}
        self.data.setdefault("steps", {})

    def fresh(self, key: str, fp: str | None = None, files=()) -> bool:
        """True if `key` finished before with the same fingerprint and its files exist."""
        step = self.data["steps"].get(key)
        if not step:
            return False
        if fp is not None and step.get("fp") != fp:
            return False
        return all(Path(f).exists() for f in files)

    def done(self, key: str, fp: str | None = None, **info) -> None:
        with self._lock:
            self.data["steps"][key] = {"fp": fp, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **info}
            write_json(self.path, self.data)

    def info(self, key: str) -> dict:
        return dict(self.data["steps"].get(key) or {})

    def forget(self, prefix: str) -> None:
        with self._lock:
            for k in [k for k in self.data["steps"] if k == prefix or k.startswith(prefix + ":")]:
                del self.data["steps"][k]
            write_json(self.path, self.data)

    def keys(self, prefix: str = "") -> list[str]:
        return [k for k in self.data["steps"] if k.startswith(prefix)]


# ---------------------------------------------------------------------------
# Episode options (what the user picked on the Idea step)
# ---------------------------------------------------------------------------


SFX_LEVELS = ("off", "subtle", "full")


def sfx_level(value) -> str:
    """off / subtle / full. Old saved options said True (sounds on → subtle) or False (off)."""
    if value is True:
        return "subtle"
    if value is False or value is None:
        return "off"
    v = str(value).strip().lower()
    return v if v in SFX_LEVELS else "subtle"


@dataclass
class EpisodeOptions:
    idea: str = ""  # the topic ("how cow poop becomes electricity") when the AI writes the script
    script_text: str = ""  # your script (or the one the AI wrote)
    source: str = "paste"  # paste = your script, ai = the AI writes it from `idea`
    length: str = "short"  # short = vertical 9:16 1080x1920 (30 s - 3 min), long = 16:9 1920x1080 (8-10 min)
    seconds: int = 0  # target length in seconds; 0 = the format's default (How it works 80 s, documentary 150 s)
    languages: list = field(default_factory=lambda: ["en"])
    formats: list = field(default_factory=lambda: ["9x16"])  # set from `length`
    resolution: str = "1080p"  # or "720p" (faster)
    captions: bool = True  # keyword captions at the top
    music_mood: str = "auto"
    music_volume: float = 0.10  # quiet: music sits well under the voice
    sfx: str = "subtle"  # sound effects: off, subtle (soft whooshes on flights + one soft sound per big moment), full
    creator_note: str = ""
    quick_test: bool = False
    end_card: bool = False  # "Part X 👀" is for story series; explainers end on an overview that loops
    video_format: str = "how_it_works"  # the channel's format (default); auto, what_if, how_made, history, top_list, story
    final_episode: bool = False  # end card says "The End" instead
    quality_check: bool = True  # check one still per scene (Gemini vision if you have a key) and fix

    def __post_init__(self):
        self.sfx = sfx_level(self.sfx)
        self.length = "long" if self.length == "long" else "short"
        self.formats = ["16x9"] if self.length == "long" else ["9x16"]  # short = 9:16, long = 16:9

    @classmethod
    def from_dict(cls, d: dict | None) -> "EpisodeOptions":
        d = d or {}
        known = {f.name for f in fields(cls)}
        opts = cls(**{k: v for k, v in d.items() if k in known})
        opts.languages = [lang for lang in (opts.languages or ["en"]) if lang in LANGUAGES] or ["en"]
        opts.length = "long" if opts.length == "long" else "short"
        opts.formats = ["16x9"] if opts.length == "long" else ["9x16"]
        opts.source = "ai" if opts.source == "ai" else "paste"
        return opts

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def primary_format(self) -> str:
        return self.formats[0]


# ---------------------------------------------------------------------------
# Series and Episode
# ---------------------------------------------------------------------------


DEFAULT_STYLE = "clean low poly 3D, flat colors, soft shadows, dark teal background, glowing grid floor"


class Series:
    def __init__(self, slug: str, root: Path | None = None):
        root = Path(root) if root else config.get().series_dir
        self.slug = slugify(slug)
        self.dir = root / self.slug
        self.path = self.dir / "series.json"
        self.data = read_json(self.path, None) or {}
        self.data.setdefault("name", slug)
        self.data.setdefault("slug", self.slug)
        self.data.setdefault("style", DEFAULT_STYLE)
        self.data.setdefault("characters", [])
        self.data.setdefault("voices", {})
        self.data.setdefault("episodes", {})

    # ---- basics ---------------------------------------------------------
    @classmethod
    def create(cls, name: str, root: Path | None = None) -> "Series":
        s = cls(slugify(name), root)
        s.data["name"] = name.strip() or s.slug
        s.save()
        return s

    def save(self) -> None:
        write_json(self.path, self.data)

    @property
    def name(self) -> str:
        return self.data.get("name") or self.slug

    @property
    def characters(self) -> list[dict]:
        return self.data["characters"]

    def character(self, name: str) -> dict | None:
        key = name.strip().lower()
        for c in self.characters:
            if c.get("name", "").strip().lower() == key:
                return c
        return None

    def char_dir(self, name: str) -> Path:
        return self.dir / "characters" / slugify(name, "character")

    # ---- episodes -------------------------------------------------------
    def episode_numbers(self) -> list[int]:
        nums = []
        ep_root = self.dir / "episodes"
        if ep_root.is_dir():
            for d in ep_root.iterdir():
                m = re.fullmatch(r"ep(\d+)", d.name)
                if m and d.is_dir():
                    nums.append(int(m.group(1)))
        return sorted(nums)

    def next_episode_number(self) -> int:
        nums = self.episode_numbers()
        return (nums[-1] + 1) if nums else 1

    def episode(self, number: int) -> "Episode":
        return Episode(self, int(number))

    def previous_summaries(self, before: int, limit: int = 3) -> list[dict]:
        eps = self.data.get("episodes", {})
        out = []
        for n in sorted((int(k) for k in eps), reverse=True):
            if n < before:
                out.append({"episode": n, **eps[str(n)]})
            if len(out) >= limit:
                break
        return list(reversed(out))

    def remember_episode(self, number: int, **info) -> None:
        self.data["episodes"].setdefault(str(number), {}).update(info)
        self.save()


def list_series(root: Path | None = None) -> list[Series]:
    root = Path(root) if root else config.get().series_dir
    if not root.is_dir():
        return []
    out = [Series(d.name, root) for d in sorted(root.iterdir()) if (d / "series.json").exists()]
    return out


class Episode:
    def __init__(self, series: Series, number: int):
        self.series = series
        self.number = number
        self.dir = series.dir / "episodes" / f"ep{number:02d}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state = State(self.dir / "state.json")

    # ---- names ------------------------------------------------------------
    @property
    def tag(self) -> str:
        return f"ep{self.number:02d}"

    @property
    def script_path(self) -> Path:
        return self.dir / "script.json"

    @property
    def script_md_path(self) -> Path:
        return self.dir / "script.md"

    @property
    def options_path(self) -> Path:
        return self.dir / "episode.json"

    @property
    def export_dir(self) -> Path:
        d = self.dir / "export"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def scene_dir(self, sid: str) -> Path:
        d = self.dir / "scenes" / sid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def audio_dir(self, lang: str) -> Path:
        d = self.dir / "audio" / lang
        d.mkdir(parents=True, exist_ok=True)
        return d

    def captions_dir(self) -> Path:
        d = self.dir / "captions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def clip_path(self, sid: str, fmt: str, lang: str) -> Path:
        return self.dir / "render" / f"{sid}_{fmt}_{lang}.mp4"

    def video_path(self, lang: str, fmt: str) -> Path:
        """Named after the video's own title ('how-an-elevator-works_en_9x16.mp4'), never after an old series."""
        title = slugify(str((self.load_script() or {}).get("title") or ""), "")
        base = title if title else f"{self.series.slug}_{self.tag}"
        return self.export_dir / f"{base}_{lang}_{fmt}.mp4"

    def own_voice_path(self, lang: str) -> Path | None:
        for p in sorted(self.audio_dir(lang).glob("own_voice.*")):
            return p
        return None

    # ---- script + options ---------------------------------------------------
    def load_script(self) -> dict | None:
        return read_json(self.script_path, None)

    def save_script(self, script: dict) -> None:
        write_json(self.script_path, script)

    def load_options(self) -> EpisodeOptions:
        return EpisodeOptions.from_dict((read_json(self.options_path, {}) or {}).get("options"))

    def save_options(self, opts: EpisodeOptions) -> None:
        write_json(self.options_path, {"options": opts.to_dict()})

    # ---- the 3D scene plan ----------------------------------------------------
    @property
    def plan_path(self) -> Path:
        return self.dir / "plan.json"

    def load_plan(self) -> dict | None:
        return read_json(self.plan_path, None)

    def save_plan(self, plan: dict) -> None:
        write_json(self.plan_path, plan)

    def still_path(self, sid: str, fmt: str) -> Path:
        return self.dir / "stills" / f"{sid}_{fmt}.jpg"

    def cleanup_work_files(self) -> int:
        """Delete re-creatable scene clips to save Drive space. Returns MB freed."""
        freed = 0
        for p in list((self.dir / "render").glob("*.mp4")):
            freed += p.stat().st_size
            p.unlink(missing_ok=True)
        self.state.forget("clip")
        return int(freed / 1024**2)
