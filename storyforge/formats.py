"""Video formats: each has its own script rules, pacing, captions, music and ending.

"auto" picks one from the topic ("what happens if…" → what_if, "how … is made/built" → how_made,
"history of…" → history, "top 5…" → top_list, "story…" → story, everything else → how_it_works).
"""

from __future__ import annotations

import re

FORMATS = {
    "how_it_works": dict(seconds=80, label="How it works", captions="keywords", ending="overview", mood="explainer",
                         rules="Open with a short question that the first shot shows, then a surprising myth buster "
                               "in the first 10 seconds (what people believe vs what really happens). Then follow the "
                               "thing step by step in the real order it works: cut it open and name each real working "
                               "part as it does its job, one clear idea with a simple 'why' per step, 1-3 sentences per "
                               "shot. Add 1-2 everyday comparisons for big or tiny numbers. Calm and curious; punchy only "
                               "for the hook, reveals and ending. End with the whole machine working."),
    "what_if": dict(seconds=60, label="What happens if", captions="keywords", ending="overview", mood="tense",
                    rules="Start with the most shocking consequence, then go back and escalate step by step with time "
                          "stamps and numbers (after 1 second, after 1 hour, after 1 day…). End with the final outcome."),
    "how_made": dict(seconds=80, label="How it's made", captions="keywords", ending="overview", mood="explainer",
                     rules="Raw material first, then every making step in order (cut, move, shape, join, finish), with "
                           "numbers (tons, days, workers). End with the finished product, big."),
    "history": dict(seconds=90, label="History of", captions="keywords", ending="overview", mood="epic",
                    rules="Use years and dates as numbers, before/after moments, the inventors or builders as blocky "
                          "people, and one surprising fact per shot. End on how it changed the world."),
    "top_list": dict(seconds=60, label="Top 5 / 10", captions="keywords", ending="overview", mood="action",
                     rules="A countdown: one item per shot or two, '#5 … #1' as number keywords, the most surprising "
                           "item last. Short, punchy lines."),
    "documentary": dict(seconds=150, label="3D Documentary", captions="karaoke", ending="overview", mood="tense",
                        rules="A TRUE story (disaster, rescue, history, survival) told in a dark cinematic way. Structure: "
                              "a cold open (the most gripping moment, then 'but let's go back'), the build up (where, "
                              "when, who: real date and place), the disaster, the struggle, the twist, the ending. A "
                              "mini cliffhanger about every 30 seconds ('but nobody knew…'). Only real, verified facts: "
                              "dates, places, numbers, names; say 'about' or 'experts estimated' when unsure; never "
                              "invent quotes or details. Cross-section views (mountains, buildings, ships, the earth) "
                              "make the place clear. Calm, serious voice; short punchy lines for the big moments."),
    "story": dict(seconds=60, label="Story", captions="words", ending="card", mood="auto",
                  rules="Original blocky characters with names, emotions on their faces (happy, sad, angry, surprised, "
                        "scared), short dialog lines, a twist and a cliffhanger. Captions are single big words."),
}
CHOICES = [(FORMATS["how_it_works"]["label"] + " (default)", "how_it_works"), ("Auto (from the topic)", "auto")] + [
    (f["label"], k) for k, f in FORMATS.items() if k != "how_it_works"]
PATTERNS = [
    (r"\btrapped\b|\brescue[ds]?\b|\bdisaster\b|\bsurviv|\btrue story\b|\bcollapse[ds]?\b|\bsank\b|"
     r"\bshipwreck\b|\bcrash(ed)?\b|\bdocumentary\b|\btragedy\b|\bexpedition\b", "documentary"),
    (r"\bwhat (would )?happens? (if|to|inside|when)\b|\bwhat if\b", "what_if"),
    (r"\bhow\b.{0,40}\b(are|is|were|was|get|gets) (made|built|produced|manufactured|created)\b|\bhow .{0,30}\bmade\b",
     "how_made"),
    (r"\bhistory of\b|\binvent(ed|ion)\b|\bancient\b|\bwho built\b", "history"),
    (r"\btop \d+\b|\b\d+ (biggest|best|worst|strangest|largest|deadliest)\b", "top_list"),
    (r"\bstory\b|\bonce upon\b|\bepisode\b", "story"),
]


def detect(text: str) -> str:
    t = (text or "").lower()
    for pattern, key in PATTERNS:
        if re.search(pattern, t):
            return key
    return "how_it_works"


def resolve(choice: str, text: str = "") -> str:
    """The user's choice, or the format that fits the topic/title when it is "auto"."""
    return choice if choice in FORMATS else detect(text)


def get(key: str) -> dict:
    return FORMATS.get(key) or FORMATS["how_it_works"]


def end_card(key: str, wanted: bool = False) -> bool:
    """"Part X" end cards only for stories. Explainers and documentaries never get one, whatever the setting."""
    return get(key)["ending"] == "card" or (wanted and key == "story")


EXPLAINER_MOODS = {"explainer", "hopeful", "playful", "calm", "action", "epic"}  # curious / upbeat beds
DOCUMENTARY_MOODS = {"tense", "dark", "mysterious", "epic", "hopeful", "sad"}


def music_mood(key: str, chosen: str = "auto", script_mood: str = "") -> str:
    """The music bed: your choice, else the format's mood. How it works is always curious/upbeat (never sad)."""
    fmt = get(key)
    if chosen and chosen != "auto":
        mood = chosen
    elif fmt["mood"] == "auto":
        mood = script_mood or "mysterious"
    else:
        mood = fmt["mood"]
    if key in ("how_it_works", "how_made", "top_list") and mood not in EXPLAINER_MOODS:
        mood = fmt["mood"]
    if key == "documentary" and mood not in DOCUMENTARY_MOODS:
        mood = fmt["mood"]
    return mood
