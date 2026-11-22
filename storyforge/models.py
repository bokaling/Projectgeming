"""Download AI models ONCE, keep them as real files, and check them before loading.

Why this file exists (T4 test, Nov 2026): the Hugging Face cache stores each file as a "symlink"
(a shortcut) to a blob. Google Drive can't keep symlinks: after Colab reconnects, every shortcut
becomes a tiny 79-byte text file that only contains the path of the blob. The old check saw
79 bytes, called the file broken and downloaded it again, every session.

Now:
* Models are saved as real files in  <models>/files/<org>--<name>/  (no symlinks, works on Drive).
* An old cache (with shortcuts or 79-byte stubs) is moved into that folder once (a fast rename,
  nothing is downloaded again) and the old cache is removed.
* After a successful check we write .storyforge_verified.json. The next session only checks that
  every file is still there with the same size: no internet, no download, a few seconds.
* A file is only downloaded again if it is really missing or really broken.
* HF_TOKEN (Colab secret) is used for every download.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import struct
import time
from pathlib import Path

from . import config
from .messages import FriendlyError

MAX_HEADER = 100 * 1024 * 1024  # a real safetensors header is a few MB at most
MARKER = ".storyforge_verified.json"
STUB = re.compile(r"^(?:\.\./)+blobs/([0-9a-f]{40,64})\s*$")  # a Drive "symlink stub": the blob's path as text
LFS = b"version https://git-lfs"
# files we never need
IGNORE = {
    "image": ["*.gguf", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.mp4"],
    "i2v": ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.mp4", "assets/*", "examples/*"],
    "kokoro": ["*.png", "*.jpg", "*.md", "samples/*", "*.wav"],
}


# ---------------------------------------------------------------------------
# What is really behind a path
# ---------------------------------------------------------------------------


def _token() -> str | None:
    return config.secret("HF_TOKEN")


def stub_target(path: Path) -> Path | None:
    """If `path` is a symlink or a Drive 'symlink stub' (79-byte text file), the blob it points to."""
    p = Path(path)
    try:
        if p.is_symlink():
            return p.resolve()
        if p.is_file() and p.stat().st_size < 400:
            text = p.read_bytes()[:400].decode("ascii", "ignore").strip()
            if STUB.match(text):
                return (p.parent / text).resolve()
    except OSError:
        return None
    return None


def real_file(path: Path) -> Path | None:
    """The real file behind a path (follows symlinks and Drive stubs). None if there is no real file."""
    p = Path(path)
    target = stub_target(p)
    if target is not None:
        return target if target.is_file() and not stub_target(target) else None
    return p if p.is_file() else None


def file_problem(path: Path, expected_size: int | None = None) -> str:
    """'' if the file is a healthy REAL file, else a short reason (checks the real blob, never the link)."""
    p = Path(path)
    if stub_target(p) is not None:
        return "only a link to the real file (Google Drive can't keep those)"
    if not p.is_file():
        return "missing"
    try:
        size = p.stat().st_size
        if expected_size and size != expected_size:
            return f"wrong size ({size} bytes, expected {expected_size})"
        with open(p, "rb") as f:
            head = f.read(64)
        if head.startswith(LFS):
            return "a download pointer, not the real file"
        if p.suffix == ".safetensors":
            return safetensors_problem(p)
        if size == 0 and not expected_size:
            return "file is empty"
        return ""
    except OSError as exc:
        return f"unreadable ({type(exc).__name__})"


def safetensors_problem(path: Path, expected_size: int | None = None) -> str:
    """'' if the .safetensors file looks healthy, else a short reason. Follows links to the real file."""
    real = real_file(Path(path))
    if real is None:
        return "missing (the link points nowhere)"
    try:
        size = real.stat().st_size
        if expected_size and size != expected_size:
            return f"wrong size ({size} bytes, expected {expected_size})"
        if size < 8:
            return "file is empty"
        with open(real, "rb") as f:
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


def _ignore_patterns(key: str, repo: str) -> list[str] | None:
    """Files to skip. FLUX: the single-file checkpoint at the top is skipped ONLY if the transformer/ folder
    (the one the app loads) is there too: that saves ~8 GB and never removes something we need."""
    pats = list(IGNORE.get(key, []))
    if key == "image":
        try:
            from huggingface_hub import HfApi  # noqa: PLC0415

            names = HfApi(token=_token()).list_repo_files(repo)
            if any(n.startswith("transformer/") and n.endswith(".safetensors") for n in names):
                pats += [n for n in names if "/" not in n and n.endswith(".safetensors")]
        except Exception:  # noqa: BLE001 - offline: download everything, to be safe
            pass
    return pats or None


def _expected_sizes(repo: str) -> dict[str, int]:
    try:
        from huggingface_hub import HfApi  # noqa: PLC0415

        info = HfApi(token=_token()).model_info(repo, files_metadata=True)
        return {s.rfilename: s.size for s in info.siblings if s.size}
    except Exception:  # offline or rate limited: we still check the files themselves
        return {}


# ---------------------------------------------------------------------------
# Folders and the "verified" marker
# ---------------------------------------------------------------------------


def model_dir(key: str) -> Path:
    repo = config.MODELS[key]
    return Path(config.get().model_cache(key)) / "files" / repo.replace("/", "--")


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if (p.is_file() or p.is_symlink()) and ".cache" not in p.parts
                  and p.name != MARKER)


def _set_key(allow_patterns) -> str:
    return json.dumps(sorted(allow_patterns)) if allow_patterns else "all"


def _read_marker(folder: Path) -> dict:
    try:
        return json.loads((folder / MARKER).read_text())
    except Exception:  # noqa: BLE001
        return {}


def _write_marker(folder: Path, key: str, files: dict[str, int]) -> None:
    data = _read_marker(folder)
    data.setdefault("sets", {})[key] = {"files": files, "checked": time.strftime("%Y-%m-%d %H:%M")}
    tmp = folder / (MARKER + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(folder / MARKER)


def _still_good(folder: Path, files: dict[str, int]) -> bool:
    """Quick check without internet: every file is a real file with the size it had when it was verified."""
    for rel, size in files.items():
        p = folder / rel
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size != size:
                return False
            if p.suffix == ".safetensors" and safetensors_problem(p, size):
                return False
        except OSError:
            return False
    return bool(files)


# ---------------------------------------------------------------------------
# One-time move from the old Hugging Face cache (symlinks / Drive stubs) to real files
# ---------------------------------------------------------------------------


def _write_hf_metadata(folder: Path, rel: str, commit: str, etag: str) -> None:
    """Tell huggingface_hub the moved file is up to date (so it doesn't hash 16 GB again)."""
    try:
        from huggingface_hub._local_folder import write_download_metadata  # noqa: PLC0415

        write_download_metadata(local_dir=folder, filename=rel, commit_hash=commit, etag=etag)
    except Exception:  # noqa: BLE001 - only an optimisation
        pass


def migrate_old_cache(key: str, rep=None) -> int:
    """Move files from the old cache layout (models--org--name/…) into real files. Returns how many."""
    repo = config.MODELS[key]
    cache = Path(config.get().model_cache(key))
    old = cache / ("models--" + repo.replace("/", "--"))
    snaps = old / "snapshots"
    if not snaps.is_dir():
        return 0
    target = model_dir(key)
    moved_blobs: dict[Path, Path] = {}
    count = 0
    commits = sorted((d for d in snaps.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
    for snap in commits[:1]:
        for f in sorted(p for p in snap.rglob("*") if p.is_file() or p.is_symlink()):
            rel = f.relative_to(snap).as_posix()
            dst = target / rel
            if dst.is_file() and not stub_target(dst):
                continue
            blob = stub_target(f)
            src = blob if blob is not None else f
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src in moved_blobs and moved_blobs[src].is_file():
                    shutil.copyfile(moved_blobs[src], dst)  # two names, one blob
                elif src.is_file() and not stub_target(src):
                    shutil.move(str(src), str(dst))  # a rename on the same drive: instant
                    moved_blobs[src] = dst
                else:
                    continue  # nothing real behind it: it will be downloaded
                if blob is not None and blob.parent.name == "blobs":
                    _write_hf_metadata(target, rel, snap.name, blob.name)
                count += 1
            except OSError:
                continue
    shutil.rmtree(old, ignore_errors=True)
    if count and rep is not None:
        rep.ok(f"Moved {count} model file(s) of {repo} to real files (no download needed)")
    return count


# ---------------------------------------------------------------------------
# The public functions
# ---------------------------------------------------------------------------


def ensure_model(key: str, rep=None, allow_patterns=None) -> str:
    """Get a model as real files (download only what is missing or broken). Returns the local folder."""
    repo = config.MODELS[key]
    target = model_dir(key)
    set_key = _set_key(allow_patterns)
    known = _read_marker(target).get("sets", {}).get(set_key, {}).get("files") or {}
    if known and _still_good(target, known):
        return str(target)  # verified before and unchanged: no internet needed
    target.mkdir(parents=True, exist_ok=True)
    migrate_old_cache(key, rep)
    from huggingface_hub import hf_hub_download, snapshot_download  # noqa: PLC0415

    where = "Google Drive" if str(target).startswith(str(config.get().root)) else "this Colab session"
    try:
        snapshot_download(repo, local_dir=str(target), allow_patterns=allow_patterns,
                          ignore_patterns=_ignore_patterns(key, repo), token=_token())
    except Exception as exc:
        have = [p for p in _files(target) if not file_problem(p)]
        if not have or (allow_patterns and not all(any(fnmatch.fnmatch(p.relative_to(target).as_posix(), pat)
                                                           for p in have) for pat in allow_patterns)):
            raise FriendlyError(f"Couldn't download the model {repo} ({type(exc).__name__}: {str(exc)[:150]}).",
                                "Check the internet and run again. If it says 401/403, add a free HF_TOKEN "
                                "secret.") from exc
        if rep is not None:
            rep.warn(f"Couldn't check {repo} online ({type(exc).__name__}); using the files you already have.")
    sizes = _expected_sizes(repo)
    files = [p for p in _files(target) if not allow_patterns
             or any(fnmatch.fnmatch(p.relative_to(target).as_posix(), pat) for pat in allow_patterns)]
    broken = [(p.relative_to(target).as_posix(), why) for p in files
              if (why := file_problem(p, sizes.get(p.relative_to(target).as_posix())))]
    for rel, why in broken:
        if rep is not None:
            rep.warn(f"Model file {rel} is broken ({why}). Downloading only this file again…")
        try:
            (target / rel).unlink(missing_ok=True)
            fresh = Path(hf_hub_download(repo, rel, local_dir=str(target), force_download=True, token=_token()))
        except Exception as exc:
            raise FriendlyError(f"Couldn't re-download the broken model file {rel} ({str(exc)[:150]}).",
                                "Check the internet and run again.") from exc
        why2 = file_problem(fresh, sizes.get(rel))
        if why2:
            raise FriendlyError(
                f"The model file {rel} is still broken after downloading it again ({why2}). It is stored in {where}.",
                "Set KEEP_BIG_MODELS_ON_DRIVE to 'no' in cell 2️⃣ (or delete MyDrive/StoryForge/models), "
                "then use Runtime → Disconnect and delete runtime and start again.")
    if broken and rep is not None:
        rep.ok(f"Repaired {len(broken)} model file(s)")
    good = {p.relative_to(target).as_posix(): p.stat().st_size for p in files if p.is_file() and not p.is_symlink()}
    if good:
        _write_marker(target, set_key, good)
    return str(target)


def ensure_file(key: str, filename: str, rep=None) -> str:
    """One file of a model repo (e.g. a Kokoro voice), as a real checked file. Returns its path."""
    folder = ensure_model(key, rep, allow_patterns=[filename])
    path = Path(folder) / filename
    if file_problem(path):
        raise FriendlyError(f"Couldn't get {filename} from {config.MODELS[key]} ({file_problem(path)}).",
                            "Check the internet and run again.")
    return str(path)
