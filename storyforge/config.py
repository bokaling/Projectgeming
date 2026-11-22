"""Settings, folders, platform detection (Colab / Kaggle / local), GPU check and secrets.

Nothing heavy is imported here, so `import storyforge` stays fast.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
ASSETS_DIR = REPO_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

# Optional free API keys. The app works with none of them.
SECRET_NAMES = [
    "GEMINI_API_KEY",  # aistudio.google.com  (free, no card)
    "GROQ_API_KEY",  # console.groq.com     (free, no card)
    "OPENROUTER_API_KEY",  # openrouter.ai     (free models only)
    "HF_TOKEN",  # huggingface.co        (faster, more reliable model downloads)
    "FREESOUND_API_KEY",  # freesound.org     (CC0 sound effects)
    "AIHORDE_API_KEY",  # aihorde.net          (higher priority in the free queue)
]

# Model ids (all permissive licenses, see research.md section 14).
MODELS = {
    "image": "black-forest-labs/FLUX.2-klein-4B",  # Apache 2.0
    "depth": "depth-anything/Depth-Anything-V2-Small-hf",  # Apache 2.0 (Small only!)
    "i2v": "Wan-AI/Wan2.2-TI2V-5B-Diffusers",  # Apache 2.0
    "kokoro": "hexgrad/Kokoro-82M",  # Apache 2.0
    "align_en": "facebook/wav2vec2-base-960h",  # Apache 2.0
    "align_fa": "jonatasgrosman/wav2vec2-large-xlsr-53-persian",  # Apache 2.0
    "local_llm": "Qwen/Qwen3-4B-Instruct-2507",  # Apache 2.0
    "piper_voices": "rhasspy/piper-voices",
}
_START = time.time()
BIG_MODELS_GB = 45  # klein (~16 GB) + Wan 2.2 5B (~25 GB) + margin

# Models small enough to keep on free Google Drive (15 GB).
SMALL_MODELS = {"depth", "kokoro", "align_en", "align_fa", "piper_voices"}


@dataclass
class GPUInfo:
    available: bool = False
    name: str = ""
    vram_gb: float = 0.0

    @property
    def label(self) -> str:
        if not self.available:
            return "No GPU (online + CPU mode)"
        return f"{self.name} ({self.vram_gb:.0f} GB)"


@dataclass
class GPUProfile:
    """Settings that depend on the GPU Colab gave you."""

    name: str = "CPU"
    dtype: str = "fp32"  # fp16 on T4 (no bf16), bf16 on L4/A100
    image_max_side: int = 1280  # long side of generated pictures
    keep_text_encoder: bool = False  # enough VRAM to keep the prompt reader loaded
    heroes_short: int = 0  # real image-to-video scenes (auto)
    heroes_long: int = 0
    wan_sizes: dict = field(default_factory=lambda: {"9x16": (480, 832), "16x9": (832, 480)})
    wan_frames: int = 81
    wan_steps: int = 20
    hero_minutes: float = 15.0
    cu_per_hour: float = 0.1  # Colab compute units per hour (unofficial user measurements, Nov 2026)
    workers: int = 1  # parallel scene-motion renders (CPU cores)

    @property
    def label(self) -> str:
        return f"{self.name} · ~{self.cu_per_hour:g} units/h"


def _workers() -> int:
    cpu = os.cpu_count() or 2
    return 1 if cpu <= 2 else min(6, cpu - 1)


def gpu_profile(gpu: "GPUInfo | None" = None) -> GPUProfile:
    gpu = gpu or get().gpu
    w = _workers()
    if not gpu.available:
        return GPUProfile(workers=w)
    name, vram = gpu.name.upper(), gpu.vram_gb
    if "A100" in name or "H100" in name or vram >= 38:
        big = vram >= 70
        return GPUProfile(name="A100 80GB" if big else ("H100" if "H100" in name else "A100"), dtype="bf16",
                          image_max_side=1920, keep_text_encoder=True, heroes_short=5, heroes_long=10,
                          wan_sizes={"9x16": (704, 1280), "16x9": (1280, 704)}, wan_frames=81, wan_steps=30,
                          hero_minutes=10.0, cu_per_hour=7.5 if big else 5.4, workers=w)
    if "L4" in name or vram >= 21:
        return GPUProfile(name="L4", dtype="bf16", image_max_side=1536, keep_text_encoder=True, heroes_short=3,
                          heroes_long=6, wan_frames=81, wan_steps=25, hero_minutes=12.0, cu_per_hour=1.7, workers=w)
    return GPUProfile(name="T4" if "T4" in name else gpu.name, dtype="fp16", image_max_side=1344,
                      keep_text_encoder=False, heroes_short=1, heroes_long=2, wan_frames=81, wan_steps=20,
                      hero_minutes=15.0, cu_per_hour=1.2, workers=w)


def session_seconds() -> float:
    """How long this Colab/Kaggle machine has been running (its uptime)."""
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        return time.time() - _START


def session_label() -> str:
    sec = int(session_seconds())
    h, m = divmod(sec // 60, 60)
    prof = gpu_profile()
    units = sec / 3600 * prof.cu_per_hour
    return f"⏱ {h}:{m:02d} · ≈{units:.1f} units ({prof.name}, ~{prof.cu_per_hour:g}/h)"


@dataclass
class Settings:
    root: Path
    platform: str
    gpu: GPUInfo = field(default_factory=GPUInfo)
    cache_big_models_on_drive: bool = False
    drive_mounted: bool = False

    # ---- folders -------------------------------------------------------
    @property
    def series_dir(self) -> Path:
        return self.root / "series"

    @property
    def library_dir(self) -> Path:
        return self.root / "library"

    @property
    def music_dir(self) -> Path:
        return self.library_dir / "music"

    @property
    def sfx_dir(self) -> Path:
        return self.library_dir / "sfx"

    @property
    def small_model_cache(self) -> Path:
        return self.root / "models"

    @property
    def big_model_cache(self) -> Path:
        if self.cache_big_models_on_drive:
            return self.root / "models"
        return local_cache_dir(self.platform) / "models"

    @property
    def temp_dir(self) -> Path:
        return local_cache_dir(self.platform) / "tmp"

    def model_cache(self, key: str) -> str:
        path = self.small_model_cache if key in SMALL_MODELS else self.big_model_cache
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def ensure_dirs(self) -> None:
        for d in (self.series_dir, self.music_dir, self.sfx_dir, self.small_model_cache, self.temp_dir):
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def detect_platform() -> str:
    if "google.colab" in sys.modules or os.environ.get("COLAB_RELEASE_TAG"):
        return "colab"
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle/working").is_dir():
        return "kaggle"
    return "local"


def local_cache_dir(platform: str) -> Path:
    if platform == "colab":
        return Path("/content/sf_cache")
    if platform == "kaggle":
        return Path("/kaggle/tmp/sf_cache") if Path("/kaggle/tmp").is_dir() else Path("/tmp/sf_cache")
    return Path(os.environ.get("STORYFORGE_CACHE", Path.home() / ".cache" / "storyforge"))


def default_root(platform: str) -> tuple[Path, bool]:
    """Return (project root, saved_to_drive)."""
    env = os.environ.get("STORYFORGE_HOME")
    if env:
        return Path(env), env.startswith("/content/drive")
    if platform == "colab":
        drive = Path("/content/drive/MyDrive")
        if drive.is_dir():
            return drive / "StoryForge", True
        return Path("/content/StoryForge"), False
    if platform == "kaggle":
        return Path("/kaggle/working/StoryForge"), False
    return Path.home() / "StoryForge", False


# ---------------------------------------------------------------------------
# GPU
# ---------------------------------------------------------------------------


def detect_gpu() -> GPUInfo:
    if os.environ.get("STORYFORGE_FORCE_CPU") == "1":
        return GPUInfo(False)
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run(
                [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            if out:
                first = out.splitlines()[0]
                name, mem = [p.strip() for p in first.split(",")[:2]]
                return GPUInfo(True, name, float(mem) / 1024.0)
        except Exception:
            pass
    try:  # torch might see a GPU even if nvidia-smi is missing
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return GPUInfo(True, props.name, props.total_memory / 1024**3)
    except Exception:
        pass
    return GPUInfo(False)


# ---------------------------------------------------------------------------
# Secrets (optional free API keys)
# ---------------------------------------------------------------------------


# What each free key turns on (shown in the log and in the app).
KEY_FEATURES = {
    "GEMINI_API_KEY": "Gemini (free): ✨ Improve script, picture prompts, titles and descriptions, Farsi translation",
    "GROQ_API_KEY": "Groq (free): backup AI writer when Gemini is busy",
    "OPENROUTER_API_KEY": "OpenRouter free models: second backup AI writer",
    "HF_TOKEN": "Hugging Face: faster, more reliable model downloads (FLUX, Wan, Kokoro, depth)",
    "FREESOUND_API_KEY": "Freesound: extra CC0 sound effects",
    "AIHORDE_API_KEY": "AI Horde: faster online pictures when there is no GPU",
}
_SECRET_STATUS: dict[str, str] = {}


def _colab_secret(name: str) -> str | None:
    try:
        from google.colab import userdata  # type: ignore  # noqa: PLC0415
    except Exception:  # not on Colab
        return None
    try:
        value = userdata.get(name) or None
        if value:
            _SECRET_STATUS[name] = "found"
        return value
    except Exception as exc:  # noqa: BLE001 - missing, or "Notebook access" is off for this notebook
        kind = type(exc).__name__
        if "Access" in kind or "access" in str(exc).lower():
            _SECRET_STATUS[name] = "no_access"
        elif "Timeout" in kind:
            _SECRET_STATUS[name] = "timeout"
        return None


def _kaggle_secret(name: str) -> str | None:
    try:
        from kaggle_secrets import UserSecretsClient  # type: ignore  # noqa: PLC0415

        return UserSecretsClient().get_secret(name) or None
    except Exception:
        return None


def load_secrets() -> dict[str, bool]:
    """Copy optional keys from Colab/Kaggle secrets into this process's environment.

    Call it once from the notebook's main thread (Colab secrets don't work from
    background threads). Keys are never printed or saved to disk.
    Returns {name: found}.
    """
    found = {}
    for name in SECRET_NAMES:
        value = os.environ.get(name) or _colab_secret(name) or _kaggle_secret(name)
        if value:
            os.environ[name] = value.strip()
        found[name] = bool(value)
    if os.environ.get("HF_TOKEN"):
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", os.environ["HF_TOKEN"])
    return found


def key_report() -> list[tuple[str, str, str]]:
    """[(name, status, what it turns on)]. status: found / missing / no_access (in Secrets but access is off)."""
    out = []
    for name in SECRET_NAMES:
        if os.environ.get(name):
            status = "found"
        else:
            status = _SECRET_STATUS.get(name, "missing")
        out.append((name, status, KEY_FEATURES.get(name, "")))
    return out


def key_lines() -> list[str]:
    """Simple lines for the log: which keys were found and what each one turns on."""
    lines = []
    for name, status, what in key_report():
        if status == "found":
            lines.append(f"   ✅ {name} → {what}")
        elif status == "no_access":
            lines.append(f"   ⚠️ {name} is in Colab Secrets but 'Notebook access' is OFF: switch it on (🔑 on the left), "
                         "then run cell 2️⃣ again")
        elif name in ("GEMINI_API_KEY", "HF_TOKEN"):
            lines.append(f"   ➖ {name} not set (optional) → would turn on: {what}")
    return lines


def secret(name: str) -> str | None:
    return os.environ.get(name) or None


# ---------------------------------------------------------------------------
# FFmpeg capabilities
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FileNotFoundError("ffmpeg")
    return path


@lru_cache(maxsize=1)
def video_encoder() -> str:
    """'h264_nvenc' if it really works on this machine, else 'libx264'."""
    try:
        cmd = [
            ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=black:s=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-",
        ]
        if subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0:
            return "h264_nvenc"
    except Exception:
        pass
    return "libx264"


def encoder_args(quality: str = "final") -> list[str]:
    """FFmpeg video encoder arguments. 'final' = upload quality, 'work' = fast intermediate.

    Every scene clip is encoded ONCE at final quality with the same settings, so the clips can be
    joined without re-encoding (GPU encoder h264_nvenc when it works, else libx264).
    """
    enc = video_encoder()
    gop = ["-g", "60", "-bf", "2"]
    if enc == "h264_nvenc":
        cq = "20" if quality == "final" else "21"
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", cq, "-b:v", "0", *gop,
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    if quality == "final":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", *gop, "-profile:v", "high",
                "-x264-params", "stitchable=1", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p"]


# ---------------------------------------------------------------------------
# Global settings object
# ---------------------------------------------------------------------------

_SETTINGS: Settings | None = None


NOISE = re.compile(r"torchao|serve_kernel_port_as_iframe|cpp extensions|TRANSFORMERS_CACHE|symlinks|"
                   r"resume_download|torch\.utils\._pytree|weight_norm|dropout option adds dropout|"
                   r"upgrade_state_dict|`torch_dtype` is deprecated|Torch was not compiled with flash attention")


class _QuietFilter:
    """Drops harmless library chatter (torchao, Colab iframe notice) from the log."""

    def filter(self, record) -> bool:
        try:
            return not NOISE.search(record.getMessage())
        except Exception:  # noqa: BLE001
            return True


def quiet_warnings() -> None:
    """Hide harmless warnings (torch UserWarning/FutureWarning, torchao, Colab iframe notice). Real errors still show."""
    import logging  # noqa: PLC0415
    import warnings  # noqa: PLC0415

    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    for mod in ("torch", "torchvision", "torchaudio", "torchao", "diffusers", "transformers", "huggingface_hub",
                "kokoro", "misaki", "spacy", "thinc", "gradio", "google.colab", "accelerate", "librosa", "phonemizer"):
        warnings.filterwarnings("ignore", category=UserWarning, module=mod.replace(".", r"\.") + r"(\.|$)")
    warnings.filterwarnings("ignore", message=r".*(torchao|serve_kernel_port_as_iframe|symlink).*")
    for name in ("torchao", "diffusers", "transformers", "huggingface_hub", "accelerate", "httpx", "phonemizer"):
        logging.getLogger(name).setLevel(logging.ERROR)
    flt = _QuietFilter()
    for lg in (logging.getLogger(), logging.getLogger("torchao"), logging.getLogger("py.warnings")):
        lg.addFilter(flt)
        for h in lg.handlers:
            h.addFilter(flt)
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("DIFFUSERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("PYTHONWARNINGS", "ignore::FutureWarning,ignore::UserWarning,ignore::DeprecationWarning")


def init(root: str | os.PathLike | None = None, cache_big_models_on_drive: bool | str = "auto") -> Settings:
    """Create (or replace) the global settings. Safe to call more than once.

    cache_big_models_on_drive: True / False / "auto" (= yes if your Drive has enough free space).
    """
    global _SETTINGS
    quiet_warnings()
    platform = detect_platform()
    if root:
        root_path, on_drive = Path(root), str(root).startswith("/content/drive")
    else:
        root_path, on_drive = default_root(platform)
    if cache_big_models_on_drive in ("auto", None):
        cache_big = on_drive and free_disk_gb(root_path) >= BIG_MODELS_GB
    else:
        cache_big = str(cache_big_models_on_drive).lower() in ("true", "yes", "1", "on")
    s = Settings(
        root=root_path,
        platform=platform,
        gpu=detect_gpu(),
        cache_big_models_on_drive=bool(cache_big),
        drive_mounted=on_drive,
    )
    s.ensure_dirs()
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    _SETTINGS = s
    return s


def get() -> Settings:
    return _SETTINGS if _SETTINGS is not None else init()


def free_disk_gb(path: str | os.PathLike) -> float:
    try:
        p = Path(path)
        while not p.exists() and p != p.parent:
            p = p.parent
        return shutil.disk_usage(p).free / 1024**3
    except Exception:
        return 0.0
