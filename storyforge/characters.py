"""Characters who speak in a script: their name, gender (for the voice) and a voice that stays the same
in every episode of the series. (In the 3D explainers most lines are the narrator's.)"""

from __future__ import annotations

import re
import zlib

from .messages import FriendlyError
from .project import Series


def stable_seed(text: str) -> int:
    return zlib.crc32(text.strip().lower().encode("utf-8")) % 2_000_000_000


MALE = re.compile(r"\b(man|male|boy|guy|he|his|him|father|dad|husband|gentleman|mr|king|son|uncle|"
                  r"brother)\b|مرد|پسر|آقا", re.I)
FEMALE = re.compile(r"\b(woman|female|girl|lady|she|her|mother|mom|wife|mrs|ms|miss|queen|daughter|aunt|"
                    r"sister)\b|زن|دختر|خانم", re.I)


def guess_gender(text: str) -> str:
    f, m = len(FEMALE.findall(text or "")), len(MALE.findall(text or ""))
    return "female" if f > m else ("male" if m > f else "")


def add_character(series: Series, name: str, description: str = "", gender: str = "") -> dict:
    existing = series.character(name)
    if existing:
        return existing
    c = {"name": name.strip(), "name_fa": "", "description": (description or "").strip(),
         "gender": (gender or guess_gender(description)).strip().lower(), "seed": stable_seed(series.slug + name)}
    series.characters.append(c)
    return c


def set_description(series: Series, name: str, description: str) -> dict:
    """[CHARACTER] NAME: description → saved for the series (the description decides the voice: man or woman)."""
    c = add_character(series, name, description, guess_gender(description))
    if description.strip():
        c["description"] = description.strip()
        g = guess_gender(description)
        if g:
            c["gender"] = g
    series.save()
    return c


def update_character(series: Series, name: str, *, description=None, name_fa=None, gender=None) -> dict:
    c = series.character(name)
    if c is None:
        raise FriendlyError(f"There is no character called {name}.", "Check the spelling.")
    if description is not None:
        c["description"] = description.strip()
    if name_fa is not None:
        c["name_fa"] = name_fa.strip()
    if gender is not None:
        c["gender"] = gender.strip().lower()
    series.save()
    return c


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
