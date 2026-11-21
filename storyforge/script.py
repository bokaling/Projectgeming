"""Story idea → episode script (hook first, cliffhanger last), editable text, Farsi translation."""

from __future__ import annotations

import random
import re

from . import config, llm, planner
from .messages import FriendlyError, Timer
from .paste import NARRATOR
from .project import Episode, EpisodeOptions, Series

CAMERAS = [
    "push_in", "pull_out", "pan_left", "pan_right", "tilt_up", "tilt_down",
    "orbit_left", "orbit_right", "dolly_zoom", "handheld", "static",
]
CAMERA_LABELS = {
    "push_in": "Push in", "pull_out": "Pull out", "pan_left": "Pan left", "pan_right": "Pan right",
    "tilt_up": "Tilt up", "tilt_down": "Tilt down", "orbit_left": "Orbit left", "orbit_right": "Orbit right",
    "dolly_zoom": "Dolly zoom", "handheld": "Handheld shake", "static": "Still (subtle drift)",
}
EFFECTS = ["dust", "snow", "rain", "embers", "fireflies", "fog", "light_leak", "god_rays", "flicker"]
SFX = ["whoosh", "impact", "riser", "heartbeat", "wind", "rain", "thunder", "sting"]
MOODS = ["tense", "mysterious", "sad", "hopeful", "epic", "calm", "dark", "action", "romantic", "playful"]
_CAMERA_ROTATION = ["push_in", "pan_right", "orbit_left", "pull_out", "tilt_up", "pan_left", "orbit_right", "dolly_zoom"]

SYSTEM_PROMPT = """You are the head writer of a serialized short-form story show for YouTube Shorts, TikTok and Reels.
You write gripping voiceover episodes with recurring characters. Every episode:
- Scene 1 is the HOOK: it must grab attention in the first 3 seconds. Start in the middle of the action or with a shocking line. Never start with "Once upon a time", "In this video" or a greeting.
- The last scene is the CLIFFHANGER: end on an unresolved question, a reveal or a threat, so viewers need the next episode.
- Narration is spoken voiceover: short, vivid, simple sentences that sound natural out loud.
- Each scene has one clear picture. Describe what the camera SEES (subject, action, setting, lighting, composition). Never ask for text, letters or logos in the picture.
- Recurring characters keep exactly the same look. Refer to them by name in "visual".
- Use a different camera move in each scene and never the same move twice in a row.
Reply with JSON only."""

SCHEMA_HINT = """Return this JSON:
{
  "title": "short episode title",
  "logline": "one sentence",
  "style": "one art style for the whole series (medium and rendering only, no color palette, no lighting)",
  "characters": [{"name": "Name", "description": "40-60 words: age, face, hair, eyes, body, clothing, colors. Fixed look.", "gender": "female|male|other"}],
  "scenes": [
    {
      "narration": "1-2 spoken sentences",
      "visual": "image prompt, what we see",
      "characters": ["Name"],
      "location": "short place name",
      "camera": "one of: %(cameras)s",
      "effects": ["zero to two of: %(effects)s"],
      "sfx": ["zero to two of: %(sfx)s"],
      "mood": "one of: %(moods)s",
      "hero": true
    }
  ],
  "cliffhanger": "the open question the episode ends on",
  "summary": "3 sentences that tell the next episode's writer what happened",
  "next_tease": "one teaser line for the next episode",
  "thumbnail_text": "2 to 4 punchy words",
  "music_mood": "one of: %(moods)s"
}
Set "hero": true only for the 2 or 3 most dramatic moving moments (big action, the hook, the reveal)."""


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def build_user_prompt(idea: str, series: Series, number: int, opts: EpisodeOptions) -> str:
    words = opts.scene_count * 17
    parts = [
        f"Series: {series.name}",
        f"Episode number: {number}",
        f"Story idea for this episode: {idea.strip() or 'continue the story'}",
        f"Write exactly {opts.scene_count} scenes. Total narration about {words} words "
        f"(about {round(words / 2.5)} seconds). Each scene 10 to 25 words.",
        "Write the narration in English.",
    ]
    custom_style = series.data.get("style_custom")
    if custom_style or number > 1:
        parts.append(f"Visual style (keep it): {series.data.get('style')}")
    if series.characters:
        parts.append("Recurring characters. Use these exact names. Copy their descriptions word for word:")
        for c in series.characters:
            parts.append(f"- {c['name']}: {c.get('description', '')}")
    prev = series.previous_summaries(number)
    if prev:
        parts.append("Story so far:")
        for p in prev:
            parts.append(f"- Episode {p['episode']} \"{p.get('title', '')}\": {p.get('summary', '')}")
        last = prev[-1]
        if last.get("cliffhanger"):
            parts.append(f"The last episode ended on this cliffhanger, pick it up in the hook: {last['cliffhanger']}")
    if opts.creator_note.strip():
        parts.append(f"Creator's note to include or respect: {opts.creator_note.strip()}")
    parts.append(
        SCHEMA_HINT
        % {"cameras": ", ".join(CAMERAS), "effects": ", ".join(EFFECTS), "sfx": ", ".join(SFX), "moods": ", ".join(MOODS)}
    )
    return "\n".join(parts)


