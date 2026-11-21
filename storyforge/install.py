"""One-call setup for Colab and Kaggle: system tools + Python packages, with simple messages.

If something fails, the real error is printed (last lines of pip's output), so it can be fixed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent

# Kokoro (the English narrator). Why these pins:
# * Every Kokoro release from 0.8 says "Python < 3.13", so pip refuses it on a Python 3.13 runtime.
#   It works fine on 3.13 (tested), so we install it with --ignore-requires-python.
# * misaki[en] pulls spacy-curated-transformers; its newest version needs thinc 9 while spacy needs
#   thinc < 8.4. Without pins pip backtracks to an old spacy/thinc and tries to compile them (fails).
KOKORO_PACKAGES = [
    "kokoro>=0.9.4", "misaki[en]>=0.9.4", "spacy>=3.8,<3.9", "thinc>=8.3,<8.4",
    "spacy-curated-transformers>=0.2,<0.4",
]
KOKORO_CHECK = (
    "from kokoro import KPipeline, KModel\n"
    "from misaki import en\n"
    "ps, _ = en.G2P(trf=False, british=False, fallback=None)('Ready to tell a story.')\n"
    "assert ps, 'no phonemes'\n"
    "print('ok')\n"
)


def _run(cmd) -> tuple[bool, str]:
    res = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True)
    return res.returncode == 0, (res.stdout or "") + (res.stderr or "")


def _pip(*args) -> tuple[bool, str]:
    return _run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", *args])


def _show_error(output: str, lines: int = 15) -> None:
    """Print the useful end of an error (pip output or a Python traceback)."""
    tail = [ln for ln in output.strip().splitlines() if ln.strip()][-lines:]
    print(f"      Python {sys.version.split()[0]} · error details:")
    for ln in tail:
        print("      │ " + ln[:220])


def install_kokoro() -> bool:
    ok, out = _pip("--ignore-requires-python", *KOKORO_PACKAGES)
    if not ok:
        print("   ❌ Kokoro (English narrator) failed to install.")
        _show_error(out)
        return False
    # Real check: import it and turn text into phonemes (also downloads the small English language model now)
    ok, out = _run([sys.executable, "-c", KOKORO_CHECK])
    if not ok:
        print("   ❌ Kokoro installed but doesn't start.")
        _show_error(out)
        return False
    print("   ✅ Kokoro (English narrator)")
    return True


def setup() -> bool:
    t0 = time.time()
    ok = True
    print(f"🐍 Python {sys.version.split()[0]}")
    print("📦 1/3 System tools (FFmpeg, espeak-ng)…")
    if not shutil.which("espeak-ng") or not shutil.which("ffmpeg"):
        _run("apt-get -qq update && apt-get -qq install -y espeak-ng ffmpeg > /dev/null 2>&1")
    print("   FFmpeg:", "✅" if shutil.which("ffmpeg") else "❌", "  espeak-ng:", "✅" if shutil.which("espeak-ng") else "⚠️ (optional)")
    print("📦 2/3 Python packages (about 1-3 minutes)…")
    good, out = _pip("-r", str(REPO_DIR / "requirements.txt"))
    if not good:
        print("   ❌ Some packages failed to install. Run this cell again. If it keeps failing, "
              "use Runtime → Disconnect and delete runtime, then start over.")
        _show_error(out)
        ok = False
    else:
        print("   ✅ Core packages")
    if good and subprocess.run([sys.executable, "-c", "from PIL import features; assert features.check('avif')"],
                               capture_output=True, check=False).returncode != 0:
        _pip("pillow-avif-plugin")  # older Pillow can't open .avif pictures by itself
    print("📦 3/3 Voice engines…")
    if not install_kokoro():
        print("      👉 Videos still work with the Edge TTS male voice. Copy the lines above and send them for a fix.")
    good, out = _pip("piper-tts>=1.3")
    if good:
        print("   ✅ Piper (offline backup voices)")
    else:
        print("   ⚠️ Piper (offline backup voices) skipped:")
        _show_error(out, 6)
    if str(REPO_DIR) not in sys.path:
        sys.path.insert(0, str(REPO_DIR))
    print(f"{'✅' if ok else '⚠️'} Setup finished in {time.time() - t0:.0f} s.")
    return ok
