"""Character bible: fixed look, fixed seed and a reference picture per character.

Consistency layers (research.md section 4): the same 40-60 word description is
copied into every prompt, each character has a fixed seed, and on the GPU the
reference picture is fed to FLUX.2 klein as a multi-reference input.
"""

from __future__ import annotations

import re
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


MALE = re.compile(r"\b(man|male|boy|guy|he|his|him|father|dad|husband|gentleman|mr|king|son|uncle|"
                  r"brother)\b|مرد|پسر|آقا", re.I)
FEMALE = re.compile(r"\b(woman|female|girl|lady|she|her|mother|mom|wife|mrs|ms|miss|queen|daughter|aunt|"
                    r"sister)\b|زن|دختر|خانم", re.I)


def guess_gender(text: str) -> str:
    f, m = len(FEMALE.findall(text or "")), len(MALE.findall(text or ""))
    return "female" if f > m else ("male" if m > f else "")


def set_description(series: Series, name: str, description: str) -> dict:
    """Your [CHARACTER] look: saved for the series, used in every picture where this character appears."""
    c = add_character(series, name, description, guess_gender(description))
    if description.strip():
        c["description"] = description.strip()
        c["look_from_script"] = True
        g = guess_gender(description)
        if g:
            c["gender"] = g
    series.save()
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
        "plain soft gray studio background, soft even lighting, sharp focus. "
        f"Style: {series.data.get('style', '')}. No text, no letters, no watermark."
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
        try:
            with Timer() as t:
                provider = images.generate_to_file(prompt, ref_path(series, c), (768, 1024), seed=c["seed"], refs=[],
                                                   rep=rep, allow_placeholder=False, label=f"ref:{c['name']}")
        except FriendlyError:
            rep.warn(f"No reference picture for {c['name']} yet (no picture service worked). "
                     "I'll try again next time, or upload one on the Characters step.")
            continue
        from .project import write_json  # noqa: PLC0415

        write_json(series.char_dir(c["name"]) / "ref.json", {"fp": fingerprint(prompt, c["seed"]), "source": provider})
        c["ref"] = str(ref_path(series, c).relative_to(series.dir))
        rep.ok(f"{c['name']} {i}/{len(todo)} ({provider}, {t.label})")
    series.save()


POSES = ["mid-movement, natural body language", "turning to look over the shoulder", "leaning forward, focused",
         "standing still, tense posture", "walking toward the camera", "hands busy with an object",
         "seen in profile", "sitting, lost in thought"]


NO_TEXT = "No text, no letters, no watermark."
# Short framing words used AFTER your own [SCENE] text (they never replace it)
SHOT_HINTS = {
    "wide": "wide shot", "medium": "medium shot", "detail": "extreme close-up detail shot", "close_up": "close-up shot",
    "environment": "atmospheric shot of the place", "over_shoulder": "over-the-shoulder shot",
    "top_down": "top-down overhead shot", "low_angle": "low angle shot looking up",
}


def frame_of(scene: dict, shot_index: int = 0) -> dict:
    """The framing of shot k of a scene (shot 0 = the scene itself)."""
    if shot_index == 0:
        return scene
    extra = scene.get("shots") or []
    return {**scene, **extra[shot_index - 1]} if shot_index - 1 < len(extra) else scene


def scene_prompt(series: Series, scene: dict, with_refs: bool, shot_index: int = 0) -> tuple[str, list[Path]]:
    """Build the image prompt for one shot of a scene and the reference pictures to send.

    Your [SCENE] text is the main prompt and comes first; the shot type is added after it.
    Characters in the shot get their fixed look (and reference picture on the GPU).
    """
    from .planner import SHOTS  # noqa: PLC0415

    fr = frame_of(scene, shot_index)
    shot = fr.get("shot") or ""
    user = bool(scene.get("user_visual"))
    names = fr.get("characters", []) if (user or fr.get("show_character", True)) else []  # no-people shots: nobody
    chars = [c for c in (series.character(n) for n in names) if c][:MAX_REFS_PER_SCENE]
    refs = [ref_path(series, c) for c in chars if with_refs and has_ref(series, c)]
    parts = [scene.get("visual", "").strip().rstrip(".") + "."]
    if shot in SHOTS:
        parts.append(f"Shot: {SHOT_HINTS[shot] if user else SHOTS[shot][0]}.")
    if scene.get("location"):
        parts.append(f"Location: {scene['location']}.")
    for k, c in enumerate(chars):
        pose = POSES[(int(scene.get("id", "s0")[1:] or 0) + k + shot_index) % len(POSES)]
        parts.append(f"{c['name']} is {c['description']}, {pose}.")
    if refs:
        mapping = ", ".join(f"image {i + 1} shows {c['name']}" for i, c in enumerate(chars) if has_ref(series, c))
        parts.append(f"Same face and hair as the reference images ({mapping}), new pose and camera angle.")
    if not chars and not user and not fr.get("show_character", True):
        parts.append("No people in the frame.")
    if fr.get("composition"):
        parts.append(fr["composition"].capitalize() + ".")
    if fr.get("lighting"):
        parts.append(f"Lighting and color: {fr['lighting']}.")
    parts.append(f"Style: {series.data.get('style', '')}. Full natural color (not sepia, not monochrome), "
                 f"cinematic, highly detailed, sharp focus. {NO_TEXT}")
    return " ".join(p.strip() for p in parts if p and p.strip() and p.strip() != "."), refs


def voice_for(series: Series, speaker: str, lang: str, narrator_value: str) -> dict:
    """The voice of a speaking character (picked once, saved in the series, different from the narrator)."""
    from .audio import tts  # noqa: PLC0415

    c = series.character(speaker)
    if c is None:
        return tts.parse_voice(narrator_value, lang)
    key = f"voice_{lang}"
    if not c.get(key):
        gender = "female" if str(c.get("gender", "")).lower().startswith(("f", "w")) else "male"
        used = {narrator_value} | {x.get(key) for x in series.characters if x.get(key)}
        pool = tts.CHARACTER_POOL[(lang, gender)]
        c[key] = next((v for v in pool if v not in used), pool[0])
        series.save()
    return tts.parse_voice(c[key], lang)
