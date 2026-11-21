"""Scene planning: shot variety, composition, lighting and automatic image prompts.

Rules (from your feedback "all scenes looked the same"):
* Every scene gets a different shot type, rotating through 8 kinds.
* The main character appears in about half the scenes (4 of the 8 shot types).
* Composition, lighting and color change from scene to scene (never all sepia).
* Scenes where a character speaks always show a character.
"""

from __future__ import annotations

import json
import re
import zlib

from . import llm
from .paste import NARRATOR, PERSIAN

# (prompt text, shows the character?)
SHOTS = {
    "wide": ("wide establishing shot showing the whole location, people tiny or absent", False),
    "medium": ("medium shot, waist up", True),
    "detail": ("extreme close-up insert of an important object or detail, no people", False),
    "close_up": ("close-up on the face, emotional expression, shallow depth of field", True),
    "environment": ("empty environment shot, atmospheric, no people", False),
    "over_shoulder": ("over-the-shoulder shot from behind one person", True),
    "top_down": ("top-down overhead shot looking straight down", False),
    "low_angle": ("low angle shot looking up at the subject, dramatic", True),
}
SHOT_LABELS = {
    "wide": "Wide establishing", "medium": "Medium shot", "detail": "Detail / object insert",
    "close_up": "Close-up", "environment": "Environment (no people)", "over_shoulder": "Over the shoulder",
    "top_down": "Top-down", "low_angle": "Low angle",
}
ROTATION = ["wide", "medium", "detail", "close_up", "environment", "over_shoulder", "top_down", "low_angle"]
CHARACTER_SHOTS = [s for s in ROTATION if SHOTS[s][1]]

COMPOSITIONS = [
    "subject placed on the left third of the frame",
    "centered symmetrical composition",
    "subject placed on the right third of the frame",
    "strong foreground element framing the subject",
    "subject small in the frame with lots of negative space",
    "diagonal composition with leading lines",
]
LIGHTING = {
    "dark": ["cold blue moonlight with deep shadows", "deep red emergency light with teal shadows",
             "single flickering bulb, high contrast", "stormy green-gray light"],
    "tense": ["harsh white flashlight beam in darkness", "cold blue moonlight with silver highlights",
              "red and blue city lights through rain", "sickly yellow street lamp light"],
    "mysterious": ["foggy pale dawn light", "violet twilight glow", "cool cyan moonlight through mist",
                   "soft green bioluminescent glow"],
    "hopeful": ["warm golden hour sunlight", "crisp morning light with clear blue sky", "soft pastel sunrise",
                "bright clean daylight with vivid colors"],
    "sad": ["soft overcast gray-blue light", "rainy window light, muted cool colors", "dim evening light, lonely",
            "pale winter daylight"],
    "epic": ["dramatic sunset with orange and purple sky", "god rays breaking through clouds",
             "fiery orange backlight", "vast bright daylight, saturated colors"],
    "calm": ["soft natural daylight", "warm lamp light, cozy", "gentle morning haze", "clear blue afternoon light"],
    "action": ["high contrast neon magenta and cyan", "sparks and orange firelight", "strobing white light",
               "bright noon sun with hard shadows"],
    "romantic": ["warm candlelight", "pink and gold sunset", "soft fairy lights bokeh", "moonlight on water"],
    "playful": ["bright colorful daylight", "candy colored neon", "sunny summer light", "vivid saturated colors"],
}
CAMERA_FOR_SHOT = {
    "wide": ["pan_right", "pull_out", "pan_left"], "medium": ["orbit_left", "push_in", "orbit_right"],
    "detail": ["push_in", "dolly_zoom"], "close_up": ["push_in", "static", "handheld"],
    "environment": ["pan_left", "tilt_up", "pan_right"], "over_shoulder": ["handheld", "push_in"],
    "top_down": ["static", "pull_out"], "low_angle": ["tilt_up", "push_in"],
}
EFFECTS_FOR_MOOD = {
    "dark": [["fog"], ["dust"], []], "tense": [["dust"], ["fog"], []], "mysterious": [["fog"], ["fireflies"], ["dust"]],
    "hopeful": [["light_leak"], ["god_rays"], []], "sad": [["rain"], ["dust"], []], "epic": [["embers"], ["god_rays"], []],
    "calm": [["dust"], [], ["fireflies"]], "action": [["dust"], ["embers"], []],
    "romantic": [["light_leak"], ["fireflies"], []], "playful": [["light_leak"], [], ["dust"]],
}
MOOD_WORDS = {
    "dark": ["blood", "dead", "death", "kill", "grave", "corpse", "shadow", "demon", "مرگ", "خون", "مرده", "سایه"],
    "tense": ["run", "scream", "afraid", "fear", "danger", "knock", "heart", "suddenly", "ترس", "فریاد", "ناگهان", "خطر"],
    "mysterious": ["secret", "strange", "mystery", "whisper", "unknown", "fog", "راز", "عجیب", "زمزمه", "مه"],
    "sad": ["cry", "tears", "lost", "alone", "goodbye", "sorry", "گریه", "اشک", "تنها", "خداحافظ"],
    "hopeful": ["hope", "smile", "light", "sun", "home", "found", "امید", "لبخند", "خورشید", "نور"],
    "action": ["fight", "explosion", "chase", "fire", "attack", "crash", "جنگ", "انفجار", "تعقیب", "آتش"],
    "romantic": ["love", "kiss", "heart beat", "together", "عشق", "بوسه"],
    "epic": ["army", "kingdom", "battle", "legend", "mountain", "ارتش", "پادشاه", "نبرد", "افسانه"],
}


