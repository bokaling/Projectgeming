"""Character bible: fixed look, fixed seed and a reference picture per character.

Consistency layers (research.md section 4): the same 40-60 word description is
copied into every prompt, each character has a fixed seed, and on the GPU the
reference picture is fed to FLUX.2 klein as a multi-reference input.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from .messages import FriendlyError, Timer
from .project import Series, fingerprint, read_json

MAX_REFS_PER_SCENE = 3


def stable_seed(text: str) -> int:
    return zlib.crc32(text.strip().lower().encode("utf-8")) % 2_000_000_000


def default_description(name: str, gender: str = "") -> str:
    who = {"female": "a woman", "male": "a man"}.get((gender or "").lower(), "a person")
    return (
        f"{who} in their late twenties, oval face, expressive dark brown eyes, shoulder-length dark hair, "
        "light olive skin, wearing a dark green field jacket over a gray t-shirt, black jeans and worn boots, "
        "calm but determined expression"
    )


def add_character(series: Series, name: str, description: str = "", gender: str = "") -> dict:
    existing = series.character(name)
    if existing:
        return existing
    c = {
        "name": name.strip(),
        "name_fa": "",
        "description": (description or "").strip() or default_description(name, gender),
        "gender": (gender or "").strip().lower(),
        "seed": stable_seed(series.slug + name),
        "ref": "",
    }
    series.characters.append(c)
    return c


def update_character(series: Series, name: str, *, description=None, name_fa=None, gender=None) -> dict:
    c = series.character(name)
    if c is None:
        raise FriendlyError(f"There is no character called {name}.", "Check the spelling on the Characters step.")
    if description is not None and description.strip() != c.get("description"):
        c["description"] = description.strip()
    if name_fa is not None:
        c["name_fa"] = name_fa.strip()
    if gender is not None:
        c["gender"] = gender.strip().lower()
    series.save()
    return c


def remove_character(series: Series, name: str) -> None:
    series.data["characters"] = [c for c in series.characters if c["name"].lower() != name.strip().lower()]
    series.save()


def ref_path(series: Series, c: dict) -> Path:
    return series.char_dir(c["name"]) / "ref.png"


def has_ref(series: Series, c: dict) -> bool:
    return ref_path(series, c).exists()


def ref_fingerprint(series: Series, c: dict) -> str:
    meta = read_json(series.char_dir(c["name"]) / "ref.json", {}) or {}
    return meta.get("fp", "")


def set_reference(series: Series, name: str, upload: str) -> Path:
    """Use your own picture as the character's reference."""
    c = series.character(name)
    if c is None:
        raise FriendlyError(f"There is no character called {name}.", "Add the character first.")
    from PIL import Image  # noqa: PLC0415

    dst = ref_path(series, c)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        Image.open(upload).convert("RGB").save(dst)
    except Exception:
        raise FriendlyError("That file is not a picture I can open.", "Upload a png or jpg.") from None
    from .project import write_json  # noqa: PLC0415

    write_json(dst.parent / "ref.json", {"fp": "uploaded", "source": "your upload"})
    c["ref"] = str(dst.relative_to(series.dir))
    series.save()
    return dst


def reference_prompt(series: Series, c: dict) -> str:
    return (
        f"Character reference portrait of {c['name']}: {c['description']}. "
        "Three-quarter view, head and upper body, looking slightly past the camera, neutral expression, "
        "plain soft gray studio background, soft even lighting, sharp focus, no text. "
        f"Style: {series.data.get('style', '')}"
    )


def ensure_references(series: Series, names: list[str] | None, rep, force: list[str] | None = None) -> None:
    """Make a reference picture for each character that has none (or was asked to redo)."""
    from . import images  # noqa: PLC0415

    force = [f.lower() for f in (force or [])]
    wanted = [c for c in series.characters if names is None or c["name"] in names]
    todo = [c for c in wanted if c["name"].lower() in force or not has_ref(series, c)
            or (ref_fingerprint(series, c) not in ("uploaded", fingerprint(reference_prompt(series, c), c["seed"])))]
    if not todo:
        return
    rep.step(f"🧑‍🎨 Character reference pictures ({len(todo)})")
    for i, c in enumerate(todo, 1):
        rep.check_stop()
        prompt = reference_prompt(series, c)
        with Timer() as t:
            provider = images.generate_to_file(prompt, ref_path(series, c), (768, 1024), seed=c["seed"], refs=[], rep=rep)
        from .project import write_json  # noqa: PLC0415

        write_json(series.char_dir(c["name"]) / "ref.json", {"fp": fingerprint(prompt, c["seed"]), "source": provider})
        c["ref"] = str(ref_path(series, c).relative_to(series.dir))
        rep.ok(f"{c['name']} {i}/{len(todo)} ({provider}, {t.label})")
    series.save()


def scene_prompt(series: Series, scene: dict, with_refs: bool) -> tuple[str, list[Path]]:
    """Build the image prompt for a scene and the list of reference pictures to send."""
    chars = [series.character(n) for n in scene.get("characters", [])]
    chars = [c for c in chars if c][:MAX_REFS_PER_SCENE]
    refs = [ref_path(series, c) for c in chars if with_refs and has_ref(series, c)]
    parts = []
    if refs:
        mapping = ", ".join(f"image {i + 1} shows {c['name']}" for i, c in enumerate(chars) if has_ref(series, c))
        parts.append(f"Keep the same people as in the reference images ({mapping}).")
    parts.append(scene.get("visual", ""))
    if scene.get("location"):
        parts.append(f"Location: {scene['location']}.")
    for c in chars:
        parts.append(f"{c['name']}: {c['description']}.")
    parts.append(f"Style: {series.data.get('style', '')}. Cinematic composition, no text, no watermark.")
    return " ".join(p.strip() for p in parts if p and p.strip()), refs

