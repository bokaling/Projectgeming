"""Gemini images mode: you make the pictures in the Gemini app (Nano Banana), StoryForge does the rest.

1. Prompts: the script is planned as usual; every picture (every shot of every scene) gets a
   numbered, standalone prompt with the full character looks, the aspect ratio and the shot type.
   Character reference sheets come first (C1, C2, …), then the scene pictures (1, 2, 3, …).
2. Upload: drop your images (any order). They are matched by the number in the file name
   (1.png, scene_03.jpg, C1.png) or else by file order, cropped to fill the frame (no black bars).
   You can also put them in Google Drive: …/episodes/epNN/my_images/
3. Make video: your images are used and the image model (FLUX) is skipped completely.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .characters import SHOT_HINTS, frame_of
from .project import Episode, Series, dims, fingerprint, read_json, write_json

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".jfif", ".webp", ".heic", ".heif", ".avif"}
UPLOAD_TYPES = ["image", *sorted(IMAGE_EXT)]  # for Gradio: the extensions too (.jfif/.heic aren't always "image")
ENDING = "cinematic, highly detailed, no text, no letters, no watermark"


@dataclass
class Slot:
    number: int  # 1, 2, 3 … (what you type in the file name)
    sid: str  # scene id
    shot: int  # 0 = the scene's main picture, 1+ = extra shots
    scene_no: int  # scene number shown to you
    line: str  # what is said in that scene
    prompt: str


def aspect_words(length: str) -> str:
    return "horizontal 16:9" if length == "long" else "vertical 9:16"


def _people(series: Series, names: list[str]) -> list[dict]:
    out = []
    for n in names:
        c = series.character(n)
        if c and c not in out:
            out.append(c)
    return out


def scene_prompt(series: Series, scene: dict, shot_index: int, length: str, mood_lock: str = "") -> str:
    """A standalone Gemini prompt: scene, shot, mood lock, lighting, mood, FULL character looks + expression, aspect ratio."""
    from .planner import SHOTS  # noqa: PLC0415

    fr = frame_of(scene, shot_index)
    user = bool(scene.get("user_visual"))
    names = fr.get("characters", []) if (user or fr.get("show_character", True)) else []
    people = _people(series, names)
    parts = [scene.get("visual", "").strip().rstrip(".") + "."]
    shot = fr.get("shot")
    if shot in SHOTS:
        parts.append(f"Shot: {SHOT_HINTS[shot] if user else SHOTS[shot][0]}.")
    if mood_lock:
        parts.append(f"Setting and look (keep the same in every picture): {mood_lock.strip().rstrip('.')}.")
    if scene.get("location"):
        parts.append(f"Place: {scene['location']}.")
    for c in people:  # the full look EVERY time, so the face stays the same in every picture
        parts.append(f"{c['name']}: {c['description']}.")
    if people and fr.get("expression"):
        parts.append(f"Facial expression: {fr['expression']}.")
    if not people and not user and not fr.get("show_character", True):
        parts.append("No people in the picture.")
    if fr.get("composition"):
        parts.append(fr["composition"].capitalize() + ".")
    if fr.get("lighting"):
        parts.append(f"Lighting: {fr['lighting']}.")
    if scene.get("mood"):
        parts.append(f"Mood: {scene['mood']}.")
    style = series.data.get("style", "")
    if style:
        parts.append(f"Style: {style}.")
    parts.append(f"Aspect ratio: {aspect_words(length)}. {ENDING}.")
    return " ".join(p.strip() for p in parts if p.strip() and p.strip() != ".")


def character_prompt(series: Series, c: dict, length: str) -> str:
    return (f"Character reference sheet of {c['name']}: {c['description']}. Front view, face and full body, "
            f"standing straight, neutral expression, plain light grey background, soft even studio lighting. "
            f"Style: {series.data.get('style', '')}. Aspect ratio: {aspect_words(length)}. {ENDING}.")


def slots(series: Series, script: dict, length: str) -> list[Slot]:
    out, n = [], 0
    for i, sc in enumerate(script["scenes"], 1):
        line = " ".join(f"{ln['speaker']}: {ln['text']}" if ln.get("speaker") not in (None, "NARRATOR") else ln["text"]
                        for ln in sc.get("lines", [])) or sc.get("narration", "")
        for k in range(1 + len(sc.get("shots") or [])):
            n += 1
            out.append(Slot(n, sc["id"], k, i, line, scene_prompt(series, sc, k, length, script.get("mood_lock", ""))))
    return out


def characters_in(series: Series, script: dict) -> list[dict]:
    names = []
    for sc in script["scenes"]:
        for fr in [sc] + list(sc.get("shots") or []):
            names += fr.get("characters", [])
    names += [c["name"] for c in series.characters if c.get("look_from_script")]
    return _people(series, list(dict.fromkeys(names)))


def prompts_text(series: Series, script: dict, length: str) -> str:
    lines = [f"# {script.get('title', '')}: prompts for the Gemini app ({aspect_words(length)})",
             "# Make each picture in Gemini, download it, and name it with its number (1.png, 2.png …).", ""]
    for k, c in enumerate(characters_in(series, script), 1):
        lines += [f"C{k}. CHARACTER SHEET · {c['name']}", character_prompt(series, c, length), ""]
    for s in slots(series, script, length):
        shot = f", shot {s.shot + 1}" if s.shot else ""
        lines += [f"{s.number}. SCENE {s.scene_no}{shot}", s.prompt, ""]
    return "\n".join(lines).rstrip() + "\n"


def folder(ep: Episode) -> Path:
    """Google Drive folder for your own images (you can upload from your phone into it)."""
    d = ep.dir / "my_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_prompts(series: Series, ep: Episode, script: dict, length: str) -> Path:
    text = prompts_text(series, script, length)
    path = ep.dir / "prompts.txt"
    path.write_text(text, encoding="utf-8")
    (ep.export_dir / "prompts.txt").write_text(text, encoding="utf-8")
    folder(ep)
    write_json(ep.dir / "my_images.json", {**_mapping(ep), "script_fp": script_fp(script)})
    return path


def script_fp(script: dict) -> str:
    return fingerprint([(sc["id"], len(sc.get("shots") or [])) for sc in script["scenes"]])


# ---------------------------------------------------------------------------
# Your images: matching, cropping, missing
# ---------------------------------------------------------------------------


def _mapping(ep: Episode) -> dict:
    data = read_json(ep.dir / "my_images.json", {}) or {}
    data.setdefault("slots", {})  # "3" -> file name in my_images/
    data.setdefault("characters", {})  # "C1" -> file name
    return data


NUMBERED = re.compile(r"^(?:scene|shot|image|img|pic|picture|frame|s|p|no|nr)?[ _\-#.]*0*(\d{1,3})(?:[ _\-.].*)?$")


def _number(name: str) -> tuple[str, int] | None:
    """('C', 1) for C1.png / character_1.jpg, ('', 3) for 3.png / 03_taxi.jpg / scene_03.jpg, else None.

    Names you didn't choose (Gemini_Generated_Image_…, IMG_20261122…, "download (2)") have no number:
    those pictures are put in order by the time they were made.
    """
    stem = Path(name).stem.lower().strip()
    if re.search(r"gemini|generated|\(\d+\)$|^(img|dsc|pxl|screenshot|photo)[_\- ]?\d{4,}", stem):
        return None
    m = re.fullmatch(r"c(?:har(?:acter)?)?[ _\-#]*0*(\d{1,2})(?:[ _\-].*)?", stem)
    if m:
        return "C", int(m.group(1))
    m = NUMBERED.fullmatch(stem)
    if m:
        return "", int(m.group(1))
    return None


def order_keys(total: int, n_chars: int = 0) -> list[str]:
    """The order of all pictures: character sheets first (C1, C2…), then scenes 1, 2, 3…"""
    return [f"C{k}" for k in range(1, n_chars + 1)] + [str(n) for n in range(1, total + 1)]


def _get(data: dict, key: str) -> str | None:
    return (data["characters"] if key.startswith("C") else data["slots"]).get(key)


def _put(data: dict, key: str, value: str | None) -> None:
    box = data["characters"] if key.startswith("C") else data["slots"]
    if value:
        box[key] = value
    else:
        box.pop(key, None)


def _open_any(src: Path):
    """Open a picture of any common type (Gemini saves .jfif; phones save .heic)."""
    from PIL import Image  # noqa: PLC0415

    ext = src.suffix.lower()
    if ext in (".heic", ".heif"):
        try:
            import pillow_heif  # noqa: PLC0415

            pillow_heif.register_heif_opener()
        except ImportError:
            pass
    if ext == ".avif":
        try:
            import pillow_avif  # noqa: F401, PLC0415  (older Pillow without built-in AVIF)
        except ImportError:
            pass
    try:
        img = Image.open(src)
        img.load()
        return img
    except Exception:  # noqa: BLE001
        pass
    # last try: FFmpeg can read some files Pillow can't
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "x.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-frames:v", "1", str(out)],
                       capture_output=True, timeout=60, check=False)
        if out.exists():
            img = Image.open(out)
            img.load()
            return img
    raise ValueError(f"can't read {ext} pictures here")


def to_png(src: str | Path, dst: Path) -> Path:
    """Convert any picture to PNG (turned the right way up). Returns dst."""
    from PIL import ImageOps  # noqa: PLC0415

    img = ImageOps.exif_transpose(_open_any(Path(src)))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    img.save(tmp, format="PNG")
    tmp.replace(dst)
    return dst


def _store(src: Path, dst: Path) -> bool:
    """Save a picture as PNG in my_images/ (True if it was converted).

    A non-PNG original that was already in the Drive folder is moved to my_images/originals/."""
    d = dst.parent
    if src.suffix.lower() == ".png":
        if src.resolve() == dst.resolve():
            return False
        if _is_png(src):
            shutil.copyfile(src, dst)
            return False
        to_png(src, dst)  # a JPG that was renamed to .png
        return True
    to_png(src, dst)
    if src.parent.resolve() == d.resolve():  # it was in the folder: keep it, but out of the way
        (d / "originals").mkdir(exist_ok=True)
        shutil.move(str(src), str(d / "originals" / src.name))
    return True


def _is_png(p: Path) -> bool:
    with open(p, "rb") as fh:
        return fh.read(8) == b"\x89PNG\r\n\x1a\n"


def add_images(ep: Episode, files: list[str | Path], total: int, times: dict | None = None,
               n_chars: int = 0) -> list[str]:
    """Copy your files into my_images/ (as PNG) and match them to pictures. Returns messages.

    A number in the file name decides (1.png, C1.png). No number: oldest first by `times`
    (file name → when the file was made, from your browser or Google Drive), filling the
    character sheets C1, C2… first and then scenes 1, 2, 3… Without times: the order you picked them in.
    """
    d = folder(ep)
    data = _mapping(ep)
    used = set(data["slots"].values())
    msgs = []
    unnumbered = []  # (time or None, position, stored name)
    converted = []
    times = {str(k): v for k, v in (times or {}).items()}
    for pos, f in enumerate(files):
        f = Path(f)
        if f.suffix.lower() not in IMAGE_EXT:
            msgs.append(f"Skipped {f.name} (not a picture).")
            continue
        dst = d / (f.stem + ".png")
        try:
            if _store(f, dst):
                converted.append(f.name)
        except Exception as exc:  # noqa: BLE001
            msgs.append(f"⚠️ Couldn't open {f.name} ({exc}). Save it as PNG or JPG and upload it again.")
            continue
        num = _number(f.name)
        if num and num[0] == "C":
            data["characters"][f"C{num[1]}"] = dst.name
        elif num and 1 <= num[1] <= total:
            data["slots"][str(num[1])] = dst.name
        else:
            t = times.get(f.name, times.get(Path(f).name))
            unnumbered.append((float(t) if t is not None else None, pos, dst.name))
        used.add(dst.name)
    if unnumbered:
        timed = all(t is not None for t, _, _ in unnumbered)
        unnumbered.sort(key=lambda x: (x[0], x[1]) if timed else x[1])  # oldest first
        free = [k for k in order_keys(total, n_chars) if not _get(data, k)]
        for (_, _, name), key in zip(unnumbered, free):  # character sheets first, then scenes
            _put(data, key, name)
        if len(unnumbered) > len(free):
            msgs.append(f"{len(unnumbered) - len(free)} picture(s) had no free place left.")
        if len(unnumbered) > 1:
            msgs.append(f"🕒 {len(unnumbered)} pictures put in order by the time they were made (oldest first"
                        + (", character sheets first" if n_chars else "") + "). Check the order below."
                        if timed else
                        f"📋 {len(unnumbered)} pictures put in the order you selected them (your browser didn't "
                        "share the file times). Check the order below and fix it with ⬆️ ⬇️.")
    write_json(ep.dir / "my_images.json", data)
    if converted:
        names = ", ".join(converted[:3]) + (f" and {len(converted) - 3} more" if len(converted) > 3 else "")
        msgs.insert(0, f"🔄 Converted {len(converted)} picture(s) to PNG ({names}).")
    return msgs


def scan_folder(ep: Episode, total: int, n_chars: int = 0) -> list[str]:
    """Pictures you put into the Drive folder (e.g. from your phone) that aren't matched yet.

    Same rules as uploading; the order comes from the files' times in Google Drive (oldest first).
    """
    data = _mapping(ep)
    known = set(data["slots"].values()) | set(data["characters"].values())
    new = [p for p in folder(ep).iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT and p.name not in known]
    new.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
    times = {p.name: p.stat().st_mtime for p in new}
    return add_images(ep, new, total, times, n_chars) + ([f"Found {len(new)} new picture(s) in your Drive folder."]
                                                         if new else [])


def set_image(ep: Episode, number: int, file: str | Path) -> None:
    """Replace one picture."""
    f = Path(file)
    if f.suffix.lower() not in IMAGE_EXT:
        raise ValueError(f"{f.name} is not a picture (use PNG, JPG, JFIF, WEBP, HEIC or AVIF).")
    dst = folder(ep) / f"{number:03d}_{f.stem}.png"
    _store(f, dst)
    data = _mapping(ep)
    data["slots"][str(number)] = dst.name
    write_json(ep.dir / "my_images.json", data)


def move(ep: Episode, number: int | str, to: int | str, total: int, n_chars: int = 0) -> None:
    """Move a picture to another place (the two swap). Places: scene numbers 1, 2… or character sheets "C1"…"""
    keys = order_keys(total, n_chars)
    a_key, b_key = str(number), str(to)
    if a_key not in keys or b_key not in keys or a_key == b_key:
        return
    data = _mapping(ep)
    a, b = _get(data, a_key), _get(data, b_key)
    _put(data, b_key, a)
    _put(data, a_key, b)
    write_json(ep.dir / "my_images.json", data)


def step(ep: Episode, key: int | str, delta: int, total: int, n_chars: int = 0) -> None:
    """⬆️ / ⬇️: swap with the picture before / after (character sheets come before scene 1)."""
    keys = order_keys(total, n_chars)
    if str(key) in keys:
        i = keys.index(str(key)) + delta
        if 0 <= i < len(keys):
            move(ep, key, keys[i], total, n_chars)


def character_image(ep: Episode, k: int) -> Path | None:
    name = _mapping(ep)["characters"].get(f"C{k}")
    p = folder(ep) / name if name else None
    return p if p and p.exists() else None


def set_character_image(ep: Episode, k: int, file: str | Path) -> None:
    f = Path(file)
    if f.suffix.lower() not in IMAGE_EXT:
        raise ValueError(f"{f.name} is not a picture (use PNG, JPG, JFIF, WEBP, HEIC or AVIF).")
    dst = folder(ep) / f"C{k}_{f.stem}.png"
    _store(f, dst)
    data = _mapping(ep)
    data["characters"][f"C{k}"] = dst.name
    write_json(ep.dir / "my_images.json", data)


def image_for(ep: Episode, number: int) -> Path | None:
    name = _mapping(ep)["slots"].get(str(number))
    p = folder(ep) / name if name else None
    return p if p and p.exists() else None


def missing(ep: Episode, total: int) -> list[int]:
    return [n for n in range(1, total + 1) if image_for(ep, n) is None]


def fit(src: Path, dst: Path, size: tuple[int, int]) -> None:
    """Crop and resize to fill the frame exactly (no black bars)."""
    from PIL import Image, ImageOps  # noqa: PLC0415

    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.42)).save(dst)


def apply_images(series: Series, ep: Episode, script: dict, length: str, fmt: str, policy: str, rep=None) -> list[int]:
    """Put your pictures in place of the generated ones. Returns the numbers still missing (for FLUX).

    policy: "nearest" = reuse the nearest picture for missing ones, "flux" = leave them for the image model.
    """
    all_slots = slots(series, script, length)
    total = len(all_slots)
    size = dims(fmt, "1080p")
    have = {s.number: image_for(ep, s.number) for s in all_slots}
    still_missing = []
    for s in all_slots:
        src = have[s.number]
        how = "your image"
        if src is None and policy == "nearest":
            near = sorted((n for n, p in have.items() if p), key=lambda n: (abs(n - s.number), n > s.number))
            if near:
                src, how = have[near[0]], f"your image #{near[0]} (reused)"
        if src is None:
            still_missing.append(s.number)
            continue
        out = ep.image_path(s.sid, fmt, s.shot)
        key = f"image:{s.sid}:{fmt}" + (f":{s.shot}" if s.shot else "")
        st = src.stat()
        fp = fingerprint("mine", src.name, st.st_size, int(st.st_mtime), size)
        if not ep.state.fresh(key, fp, [out]):
            fit(src, out, size)
            ep.state.done(key, fp, provider=how)
            ep.state.forget(f"clip:{s.sid}")
            ep.state.forget(f"hero:{s.sid}")
    for cname, fname in _mapping(ep)["characters"].items():  # character sheets → reference pictures
        k = int(cname[1:])
        chars = characters_in(series, script)
        if 1 <= k <= len(chars) and (folder(ep) / fname).exists():
            from .characters import set_reference  # noqa: PLC0415

            set_reference(series, chars[k - 1]["name"], str(folder(ep) / fname))
    if rep is not None:
        rep.ok(f"🖼️ Your images: {total - len(still_missing)}/{total} pictures in place")
    return still_missing