def validate_raw(obj) -> None:
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    scenes = obj.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 2:
        raise ValueError("need a 'scenes' list with at least 2 scenes")
    for i, sc in enumerate(scenes, 1):
        if not isinstance(sc, dict) or not str(sc.get("narration", "")).strip():
            raise ValueError(f"scene {i} has no narration")


# ---------------------------------------------------------------------------
# Normalizing (make any AI output safe for the rest of the pipeline)
# ---------------------------------------------------------------------------


def _pick(value, allowed: list[str], default: str) -> str:
    v = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if v in allowed:
        return v
    for a in allowed:
        if v and (a in v or v in a):
            return a
    return default


def _pick_list(values, allowed: list[str], limit: int = 2) -> list[str]:
    if isinstance(values, str):
        values = re.split(r"[,;/]+", values)
    out = []
    for v in values or []:
        p = _pick(v, allowed, "")
        if p and p not in out:
            out.append(p)
    return out[:limit]


def _scene_ids(n: int, existing: list[str | None], reserved=()) -> list[str]:
    """Keep known ids; new scenes get ids never used before (so they never pick up old files)."""
    used = {e for e in existing if e} | set(reserved)
    ids, counter = [], 1
    for e in existing + [None] * (n - len(existing)):
        if e and e not in ids:
            ids.append(e)
            continue
        while f"s{counter:02d}" in used or f"s{counter:02d}" in ids:
            counter += 1
        ids.append(f"s{counter:02d}")
        counter += 1
    return ids[:n]


def _norm_lines(sc: dict, language: str) -> list[dict]:
    lines = []
    for ln in sc.get("lines") or []:
        if isinstance(ln, dict) and str(ln.get("text", "")).strip():
            lines.append({"speaker": str(ln.get("speaker") or NARRATOR).strip() or NARRATOR,
                          "text": re.sub(r"\s+", " ", str(ln["text"])).strip()})
    if not lines:
        text = sc.get("narration_fa") if language == "fa" else sc.get("narration")
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if text:
            lines = [{"speaker": NARRATOR, "text": text}]
    return lines


def _norm_shot(x: dict) -> dict:
    shot = str(x.get("shot") or "")
    return {"shot": shot if shot in planner.SHOTS else "medium", "show_character": bool(x.get("show_character")),
            "characters": [str(c) for c in (x.get("characters") or [])][:3],
            "composition": str(x.get("composition") or ""), "lighting": str(x.get("lighting") or ""),
            "camera": _pick(x.get("camera"), CAMERAS, "push_in"), "effects": _pick_list(x.get("effects"), EFFECTS)}