def guess_mood(text: str, default: str = "mysterious") -> str:
    low = (text or "").lower()
    best, score = default, 0
    for mood, words in MOOD_WORDS.items():
        s = sum(low.count(w) for w in words)
        if s > score:
            best, score = mood, s
    return best


def mentioned(text: str, names: list[str]) -> list[str]:
    low = (text or "").lower()
    return [n for n in names if n and re.search(r"(?<!\w)" + re.escape(n.lower()) + r"(?!\w)", low)]


def assign_variety(scenes: list[dict], character_names: list[str], protagonist: str, seed: int) -> None:
    """Shot type, composition, lighting, camera move and effects for every scene (in place)."""
    idx = seed % len(ROTATION)
    prev_shot = prev_cam = prev_light = prev_comp = None
    canon = {n.lower(): n for n in character_names}
    for i, sc in enumerate(scenes):
        speakers = [canon.get(ln["speaker"].lower(), ln["speaker"]) for ln in sc.get("lines", [])
                    if ln.get("speaker") not in (None, NARRATOR)]
        text = " ".join(ln.get("text", "") for ln in sc.get("lines", []))
        named = mentioned(sc.get("visual", "") if sc.get("from_tag") else "", character_names)
        must_show = bool(speakers or named)
        if sc.get("shot") in SHOTS:  # user's choice
            shot = sc["shot"]
        else:
            shot = ROTATION[idx % len(ROTATION)]
            if must_show and not SHOTS[shot][1]:
                shot = next(s for s in ROTATION[idx % 8:] + ROTATION if SHOTS[s][1] and s != prev_shot)
            elif shot == prev_shot:
                idx += 1
                shot = ROTATION[idx % len(ROTATION)]
            idx += 1
        sc["shot"] = shot
        sc["show_character"] = SHOTS[shot][1]
        chars = list(dict.fromkeys(speakers + named + mentioned(text, character_names)))
        if sc["show_character"] and not chars and protagonist:
            chars = [protagonist]
        sc["characters"] = chars[:3] if sc["show_character"] else []
        mood = sc.get("mood") or guess_mood(text + " " + sc.get("visual", ""))
        sc["mood"] = mood
        comps = [c for c in COMPOSITIONS if c != prev_comp]
        sc["composition"] = sc.get("composition") or comps[(i * 2 + seed) % len(comps)]
        lights = [x for x in LIGHTING.get(mood, LIGHTING["mysterious"]) if x != prev_light]
        sc["lighting"] = sc.get("lighting") or lights[(i + seed) % len(lights)]
        cams = [c for c in CAMERA_FOR_SHOT[shot] if c != prev_cam] or CAMERA_FOR_SHOT[shot]
        sc["camera"] = sc.get("camera") or cams[(i + seed) % len(cams)]
        if "effects" not in sc:
            options = EFFECTS_FOR_MOOD.get(mood, [[]])
            sc["effects"] = list(options[(i + seed) % len(options)])
        prev_shot, prev_cam, prev_light, prev_comp = shot, sc["camera"], sc["lighting"], sc["composition"]


