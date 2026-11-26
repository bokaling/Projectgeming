"""Topic → script (the free AI with retention rules), and your script → scenes.

Script format (you can paste your own):
    [TITLE] How cow poop becomes electricity
    [STYLE] clean low poly farm (optional)
    [SCENE] what we see in this shot
    NARRATOR: what is said in this shot
Several scripts separated by a line of ===== = batch mode.
"""

from __future__ import annotations

import json
import re

from . import beats, llm, paste
from .messages import FriendlyError, Timer
from .paste import NARRATOR
from .project import Episode, EpisodeOptions, Series

SCRIPT_SYSTEM = """You write scripts for a viral low poly 3D "how it works" explainer channel (YouTube Shorts, TikTok, long YouTube videos).
Topics: how things work, what happens if, how things are made, inside machines, science, engineering, history, true stories.
Hook (the first 10 seconds):
- Line 1 is a short question (max 10 words) that the first shot SHOWS ("What happens when you press the gas pedal?").
- Then, within the first 10 seconds, a surprising myth buster: what most people believe, and what really happens
  ("The gas pedal doesn't give the engine more gas. It lets in more air."). No slow intros ("Have you ever wondered",
  "In this video", "Once upon a time").
Explain step by step:
- Follow the REAL order the thing works, from start to finish. One clear idea per step, with a simple "why".
- Each step is one [SCENE] with 1-3 sentences (about 10-20 words, 4-8 seconds) that match ONE shot. Several sentences
  about the same thing stay in the same [SCENE].
- Every NARRATOR line describes something the viewer can SEE at that moment (a part moving, a liquid flowing, a light
  turning on, a number appearing). [SCENE] says literally what we see.
- Name the REAL parts (piston, valve, compressor, float, sheave...) and show each one working, in order.
Tone:
- A strong hook, then a calm, curious tone. Punchy short sentences only for the hook, the reveals and the ending.
- No jargon or unit soup (kN, MPa, degrees, microseconds) unless you explain it simply. Turn big or tiny numbers into
  everyday comparisons ("as heavy as 9 cars", "thinner than a human hair", "a water bottle squeezed to the size of a
  shot glass"); 1 or 2 such comparisons per video, each in its own [SCENE].
- Only well-known, accurate facts an engineer would agree with. When a number varies or is an estimate, say so
  ("about", "up to", "engineers estimate", "a typical fridge"). Never invent technologies, records, studies or quotes.
  If you are not sure of a number, leave it out.
- Put [PAUSE] right after a reveal or an important result (the voice stops for a moment): "It never needed more gas.
  [PAUSE]".
- End with a satisfying payoff (the whole thing working), then a short line that makes people want the next video.
Format (exactly):
[TITLE] title
[STYLE] a short visual style line
[SCENE] what we see in this shot (objects, the part in focus, what moves)
NARRATOR: the narration for this shot (1-3 sentences)
...repeat [SCENE] + NARRATOR for every shot...
Long videos: [CHAPTER] name lines between parts.
Reply with JSON only: {"script": "the full script text with \\n between lines"}"""


