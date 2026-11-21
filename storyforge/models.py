"""Download AI models and check the files before loading them.

Why: a model file copied to Google Drive can end up cut off (a disconnect during
the copy, Drive still syncing). Loading it then fails with errors like
"SafetensorError: header too large". Here every .safetensors file is checked
(header + size); broken files are downloaded again. If a file is still broken,
we stop with a clear message instead of using something else silently.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

from . import config
from .messages import FriendlyError

MAX_HEADER = 100 * 1024 * 1024  # a real safetensors header is a few MB at most


def safetensors_problem(path: Path, expected_size: int | None = None) -> str:
    """'' if the file looks healthy, else a short reason."""
    try:
        size = path.stat().st_size
        if expected_size and size != expected_size:
            return f"wrong size ({size} bytes, expected {expected_size})"
        if size < 8:
            return "file is empty"
        with open(path, "rb") as f:
            (n,) = struct.unpack("<Q", f.read(8))
            if n <= 1 or n > MAX_HEADER or n + 8 > size:
                return f"header too large or cut off ({n} bytes)"
            header = json.loads(f.read(n).decode("utf-8"))
        end = max((v["data_offsets"][1] for k, v in header.items() if k != "__metadata__"), default=0)
        if 8 + n + end > size:
            return "file is cut off (data missing)"
        return ""
    except Exception as exc:  # noqa: BLE001
        return f"unreadable ({type(exc).__name__})"


def _expected_sizes(repo: str) -> dict[str, int]:
    try:
        from huggingface_hub import HfApi  # noqa: PLC0415

        info = HfApi().model_info(repo, files_metadata=True)
        return {s.rfilename: s.size for s in info.siblings if s.size}
    except Exception:  # offline or rate limited: we still check the headers
        return {}


def ensure_model(key: str, rep=None, allow_patterns=None) -> str:
    """Download (or reuse) a model, verify every weights file, re-download broken ones. Returns a local folder."""
    from huggingface_hub import hf_hub_download, snapshot_download  # noqa: PLC0415

    repo = config.MODELS[key]
    cache = config.get().model_cache(key)
    where = "Google Drive" if cache.startswith(str(config.get().root)) else "this Colab session"
    try:
        local = Path(snapshot_download(repo, cache_dir=cache, allow_patterns=allow_patterns))
    except Exception as exc:
        raise FriendlyError(f"Couldn't download the model {repo} ({type(exc).__name__}: {str(exc)[:150]}).",
                            "Check the internet and run again. If it says 401/403, add a free HF_TOKEN secret.") from exc
    sizes = _expected_sizes(repo)
    broken = []
    for f in sorted(local.rglob("*.safetensors")):
        rel = f.relative_to(local).as_posix()
        why = safetensors_problem(f, sizes.get(rel))
        if why:
            broken.append((rel, why))
    for rel, why in broken:
        if rep is not None:
            rep.warn(f"Model file {rel} is broken ({why}). Downloading it again…")
        try:
            path = Path(local / rel)
            path.unlink(missing_ok=True)
            fresh = Path(hf_hub_download(repo, rel, cache_dir=cache, force_download=True))
        except Exception as exc:
            raise FriendlyError(f"Couldn't re-download the broken model file {rel} ({str(exc)[:150]}).",
                                "Check the internet and run again.") from exc
        why2 = safetensors_problem(fresh, sizes.get(rel))
        if why2:
            raise FriendlyError(
                f"The model file {rel} is still broken after downloading it again ({why2}). It is stored in {where}.",
                "Set KEEP_BIG_MODELS_ON_DRIVE to 'no' in cell 2️⃣ (or delete MyDrive/StoryForge/models), "
                "then use Runtime → Disconnect and delete runtime and start again.")
    if broken and rep is not None:
        rep.ok(f"Repaired {len(broken)} model file(s)")
    return str(local)
