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


GL_PACKAGES = "libegl1 libgl1 libgles2 libegl-mesa0 libgl1-mesa-dri"
NVIDIA_EGL = Path("/usr/share/glvnd/egl_vendor.d/10_nvidia.json")


def setup_opengl() -> str:
    """OpenGL without a screen: the NVIDIA GPU through EGL when there is one, else Mesa on the CPU."""
    _run(f"apt-get -qq install -y {GL_PACKAGES} > /dev/null 2>&1 || "
         f"(apt-get -qq update > /dev/null 2>&1 && apt-get -qq install -y {GL_PACKAGES} > /dev/null 2>&1)")
    if shutil.which("nvidia-smi") and not NVIDIA_EGL.exists():  # tell EGL where NVIDIA's driver is
        try:
            NVIDIA_EGL.parent.mkdir(parents=True, exist_ok=True)
            NVIDIA_EGL.write_text('{"file_format_version": "1.0.0", "ICD": {"library_path": "libEGL_nvidia.so.0"}}\n')
        except OSError:
            pass
    ok, out = _run([sys.executable, "-c", "import moderngl; c = moderngl.create_standalone_context(backend='egl'); "
                    "print(c.info['GL_RENDERER'])"])
    return out.strip().splitlines()[-1] if ok and out.strip() else ""


def setup() -> bool:
    t0 = time.time()
    ok = True
    print(f"🐍 Python {sys.version.split()[0]}")
    print("📦 1/4 System tools (FFmpeg, espeak-ng)…")
    if not shutil.which("espeak-ng") or not shutil.which("ffmpeg"):
        _run("apt-get -qq update && apt-get -qq install -y espeak-ng ffmpeg > /dev/null 2>&1")
    print("   FFmpeg:", "✅" if shutil.which("ffmpeg") else "❌", "  espeak-ng:", "✅" if shutil.which("espeak-ng") else "⚠️ (optional)")
    print("📦 2/4 Python packages (about 1-2 minutes)…")
    good, out = _pip("-r", str(REPO_DIR / "requirements.txt"))
    if not good:
        print("   ❌ Some packages failed to install. Run this cell again. If it keeps failing, "
              "use Runtime → Disconnect and delete runtime, then start over.")
        _show_error(out)
        ok = False
    else:
        print("   ✅ Core packages")
    print("🧊 3/4 3D renderer (OpenGL)…")
    gl = setup_opengl()
    if gl:
        where = "GPU" if "llvmpipe" not in gl.lower() else "CPU (no GPU: slower, still works)"
        print(f"   ✅ OpenGL ready on the {where}: {gl[:60]}")
    else:
        print("   ❌ OpenGL didn't start. Run this cell again; if it keeps failing, send the lines above.")
        ok = False
    print("📦 4/4 Voice engines…")
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