def write_from_topic(topic: str, length: str = "short", language: str = "en", note: str = "", rep=None,
                     video_format: str = "auto", seconds: int | float = 0) -> tuple[str, str]:
    """Topic → script text in our format. Returns (text, provider).

    The script must hit the target length (about 150 words a minute): a short reply is sent back once with the
    word count. With a Gemini key that stays busy: stop with "Gemini is busy" (no garbage). No key: a template."""
    from . import config, formats, net  # noqa: PLC0415
    from .messages import StopRequested  # noqa: PLC0415

    topic = (topic or "").strip()
    if not topic:
        raise FriendlyError("Type a topic first.", "For example: how cow poop becomes electricity.")
    fkey = formats.resolve(video_format, topic)
    words = paste.target_words(length, seconds, fkey)
    secs = paste.target_seconds(length, seconds, fkey)
    shots = max(5, round(words / paste.WORDS_PER_SCENE.get(length, 15)))
    payload = {"topic": topic, "target_words": words,
               "word_rule": f"The NARRATOR lines together must have {int(words * 0.95)}-{int(words * 1.1)} words "
                            f"(about {secs} seconds at 150 words a minute). Count them before you answer.",
               "shots": f"{max(4, shots - 2)}-{shots + 2}",
               "language": "Persian (Farsi)" if language == "fa" else "English",
               "length": f"about {secs} seconds" if secs < 240 else
                         f"about {round(secs / 60)} minutes, a mini cliffhanger every 2 minutes, [CHAPTER] lines between parts",
               "creator_note": note}
    payload["format"] = {"name": formats.get(fkey)["label"], "rules": formats.get(fkey)["rules"]}
    best = {"n": 0, "text": ""}

    def validate(obj):
        text = str((obj or {}).get("script", "")) if isinstance(obj, dict) else ""
        parsed = paste.parse_lines(text)
        n = sum(len(b["lines"]) for b in parsed["blocks"])
        if n < 4:
            raise ValueError("the script needs at least 4 NARRATOR lines with [SCENE] lines")
        said = paste.count_words(" ".join(ln["text"] for b in parsed["blocks"] for ln in b["lines"]))
        if said > best["n"]:
            best.update(n=said, text=text)
        if said < words * 0.85:
            raise ValueError(f"the NARRATOR lines have only {said} words, but this {secs} s video needs about {words} "
                             f"words. Keep every line and add {words - said} more words: more real steps, a "
                             "comparison, a 'why'")
        if said > words * 1.35:
            raise ValueError(f"the NARRATOR lines have {said} words, too long: it needs about {words} words")

    def finish(text: str) -> str:
        text = text.strip() + "\n"
        if not text.lstrip().startswith("[TITLE]"):
            text = f"[TITLE] {topic[:1].upper() + topic[1:]}\n" + text
        return text

    try:
        provider, obj = llm.generate_json(SCRIPT_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate,
                                          rep=rep, task="script", temperature=0.85, max_tokens=8000, strong=True)
        return finish(str(obj["script"])), provider
    except StopRequested:
        raise
    except Exception as exc:  # noqa: BLE001
        if best["n"] >= words * 0.6:  # close enough: better than no script
            if rep is not None:
                rep.warn(f"The AI script has {best['n']} words (the target is {words}). The video will be a bit "
                         "shorter; you can add lines on the Script step.")
            return finish(best["text"]), "Gemini (shorter than asked)"
        if config.secret("GEMINI_API_KEY") and isinstance(exc, net.AllProvidersFailed):
            raise FriendlyError(*llm.BUSY_TEXT) from None
        if rep is not None:
            rep.warn("No free AI key, so I made a simple starter script. Edit it, or add a free GEMINI_API_KEY.")
        return template_script(topic), "Template (no AI)"


VERBS = {"spin": "It turns, around and around.", "slide": "It slides up and down, again and again.",
         "rod": "It turns pushing into spinning.", "valve": "It opens and closes at exactly the right moment.",
         "pulse": "It fires a tiny spark.", "chamber": "Here gas is squeezed, burned and pushed out.",
         "open": "It opens and closes.", "lift": "It travels up and down.", "stretch": "It holds the weight.",
         "level": "It floats on the water and rises with it.", "swing": "It swings back and forth."}


def machine_template(topic: str) -> str | None:
    """No AI: a machine from the library named in the topic → one shot per real working part (no invented facts)."""
    from .world import assets, planner  # noqa: PLC0415

    found = [a for a in planner.find_assets(topic) if {"machine", "cutaway"} & set(assets.REGISTRY[a].tags)]
    if not found:
        return None
    name = found[0]
    model = assets.build(name)
    t = topic.strip().rstrip("?.!")
    nice = name.replace("_", " ")
    lines = [f"[TITLE] {t[:1].upper() + t[1:]}",
             f"[SCENE] close on the {nice}", "NARRATOR: You use it all the time. But have you seen inside?",
             f"[SCENE] the {nice} cut open", f"NARRATOR: Here is the {nice}, cut open."]
    if model.tour:  # the machine's own tour: its key parts in working order, one plain sentence each
        for part, sentence in model.tour[:9]:
            lines += [f"[SCENE] close on the {part.replace('_', ' ')}", f"NARRATOR: {sentence}"]
    else:
        done = 0
        for part in assets.focus_points(name):
            ks = [p for p in model.parts if p.name == part or p.name.startswith(part + "_") or
                  p.name.rstrip("0123456789") == part]
            mos = [m for p in ks for m in (p.motion if isinstance(p.motion, list) else [p.motion] if p.motion else [])]
            kind = next((m.get("type") for m in mos if m.get("type") in VERBS and m.get("type") != "lift"), None)
            if kind is None or done >= 7:
                continue
            words = part.replace("_", " ")
            lines += [f"[SCENE] close on the {words}", f"NARRATOR: Here is the {words}. {VERBS[kind]}"]
            done += 1
    lines += [f"[SCENE] the whole {nice} working", "NARRATOR: Every part works together, every single time.",
              f"[SCENE] close on the {nice}", "NARRATOR: Next: what happens when one of these parts fails?"]
    return "\n".join(lines) + "\n"


def template_script(topic: str) -> str:
    known = machine_template(topic)
    if known:
        return known
    t = topic.strip().rstrip("?.!")
    title = t[:1].upper() + t[1:]
    return (f"[TITLE] {title}\n"
            f"[SCENE] a wide shot of the whole thing\nNARRATOR: You use it every day. You've never seen inside it.\n"
            f"[SCENE] the main machine, close\nNARRATOR: Here is {t.lower()}, step by step.\n"
            f"[SCENE] the first part starts moving\nNARRATOR: First, everything starts here.\n"
            f"[SCENE] a cutaway of the inside\nNARRATOR: Inside, the real work happens.\n"
            f"[SCENE] the result, lights turn on\nNARRATOR: And that's the payoff.\n"
            f"[SCENE] a dark close up\nNARRATOR: But one part of it is more dangerous than you think.\n")


