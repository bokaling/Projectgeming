"""One-call setup for Colab and Kaggle: system tools + Python packages, with simple messages."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def _run(cmd, quiet=True) -> bool:
    res = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=quiet, text=True)
    return res.returncode == 0


def _pip(*args) -> bool:
    return _run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", *args])


def setup() -> bool:
    t0 = time.time()
    ok = True
    print("📦 1/3 System tools (FFmpeg, espeak-ng)…")
    if not shutil.which("espeak-ng") or not shutil.which("ffmpeg"):
        _run("apt-get -qq update && apt-get -qq install -y espeak-ng ffmpeg > /dev/null 2>&1")
    print("   FFmpeg:", "✅" if shutil.which("ffmpeg") else "❌", "  espeak-ng:", "✅" if shutil.which("espeak-ng") else "⚠️ (optional)")
    print("📦 2/3 Python packages (about 1-3 minutes)…")
    if not _pip("-r", str(REPO_DIR / "requirements.txt")):
        print("   ❌ Some packages failed to install. Run this cell again. If it keeps failing, "
              "use Runtime → Disconnect and delete runtime, then start over.")
        ok = False
    else:
        print("   ✅ Core packages")
    print("📦 3/3 Voice engines (optional)…")
    for pkg, label in (("kokoro>=0.9.4", "Kokoro (English voice)"), ("piper-tts>=1.3", "Piper (offline voices)")):
        print(f"   {'✅' if _pip(pkg) else '⚠️ skipped'} {label}")
    if str(REPO_DIR) not in sys.path:
        sys.path.insert(0, str(REPO_DIR))
    print(f"{'✅' if ok else '⚠️'} Setup finished in {time.time() - t0:.0f} s.")
    return ok
