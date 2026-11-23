"""Video formats: each has its own script rules, pacing, captions, music and ending.

"auto" picks one from the topic ("what happens if…" → what_if, "how … is made/built" → how_made,
"history of…" → history, "top 5…" → top_list, "story…" → story, everything else → how_it_works).
"""

from __future__ import annotations

import re

FORMATS = {
    "how_it_works": dict(label="How it works", captions="keywords", ending="overview", mood="explainer",
                         rules="Open on one striking, close moment (a cable snapping, a door opening in slow motion, a "
                               "spark in a cylinder). Then follow the thing step by step from start to finish: cut it "
                               "open and name each real working part as it does its job (pistons move, valves open, "
                               "liquid flows, lights turn on), one step per shot, in the real order. Use numbers people "
                               "can picture. End with the whole machine working, then a cliffhanger."),
    "what_if": dict(label="What happens if", captions="keywords", ending="overview", mood="tense",
                    rules="Start with the most shocking consequence, then go back and escalate step by step with time "
                          "stamps and numbers (after 1 second, after 1 hour, after 1 day…). End with the final outcome."),
    "how_made": dict(label="How it's made", captions="keywords", ending="overview", mood="explainer",
                     rules="Raw material first, then every making step in order (cut, move, shape, join, finish), with "
                           "numbers (tons, days, workers). End with the finished product, big."),
    "history": dict(label="History of", captions="keywords", ending="overview", mood="epic",
                    rules="Use years and dates as numbers, before/after moments, the inventors or builders as blocky "
                          "people, and one surprising fact per shot. End on how it changed the world."),
    "top_list": dict(label="Top 5 / 10", captions="keywords", ending="overview", mood="action",
                     rules="A countdown: one item per shot or two, '#5 … #1' as number keywords, the most surprising "
                           "item last. Short, punchy lines."),
    "story": dict(label="Story", captions="words", ending="card", mood="auto",
                  rules="Original blocky characters with names, emotions on their faces (happy, sad, angry, surprised, "
                        "scared), short dialog lines, a twist and a cliffhanger. Captions are single big words."),
}
CHOICES = [(FORMATS["how_it_works"]["label"] + " (default)", "how_it_works"), ("Auto (from the topic)", "auto")] + [
    (f["label"], k) for k, f in FORMATS.items() if k != "how_it_works"]
PATTERNS = [
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