def normalize_scenes(scenes: list[dict], reserved=(), variety: bool = True, language: str = "en") -> list[dict]:
    ids = _scene_ids(
        len(scenes), [sc.get("id") if re.fullmatch(r"s\d+", str(sc.get("id", ""))) else None for sc in scenes], reserved
    )
    out = []
    prev_cam = None
    for i, sc in enumerate(scenes):
        lines = _norm_lines(sc, language)
        spoken = " ".join(ln["text"] for ln in lines)
        narration = spoken if language == "en" else re.sub(r"\s+", " ", str(sc.get("narration", ""))).strip()
        narration_fa = spoken if language == "fa" else str(sc.get("narration_fa") or "").strip()
        visual = str(sc.get("visual") or sc.get("image_prompt") or sc.get("picture") or "").strip()
        chars = sc.get("characters") or []
        if isinstance(chars, str):
            chars = re.split(r"[,;]+", chars)
        cam = _pick(sc.get("camera"), CAMERAS, _CAMERA_ROTATION[i % len(_CAMERA_ROTATION)])
        if variety and cam == prev_cam:  # never the same move twice in a row (AI scripts only)
            cam = next(c for c in _CAMERA_ROTATION[(i + 1) % len(_CAMERA_ROTATION):] + _CAMERA_ROTATION if c != prev_cam)
        prev_cam = cam
        shot = str(sc.get("shot") or "").strip().lower().replace(" ", "_").replace("-", "_")
        hero = sc.get("hero")
        out.append(
            {
                "id": ids[i],
                "kind": "hook" if i == 0 else ("cliffhanger" if i == len(scenes) - 1 else "scene"),
                "lines": lines,
                "narration": narration,
                "narration_fa": narration_fa,
                "narration_fa_src": str(sc.get("narration_fa_src") or "").strip(),
                "visual": visual or spoken[:200],
                "characters": [str(c).strip() for c in chars if str(c).strip()][:3],
                "location": str(sc.get("location") or "").strip(),
                "camera": cam,
                "effects": _pick_list(sc.get("effects"), EFFECTS),
                "sfx": _pick_list(sc.get("sfx"), SFX),
                "mood": _pick(sc.get("mood"), MOODS, "mysterious"),
                "hero": hero.strip().lower() in ("yes", "true", "1", "y") if isinstance(hero, str) else bool(hero),
                "shot": shot if shot in planner.SHOTS else "",
                "show_character": bool(sc.get("show_character", True)),
                "composition": str(sc.get("composition") or "").strip(),
                "lighting": str(sc.get("lighting") or "").strip(),
                "chapter": str(sc.get("chapter") or "").strip(),
                "regen": int(sc.get("regen") or 0),
                "user_visual": bool(sc.get("user_visual") or sc.get("from_tag")),
                "shots": [_norm_shot(x) for x in (sc.get("shots") or []) if isinstance(x, dict)][:8],
            }
        )
    return out


def hero_target(opts: EpisodeOptions) -> int:
    """How many hero scenes: your number, or 'auto' = what your GPU can do in reasonable time."""
    if opts.hero_count >= 0:
        return opts.hero_count
    prof = config.gpu_profile()
    return prof.heroes_long if opts.length == "long" else prof.heroes_short