def fill_characters(scenes: list[dict], names: list[str], protagonist: str) -> None:
    """After new characters are known: who is in each character shot."""
    for sc in scenes:
        if not sc.get("show_character"):
            sc["characters"] = []
            continue
        text = " ".join(ln.get("text", "") for ln in sc.get("lines", [])) + " " + sc.get("visual", "")
        speakers = [ln["speaker"] for ln in sc.get("lines", []) if ln.get("speaker") not in (None, NARRATOR)]
        found = [n for n in names if n.lower() in [s.lower() for s in speakers]] + mentioned(text, names)
        found = list(dict.fromkeys(found))
        if not found and protagonist:
            found = [protagonist]
        sc["characters"] = found[:3]


def fallback_visual(text: str, shot: str) -> str:
    """No AI available: describe the scene from its own words."""
    clean = re.sub(r"[\"“”«»]", "", text or "").strip()
    first = " ".join(re.split(r"(?<=[.!?؟])\s+", clean)[:2])
    words = first.split()
    return " ".join(words[:35]) if words else "an atmospheric cinematic scene"


PROMPT_SYSTEM = """You are a film director and storyboard artist for short story videos.
For each scene write ONE English image prompt (25-45 words) describing what the camera sees: subject, action, setting, props, weather, time of day.
Follow the given shot type and the 'show_character' flag exactly: if it is false, show NO people (an object, a place or a detail).
Never describe the same composition twice. Do not mention text, captions or logos. Reply with JSON only."""


def write_visuals(scenes: list[dict], language: str, known: list[dict], rep=None) -> tuple[str, list[dict], str]:
    """Fill scene['visual'] where missing (or translate Farsi visuals to English).

    Returns (provider, new_characters, protagonist).
    """
    todo = [s for s in scenes if not s.get("visual", "").strip() or PERSIAN.search(s.get("visual", ""))]
    provider, new_chars, protagonist = "Built-in (no AI)", [], ""
    if todo:
        try:
            for k in range(0, len(todo), 20):
                batch = todo[k:k + 20]
                payload = {
                    "language_of_text": "Persian" if language == "fa" else "English",
                    "known_characters": [{"name": c["name"], "look": c.get("description", "")} for c in known],
                    "scenes": [{"id": s["id"], "text": " ".join(f"{ln['speaker']}: {ln['text']}" for ln in s["lines"])[:700],
                                "shot": SHOTS[s["shot"]][0], "show_character": s["show_character"],
                                "given_description": s.get("visual", "")} for s in batch],
                    "reply_format": {
                        "protagonist": "name of the main character (or empty)",
                        "new_characters": [{"name": "Name", "gender": "female|male",
                                            "description": "40-60 words fixed look: age, face, hair, clothes, colors"}],
                        "scenes": [{"id": "same id", "visual": "English image prompt", "mood": "one word",
                                    "location": "short place name"}],
                    },
                }

                def validate(obj):
                    if not isinstance(obj, dict) or not isinstance(obj.get("scenes"), list):
                        raise ValueError("need a 'scenes' list")

                provider, obj = llm.generate_json(PROMPT_SYSTEM, json.dumps(payload, ensure_ascii=False),
                                                  validate=validate, rep=rep, task="image prompts", temperature=0.8)
                by_id = {str(x.get("id")): x for x in obj["scenes"] if isinstance(x, dict)}
                for s in batch:
                    got = by_id.get(s["id"]) or {}
                    if str(got.get("visual", "")).strip():
                        s["visual"] = str(got["visual"]).strip()
                    if got.get("location"):
                        s["location"] = str(got["location"]).strip()
                for c in obj.get("new_characters") or []:
                    if isinstance(c, dict) and c.get("name") and c["name"] not in [x.get("name") for x in new_chars]:
                        new_chars.append(c)
                protagonist = protagonist or str(obj.get("protagonist") or "").strip()
        except Exception as exc:  # noqa: BLE001
            from .messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            if rep is not None:
                rep.warn("The AI prompt writer is busy, so I wrote simple picture prompts from your text.")
    for s in scenes:
        if not s.get("visual", "").strip() or (PERSIAN.search(s["visual"]) and provider.startswith("Built-in")):
            s["visual"] = s.get("visual", "").strip() or fallback_visual(" ".join(ln["text"] for ln in s["lines"]), s["shot"])
    return provider, new_chars, protagonist


def episode_seed(series_slug: str, number: int) -> int:
    return zlib.crc32(f"{series_slug}/{number}".encode()) % 997