def normalize_script(raw: dict, opts: EpisodeOptions) -> dict:
    scenes = []
    for i, sc in enumerate(raw.get("scenes") or []):
        lines = [{"speaker": str(ln.get("speaker") or NARRATOR), "text": re.sub(r"\s+", " ", str(ln["text"])).strip()}
                 for ln in sc.get("lines", []) if str(ln.get("text", "")).strip()]
        if not lines:
            continue
        scenes.append({"id": f"s{len(scenes) + 1:02d}", "lines": lines, "narration": " ".join(x["text"] for x in lines),
                       "visual": str(sc.get("visual") or "").strip(), "chapter": str(sc.get("chapter") or "").strip(),
                       "kind": "hook" if i == 0 else "scene"})
    if scenes:
        scenes[-1]["kind"] = "cliffhanger" if len(scenes) > 1 else "hook"
    first = scenes[0]["narration"] if scenes else ""
    return {"title": str(raw.get("title") or "Untitled").strip(), "language": raw.get("language", "en"),
            "length": opts.length, "source": raw.get("source", "paste"), "provider": raw.get("provider", ""),
            "style": str(raw.get("style") or "").strip(), "scenes": scenes,
            "hook_text": beats.hook_text(first, raw.get("language", "en")),
            "thumbnail_text": " ".join(str(raw.get("title") or "").split()[:4]),
            "music_mood": _explainer_mood(" ".join(s["narration"] for s in scenes)),
            "summary": " ".join(" ".join(s["narration"] for s in scenes).split()[:60]),
            "cliffhanger": scenes[-1]["narration"] if scenes else "", "text": raw.get("text", "")}


def _explainer_mood(text: str) -> str:
    """Music for an explainer: the curious 'explainer' bed by default, tense or dark only when the story is."""
    m = beats.guess_mood(text, "explainer")
    return m if m in ("tense", "dark", "action", "epic", "sad", "mysterious") else "explainer"


def script_from_text(series: Series, episode: Episode, opts: EpisodeOptions, text: str, rep) -> dict:
    """Read your script, split it into scenes and save it."""
    from .characters import add_character, set_description  # noqa: PLC0415

    rep.step("📝 Reading your script")
    with Timer():
        parsed = paste.parse_lines(text)
    if not parsed["blocks"]:
        raise FriendlyError("I couldn't find any story lines in your script.",
                            "Paste the text (NARRATOR: lines, with [SCENE] lines for the shots), then press Generate.")
    warning = paste.length_warning(text, opts.length)
    if warning:
        rep.warn("📏 " + warning)
        rep.record("warn", "Script length", warning.split(".")[0])
    for c in parsed.get("characters", []):
        set_description(series, c["name"].title() if paste.LATIN.search(c["name"]) else c["name"], c["description"])
    for sp in parsed["speakers"]:
        if series.character(sp) is None:
            add_character(series, sp.title() if paste.LATIN.search(sp) else sp)
    scenes = paste.to_scenes(parsed, opts.length)
    words = " ".join(ln["text"] for sc in scenes for ln in sc["lines"]).split()
    title = parsed["title"] or " ".join(words[:6]).rstrip(".,!?؟") + "…"
    raw = {"title": title, "language": parsed["language"], "scenes": scenes, "source": opts.source,
           "style": parsed.get("style", ""), "text": text}
    script = normalize_script(raw, opts)
    if parsed["language"] not in opts.languages:
        opts.languages = [parsed["language"]]
    series.save()
    episode.save_options(opts)
    save_script(episode, script)
    rep.ok(f"Script ready: “{title}”, {len(script['scenes'])} scenes")
    rep.record("ok", "Script", f"{len(script['scenes'])} scenes")
    return script


def save_script(episode: Episode, script: dict) -> None:
    episode.save_script(script)
    episode.script_md_path.write_text(script.get("text") or to_text(script), encoding="utf-8")


def to_text(script: dict) -> str:
    """The script back in the paste format."""
    lines = [f"[TITLE] {script.get('title', '')}"]
    if script.get("style"):
        lines.append(f"[STYLE] {script['style']}")
    for sc in script["scenes"]:
        if sc.get("chapter"):
            lines.append(f"[CHAPTER] {sc['chapter']}")
        lines.append(f"[SCENE] {sc.get('visual', '')}".rstrip())
        lines += [f"{ln['speaker']}: {ln['text']}" for ln in sc["lines"]]
    return "\n".join(lines) + "\n"