def apply_hero_count(scenes: list[dict], n: int) -> None:
    """Mark exactly n scenes as hero (real image-to-video). Keeps your choices first."""
    n = max(0, min(12, int(n), len(scenes)))
    order = [s for s in scenes if s.get("hero")]
    people = [s for s in scenes if s.get("show_character") and s.get("shot") in ("medium", "low_angle", "over_shoulder")]
    priority = ([scenes[0], scenes[-1]] + [s for s in scenes if s.get("mood") in ("action", "epic")] + people
                + scenes[:: max(1, len(scenes) // max(1, n))] + scenes)
    for s in priority:
        if len(order) >= n:
            break
        if s not in order:
            order.append(s)
    keep = {s["id"] for s in order[:n]}
    for s in scenes:
        s["hero"] = s["id"] in keep


def normalize_script(raw: dict, opts: EpisodeOptions, user_edit: bool = False, reserved=()) -> dict:
    """Make any script safe for the pipeline. user_edit=True keeps the user's camera and hero choices."""
    language = raw.get("language") if raw.get("language") in ("en", "fa") else "en"
    scenes = normalize_scenes(list(raw.get("scenes") or [])[:200], reserved, variety=not user_edit, language=language)
    if not user_edit:
        apply_hero_count(scenes, hero_target(opts))
    return {
        "title": str(raw.get("title") or "Untitled episode").strip(),
        "title_fa": str(raw.get("title_fa") or "").strip(),
        "language": language,
        "length": opts.length,
        "source": raw.get("source") or ("ai" if opts.source == "ai" else "paste"),
        "logline": str(raw.get("logline") or "").strip(),
        "style": str(raw.get("style") or "").strip(),
        "characters": raw.get("characters") or [],
        "scenes": scenes,
        "cliffhanger": str(raw.get("cliffhanger") or "").strip(),
        "cliffhanger_fa": str(raw.get("cliffhanger_fa") or "").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "next_tease": str(raw.get("next_tease") or "").strip(),
        "thumbnail_text": str(raw.get("thumbnail_text") or raw.get("title") or "").strip(),
        "thumbnail_text_fa": str(raw.get("thumbnail_text_fa") or "").strip(),
        "music_mood": _pick(raw.get("music_mood"), MOODS, scenes[0]["mood"] if scenes else "mysterious"),
        "provider": raw.get("provider", ""),
        "retired_ids": list(raw.get("retired_ids") or []),
    }


# ---------------------------------------------------------------------------
# Template script (used when every AI service is unavailable)
# ---------------------------------------------------------------------------

_BEATS = [
    ("hook", "Nobody believed it could happen. Until tonight.", "a dramatic close-up moment of shock", "tense"),
    ("setup", "It started like any other day.", "an establishing wide shot of the setting", "calm"),
    ("inciting", "Then something small changed everything.", "a mysterious detail is discovered", "mysterious"),
    ("push", "There was no turning back now.", "the hero moves forward with determination", "tense"),
    ("obstacle", "But someone was watching.", "a shadowy figure watching from afar", "dark"),
    ("twist", "The truth was worse than anyone thought.", "a shocking reveal, dramatic lighting", "dark"),
    ("action", "Run. Now.", "a fast action moment, motion blur", "action"),
    ("calm", "For a moment, everything went quiet.", "a quiet emotional moment", "sad"),
    ("hope", "Maybe there was still a way out.", "a ray of light breaking through", "hopeful"),
    ("climax", "Everything led to this moment.", "an epic wide shot at the climax", "epic"),
]


def template_script(idea: str, opts: EpisodeOptions, series: Series) -> dict:
    rng = random.Random(idea)
    names = [c["name"] for c in series.characters][:2] or ["Alex"]
    hero = names[0]
    first = re.split(r"(?<=[.!?])\s+", idea.strip())[0] if idea.strip() else ""
    n = opts.scene_count
    beats = [_BEATS[0]] + [_BEATS[1 + (i % (len(_BEATS) - 1))] for i in range(n - 2)]
    scenes = []
    for i, (beat, line, picture, mood) in enumerate(beats):
        narration = (first or line) if i == 0 else line
        scenes.append(
            {
                "narration": narration.replace("the hero", hero),
                "visual": f"{hero}, {picture}. Story: {idea[:160]}",
                "characters": [hero],
                "camera": rng.choice(CAMERAS),
                "mood": mood,
                "effects": [rng.choice(EFFECTS)] if rng.random() < 0.6 else [],
                "sfx": ["whoosh"] if i else ["impact"],
            }
        )
    scenes.append(
        {
            "narration": f"And then {hero} heard a voice behind the door. A voice that should not exist.",
            "visual": f"{hero} turns toward a half-open door, light spilling out, suspense",
            "characters": [hero],
            "camera": "push_in",
            "mood": "tense",
            "effects": ["fog"],
            "sfx": ["sting"],
        }
    )
    raw = {
        "title": (idea.strip()[:40] or "A new story").rstrip(".") + "…",
        "logline": idea.strip()[:200],
        "characters": [] if series.characters else [
            {"name": hero, "description": "a young adult with short dark hair, brown eyes, a worn olive jacket, "
             "jeans and boots, determined expression", "gender": "other"}
        ],
        "scenes": scenes,
        "cliffhanger": "Whose voice was behind the door?",
        "summary": f"{hero} faced the first mystery. {idea[:200]}",
        "next_tease": "Next time: the voice has a name.",
        "thumbnail_text": "WHO WAS IT?",
        "music_mood": "tense",
    }
    return raw


# ---------------------------------------------------------------------------
# Write a script
# ---------------------------------------------------------------------------


def merge_characters(series: Series, script: dict) -> list[str]:
    """Add new characters from the script to the series bible. Returns new names."""
    from .characters import add_character  # noqa: PLC0415

    new = []
    for c in script.get("characters") or []:
        if not isinstance(c, dict) or not str(c.get("name", "")).strip():
            continue
        if series.character(c["name"]) is None:
            add_character(series, c["name"], c.get("description", ""), c.get("gender", ""))
            new.append(c["name"])
    # characters used in scenes but never described
    for sc in script["scenes"]:
        for name in sc["characters"]:
            if series.character(name) is None:
                add_character(series, name, "", "")
                new.append(name)
    return new


def write_script(series: Series, episode: Episode, opts: EpisodeOptions, rep) -> dict:
    """Ask the AI for a new episode script and save it (script.json + script.md)."""
    rep.step("✍️ Writing the script")
    rep.progress(0.1, "✍️ Writing the script")
    with Timer() as t:
        try:
            provider, raw = llm.generate_json(
                SYSTEM_PROMPT, build_user_prompt(opts.idea, series, episode.number, opts),
                validate=validate_raw, rep=rep, task="script",
            )
            rep.ok(f"Script written by {provider}")
        except Exception as exc:  # all AI services failed
            from .messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            rep.warn("All free AI writers are busy right now, so I made a simple starter script.")
            rep.info("👉 Please rewrite the lines in the Script step (or try again in a minute).")
            provider, raw = "Template (no AI)", template_script(opts.idea, opts, series)
    raw["provider"] = provider
    raw["source"] = "ai"
    rep.progress(0.7)
    scenes = [sc for sc in (raw.get("scenes") or []) if isinstance(sc, dict)]
    for sc in scenes:
        sc.setdefault("lines", [{"speaker": NARRATOR, "text": str(sc.get("narration", ""))}])
    names = [c.get("name", "") for c in raw.get("characters") or [] if isinstance(c, dict)]
    from .characters import add_character  # noqa: PLC0415

    for sc in scenes:  # characters the AI put in scenes join the series bible
        declared = sc.get("characters") or []
        for name in ([declared] if isinstance(declared, str) else declared):
            if str(name).strip() and str(name).strip() not in names:
                names.append(str(name).strip())
                if series.character(str(name).strip()) is None:
                    add_character(series, str(name).strip(), "", "")
    names += [c["name"] for c in series.characters if c["name"] not in names]
    from . import paste  # noqa: PLC0415

    planner.assign_variety(scenes, names, names[0] if names else "", planner.episode_seed(series.slug, episode.number),
                           paste.WORDS_PER_SHOT[opts.length])
    script = normalize_script(raw, opts)
    if script["style"] and not series.data.get("style_custom") and episode.number == 1:
        series.data["style"] = script["style"]
    merge_characters(series, script)
    series.save()
    episode.save_options(opts)
    save_script(episode, script)
    llm.unload_local()
    rep.ok(f"{len(script['scenes'])} scenes, “{script['title']}” ({t.label})")
    rep.record("ok" if provider != "Template (no AI)" else "warn", "Script", provider)
    if "fa" in opts.languages:
        translate_script(series, episode, script, rep, "fa")
    return script


def save_script(episode: Episode, script: dict) -> None:
    episode.save_script(script)
    episode.script_md_path.write_text(to_markdown(script), encoding="utf-8")


# ---------------------------------------------------------------------------
# Farsi translation
# ---------------------------------------------------------------------------


def translate_script(series: Series, episode: Episode, script: dict, rep, target: str = "fa") -> bool:
    """Translate the narration into the other language (only scenes whose text changed). True if all done."""
    import json  # noqa: PLC0415

    source = script.get("language", "en")
    if target == source:
        return True
    src_f, dst_f = ("narration", "narration_fa") if target == "fa" else ("narration_fa", "narration")
    mark = f"{dst_f}_src"
    todo = [s for s in script["scenes"] if s.get(src_f) and (not s.get(dst_f) or s.get(mark) != s[src_f])]
    title_key = "title_fa" if target == "fa" else "title_en"
    if not todo and script.get(title_key):
        return True
    lang_name = "Persian (Farsi)" if target == "fa" else "English"
    rep.step(f"🌍 Translating to {'Farsi' if target == 'fa' else 'English'}")
    names = {c["name"]: c.get("name_fa", "") for c in series.characters}
    system = (
        f"You translate story voiceovers into natural spoken {lang_name}. Keep each line about the same length so it "
        "fits the same timing. Keep the suspense. Write numbers as words. Use the given spellings for names. "
        "Reply with JSON only."
    )

    def validate(obj):
        if not isinstance(obj, dict) or not isinstance(obj.get("lines"), list):
            raise ValueError("expected 'lines' list")

    provider, ok = "", True
    batches = [todo[k:k + 25] for k in range(0, len(todo), 25)] or [script["scenes"][:1]]
    for n, batch in enumerate(batches):
        user = {"names": names, "lines": [{"id": s["id"], "text": s[src_f]} for s in batch],
                "reply_format": {"lines": [{"id": "same id", "text": f"{lang_name} line"}]}}
        if n == 0:
            user.update({"title": script["title"], "thumbnail_text": script.get("thumbnail_text", ""),
                         "cliffhanger": script.get("cliffhanger", "")})
            user["reply_format"].update({"title": lang_name, "thumbnail_text": f"2-4 {lang_name} words",
                                         "cliffhanger": lang_name, "names": {"EnglishName": "Persian spelling"}})
        try:
            provider, obj = llm.generate_json(system, json.dumps(user, ensure_ascii=False), validate=validate, rep=rep,
                                              task="translate", temperature=0.4)
        except Exception as exc:
            from .messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            ok = False
            break
        by_id = {str(item.get("id")): str(item.get("text", "")).strip() for item in obj["lines"] if isinstance(item, dict)}
        for sc in batch:
            if by_id.get(sc["id"]):
                sc[dst_f] = by_id[sc["id"]]
                sc[mark] = sc[src_f]
        if n == 0:
            if target == "fa":
                script["title_fa"] = str(obj.get("title") or script.get("title_fa") or "").strip()
                script["thumbnail_text_fa"] = str(obj.get("thumbnail_text") or script.get("thumbnail_text_fa") or "").strip()
                script["cliffhanger_fa"] = str(obj.get("cliffhanger") or script.get("cliffhanger_fa") or "").strip()
            else:
                script["title_en"] = str(obj.get("title") or "").strip()
            for en, fa in (obj.get("names") or {}).items():
                c = series.character(str(en))
                if c is not None and fa and not c.get("name_fa"):
                    c["name_fa"] = str(fa).strip()
    series.save()
    save_script(episode, script)
    label = "Farsi" if target == "fa" else "English"
    missing = [sc["id"] for sc in script["scenes"] if not sc.get(dst_f)]
    if not ok and missing:
        rep.warn(f"Couldn't translate right now. Type the {label} lines in the Script step (field '{label}:').")
        rep.record("warn", f"{label} translation", "type it yourself")
        return False
    if missing:
        rep.warn(f"{label} missing for {', '.join(missing)}. Add it in the Script step.")
    else:
        rep.ok(f"{label} ready ({provider})")
    rep.record("ok" if not missing else "warn", f"{label} translation", provider)
    return not missing


# ---------------------------------------------------------------------------
# Your pasted script (main mode)
# ---------------------------------------------------------------------------


def script_from_text(series: Series, episode: Episode, opts: EpisodeOptions, text: str, rep) -> dict:
    """Read a pasted script, plan the scenes (shots, prompts, characters) and save it."""
    from . import paste  # noqa: PLC0415
    from .characters import add_character  # noqa: PLC0415

    rep.step("📝 Reading your script")
    rep.progress(0.03, "📝 Reading your script")
    known = {c["name"].upper() for c in series.characters} | {c["name"] for c in series.characters}
    parsed = paste.parse_lines(text, known)
    if not parsed["blocks"]:
        raise FriendlyError("I couldn't find any story lines in your script.",
                            "Paste the text (NARRATOR: lines or plain sentences), then press Generate again.")
    lang = parsed["language"]
    warning = paste.length_warning(text, opts.length)
    if warning:
        rep.warn("📏 " + warning)
        rep.record("warn", "Script length", warning.split(".")[0])
    from .characters import set_description  # noqa: PLC0415

    for c in parsed.get("characters", []):  # [CHARACTER] NAME: look → used in every picture of that character
        name = c["name"].title() if paste.LATIN.search(c["name"]) else c["name"]
        set_description(series, name, c["description"])
        rep.info(f"🧑 {name}: {c['description']}")
    scenes = paste.to_scenes(parsed, opts.length)
    for i, sc in enumerate(scenes):
        sc["id"] = f"s{i + 1:02d}"
    for sp in parsed["speakers"]:  # characters who speak get a place in the series bible
        if series.character(sp) is None:
            add_character(series, sp.title() if paste.LATIN.search(sp) else sp, "", "")
    names = [c["name"] for c in series.characters]
    protagonist = series.data.get("protagonist", "") or (names[0] if names else "")
    seed = planner.episode_seed(series.slug, episode.number)
    planner.assign_variety(scenes, names, protagonist, seed, paste.WORDS_PER_SHOT[opts.length])
    n_pics = sum(1 + len(s["shots"]) for s in scenes)
    rep.info(f"{len(scenes)} scenes, {n_pics} pictures (a new picture every ~{paste.SECONDS_PER_IMAGE[opts.length]:g} s)")
    provider, new_chars, prot = planner.write_visuals(scenes, lang, series.characters, rep)
    for c in new_chars:
        existing = series.character(c["name"])
        if existing is None:
            add_character(series, c["name"], c.get("description", ""), c.get("gender", ""))
        elif not existing.get("look_from_script"):
            if c.get("description") and existing["description"].startswith(("a person in their", "a woman in their",
                                                                              "a man in their")):
                existing["description"] = c["description"]  # replace the default look with a real one
            if c.get("gender") and not existing.get("gender"):
                existing["gender"] = str(c["gender"]).strip().lower()  # so a woman gets a woman's voice
    protagonist = series.data.get("protagonist") or prot or protagonist
    if protagonist and series.character(protagonist):
        series.data["protagonist"] = series.character(protagonist)["name"]
    names = [c["name"] for c in series.characters]
    planner.fill_characters(scenes, names, series.data.get("protagonist", ""))
    words = " ".join(ln["text"] for sc in scenes for ln in sc["lines"]).split()
    title = parsed["title"] or " ".join(words[:6]).rstrip(".,!?؟") + "…"
    moods = [sc["mood"] for sc in scenes]
    raw = {
        "title": title, "language": lang, "scenes": scenes, "source": "paste", "provider": provider,
        "music_mood": max(set(moods), key=moods.count) if moods else "mysterious",
        "thumbnail_text": " ".join(title.split()[:4]),
        "summary": " ".join(words[:60]), "cliffhanger": scenes[-1]["lines"][-1]["text"] if scenes else "",
    }
    if lang not in opts.languages:
        opts.languages = [lang] + [x for x in opts.languages if x != lang]
    script = normalize_script(raw, opts)
    if lang == "fa":
        script["title_fa"] = title
        script["thumbnail_text_fa"] = raw["thumbnail_text"]
    series.save()
    episode.save_options(opts)
    save_script(episode, script)
    llm.unload_local()
    rep.ok(f"Script ready: “{title}”, {len(script['scenes'])} scenes, picture prompts by {provider}")
    rep.record("ok" if not provider.startswith("Built-in") else "warn", "Script", f"your script · prompts: {provider}")
    for target in opts.languages:
        if target != lang:
            translate_script(series, episode, script, rep, target)
    return script


# ---------------------------------------------------------------------------
# Editable text format (round trip)
# ---------------------------------------------------------------------------

_FIELD_ORDER = [
    ("Picture", "visual"), ("Shot", "shot"), ("Characters", "characters"), ("Place", "location"),
    ("Camera", "camera"), ("Effects", "effects"), ("Sound", "sfx"), ("Mood", "mood"), ("Hero", "hero"),
    ("Chapter", "chapter"),
]
_KEYS = {label.lower(): key for label, key in _FIELD_ORDER}
_KEYS.update({"visual": "visual", "location": "location", "sfx": "sfx", "farsi narration": "narration_fa",
              "persian": "narration_fa", "farsi": "narration_fa", "english": "narration", "image": "visual",
              "real video": "hero", "scene": "visual"})
_TOP = {"logline": "logline", "music": "music_mood", "thumbnail": "thumbnail_text", "farsi title": "title_fa",
        "farsi thumbnail": "thumbnail_text_fa", "style": "style", "language": "language"}


def to_markdown(script: dict) -> str:
    lang = script.get("language", "en")
    lines = [f"# {script.get('title', 'Untitled')}", "", f"Language: {lang}"]
    for label, key in (("Logline", "logline"), ("Farsi title", "title_fa"), ("Music", "music_mood"),
                       ("Thumbnail", "thumbnail_text"), ("Farsi thumbnail", "thumbnail_text_fa")):
        if script.get(key) or key in ("music_mood", "thumbnail_text"):
            lines.append(f"{label}: {script.get(key, '')}")
    for i, sc in enumerate(script["scenes"], 1):
        tag = " · HOOK" if sc["kind"] == "hook" else (" · CLIFFHANGER" if sc["kind"] == "cliffhanger" else "")
        lines += ["", f"## Scene {i} [{sc['id']}]{tag}"]
        for ln in sc.get("lines") or [{"speaker": NARRATOR, "text": sc.get("narration", "")}]:
            lines.append(f"{ln['speaker']}: {ln['text']}")
        if lang == "en" and sc.get("narration_fa"):
            lines.append(f"Farsi: {sc['narration_fa']}")
        if lang == "fa" and sc.get("narration"):
            lines.append(f"English: {sc['narration']}")
        for label, key in _FIELD_ORDER:
            val = sc.get(key)
            if key == "chapter" and not val:
                continue
            if isinstance(val, list):
                val = ", ".join(val)
            elif isinstance(val, bool):
                val = "yes" if val else "no"
            lines.append(f"{label}: {val or ''}")
    for label, key in (("Cliffhanger", "cliffhanger"), ("Summary", "summary"), ("Next time", "next_tease")):
        lines += ["", f"## {label}", script.get(key, "")]
    return "\n".join(lines).strip() + "\n"


def from_markdown(text: str, old: dict | None, opts: EpisodeOptions) -> dict:
    """Parse the edited text back into a script. Unknown lines are kept with the field above them."""
    from . import paste  # noqa: PLC0415

    old = old or {}
    title, top, sections = "", {}, []
    current: dict | None = None
    last_key = None
    known = {ln["speaker"] for sc in old.get("scenes", []) for ln in sc.get("lines", [])} | {NARRATOR}
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            continue
        if line.startswith("##"):
            head = line.lstrip("#").strip()
            if re.match(r"(?i)scene\b", head):
                m = re.search(r"\[(s\d+)\]", head)
                current = {"_type": "scene", "id": m.group(1) if m else None, "lines": []}
            else:
                current = {"_type": head.lower(), "_text": []}
            sections.append(current)
            last_key = None
            continue
        m = re.match(r"^\s*([^:：]{1,32}?)\s*[:：]\s*(.*)$", line)
        label = m.group(1).strip().lower() if m else ""
        if current is None:
            if m and label in _TOP:
                top[_TOP[label]] = m.group(2).strip()
            continue
        if current["_type"] != "scene":
            current["_text"].append(line)
            continue
        if m and label == "narration":
            current["lines"].append({"speaker": NARRATOR, "text": m.group(2).strip()})
            last_key = "_line"
        elif m and label in _KEYS:
            last_key = _KEYS[label]
            current[last_key] = m.group(2).strip()
        elif m and paste._speaker(m.group(1), known):
            who = paste._speaker(m.group(1), known)
            known.add(who)
            current["lines"].append({"speaker": who, "text": m.group(2).strip()})
            last_key = "_line"
        elif line.strip() and last_key == "_line" and current["lines"]:
            current["lines"][-1]["text"] = (current["lines"][-1]["text"] + " " + line.strip()).strip()
        elif line.strip() and last_key:
            current[last_key] = (str(current.get(last_key, "")) + " " + line.strip()).strip()
    old_scenes = {s["id"]: s for s in old.get("scenes", [])}
    language = top.get("language") or old.get("language", "en")
    scenes = []
    for sec in sections:
        if sec["_type"] != "scene":
            continue
        base = dict(old_scenes.get(sec.get("id") or "", {}))
        base.update({k: v for k, v in sec.items() if not k.startswith("_")})
        for key in ("characters", "effects", "sfx"):
            if isinstance(base.get(key), str):
                base[key] = [x.strip() for x in re.split(r"[,;]+", base[key]) if x.strip()]
        if base.get("lines"):
            scenes.append(base)
    if len(scenes) < 1:
        raise FriendlyError("I couldn't find any scenes in your text.",
                            "Each scene needs a '## Scene' line and at least one 'NARRATOR:' line.")
    extra = {sec["_type"]: "\n".join(sec["_text"]).strip() for sec in sections if sec["_type"] != "scene"}
    raw = {**old, **top, "scenes": scenes, "title": title or old.get("title", ""), "language": language}
    raw["cliffhanger"] = extra.get("cliffhanger", old.get("cliffhanger", ""))
    raw["summary"] = extra.get("summary", old.get("summary", ""))
    raw["next_tease"] = extra.get("next time", old.get("next_tease", ""))
    reserved = [sc["id"] for sc in old.get("scenes", [])] + list(old.get("retired_ids", []))
    result = normalize_script(raw, opts, user_edit=True, reserved=reserved)
    result["retired_ids"] = sorted(set(reserved) - {sc["id"] for sc in result["scenes"]})
    return result
