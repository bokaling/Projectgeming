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
Topics: how things work, what happens if, how things are made, inside machines, science, engineering, history of inventions.
Retention rules:
- The first line is a shocking statement or question, max 10 words. No slow intros ("Have you ever wondered", "In this video", "Once upon a time").
- Something new every 5 seconds: a new step, object, number or twist. Short, punchy, spoken sentences.
- Use specific, true numbers (tons, degrees, days, kilowatt hours, percent) - never vague words.
- Facts must be safe: only well-known, accurate facts that an engineer would agree with. If a number is an estimate or
  varies, say so ("about", "up to", "engineers estimate", "a typical fridge"). Never invent technologies, records,
  studies or quotes. If you are not sure of a number, leave it out.
- Every shot can be shown in 3D: objects, machines, liquids, gas, particles, cutaways, zooming into tiny things.
- Machines: name the REAL parts (piston, valve, compressor, float, sheave…) and show each one working in its own shot,
  in the order things really happen. [SCENE] says literally what we see (the part, what moves, where it flows).
- End with a satisfying payoff, then a cliffhanger line for the next episode.
Format (exactly):
[TITLE] title
[STYLE] a short visual style line
[SCENE] what we see in this shot (objects and what moves)
NARRATOR: the narration for this shot (1-2 sentences)
...repeat [SCENE] + NARRATOR for every shot...
Reply with JSON only: {"script": "the full script text with \\n between lines"}"""


def write_from_topic(topic: str, length: str = "short", language: str = "en", note: str = "", rep=None,
                     video_format: str = "auto") -> tuple[str, str]:
    """Topic → script text in our format. Returns (text, provider). Never fails: a simple template if no AI works."""
    topic = (topic or "").strip()
    if not topic:
        raise FriendlyError("Type a topic first.", "For example: how cow poop becomes electricity.")
    words = paste.TARGET_WORDS.get(length, 150)
    payload = {"topic": topic, "target_words": words, "shots": "12-14" if length == "short" else "70-90",
               "language": "Persian (Farsi)" if language == "fa" else "English",
               "length": "about 60 seconds" if length == "short" else "about 10 minutes, a mini cliffhanger every 2 minutes, "
                                                                     "[CHAPTER] lines between parts",
               "creator_note": note}
    from . import formats  # noqa: PLC0415

    fkey = formats.resolve(video_format, topic)
    payload["format"] = {"name": formats.get(fkey)["label"], "rules": formats.get(fkey)["rules"]}

    def validate(obj):
        text = str((obj or {}).get("script", "")) if isinstance(obj, dict) else ""
        parsed = paste.parse_lines(text)
        n = sum(len(b["lines"]) for b in parsed["blocks"])
        if n < 4:
            raise ValueError("the script needs at least 4 NARRATOR lines with [SCENE] lines")

    try:
        provider, obj = llm.generate_json(SCRIPT_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate,
                                          rep=rep, task="script", temperature=0.85, max_tokens=8000, strong=True)
        text = str(obj["script"]).strip() + "\n"
        if not text.lstrip().startswith("[TITLE]"):
            text = f"[TITLE] {topic[:1].upper() + topic[1:]}\n" + text
        return text, provider
    except Exception as exc:  # noqa: BLE001
        from .messages import StopRequested  # noqa: PLC0415

        if isinstance(exc, StopRequested):
            raise
        if rep is not None:
            rep.warn("All free AI writers are busy, so I made a simple starter script. Edit it, or try again later.")
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
