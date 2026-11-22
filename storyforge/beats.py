"""Story beats: what in the text is a hook, a twist, a reveal, a scary moment or an emotion.

Used by the script doctor (scores), the 3D camera (punch-ins, shake, white flash), the sound
design (music drops, booms) and the music mood.
All simple word lists: instant, offline, English + some Farsi.
"""

from __future__ import annotations

import re

STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been being it its this that
these those he she they them his her their him i you we me my your our us not no so do does did have has had will would
can could just then than there here what when where who why how which into out up down over under again very really
very also only about all any some one two""".split())

SLOW_INTRO = re.compile(
    r"^\s*(at\s+(\d|exactly|around|about|midnight|night|dawn|noon|three|two|four|one|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)|once upon a time|one day|long ago|years ago|a long time ago|it was (a|an|the|just)\b|this is the "
    r"story|this is a story|in this video|hi\b|hello\b|hey (guys|everyone|there)|let me tell you|there (was|once was|"
    r"lived)\b|my name is|today (i|we)\b|welcome\b|so,? (one|this|there)|it all (started|began)|"
    r"روزی روزگاری|یک روز|سال‌ها پیش|سلام)", re.I)
SHOCK = ["never", "nobody", "no one", "dead", "died", "death", "killed", "kill", "murder", "murdered", "vanished",
         "disappeared", "missing", "secret", "impossible", "last", "blood", "scream", "screamed", "warning", "buried",
         "alive", "wrong", "lie", "lied", "truth", "only", "real", "body", "bodies", "ghost", "stranger", "trapped",
         "gone", "erased", "strange", "deadly", "evil", "cursed", "forbidden", "terrifying", "worst",
         "مرده", "مرگ", "خون", "هیچ‌کس", "هرگز", "ناپدید", "راز", "جیغ", "زنده", "دروغ"]
STAKES = ["die", "dies", "death", "dead", "kill", "killed", "lose", "lost", "forever", "never", "last", "only",
          "trapped", "missing", "gone", "too late", "before", "or else", "life", "lives", "family", "child", "children",
          "daughter", "son", "wife", "husband", "mother", "father", "danger", "dangerous", "deadly", "risk", "survive",
          "escape", "hunt", "hunted", "chase", "police", "prison", "debt", "fired", "everything", "minutes", "hours",
          "seconds", "countdown", "bomb", "poison", "sick", "save",
          "مرگ", "بمیرد", "خانواده", "دختر", "پسر", "مادر", "پدر", "خطر", "فرار", "نجات", "زندان", "دقیقه"]
CURIOSITY = ["?", "but", "until", "what", "why", "who", "how", "nobody knew", "no one knew", "secret", "the reason",
             "turns out", "little did", "something", "someone", "somewhere", "strange", "weird", "didn't know",
             "wasn't", "couldn't explain", "mystery", "except", "the problem", "here's", "wonder", "unknown",
             "چرا", "چه", "کی", "اما", "ولی", "تا اینکه", "راز", "عجیب", "کسی", "چیزی"]
REVEAL = ["turns out", "turned out", "realized", "realised", "was actually", "the truth", "revealed", "that's when",
          "that is when", "it was him", "it was her", "it was me", "it wasn't", "the real", "all along", "found out",
          "discovered", "recognized", "recognised", "was never", "was already", "had been", "was dead", "was alive",
          "instead", "suddenly", "and then", "it was", "saw", "behind her", "behind him", "behind me",
          "فهمید", "حقیقت", "ناگهان", "معلوم شد", "در واقع", "پشت سرش"]
TWIST = ["but", "then", "suddenly", "until", "that's when", "instead", "except", "however", "and then", "turns out",
         "turned out", "realized", "only to", "اما", "ولی", "ناگهان", "تا اینکه", "بعد"]
SCARY = ["scream", "screamed", "screaming", "blood", "bloody", "dead", "body", "corpse", "behind", "knock", "knocked",
         "knocking", "bang", "gun", "gunshot", "shot", "crash", "crashed", "slammed", "grabbed", "monster", "demon",
         "ghost", "footsteps", "killer", "knife", "explosion", "exploded", "attack", "attacked", "fell", "fall", "run",
         "ran", "dark figure", "shadow", "whisper", "whispered", "growl", "thunder",
         "جیغ", "خون", "جسد", "پشت", "تفنگ", "شلیک", "انفجار", "سایه", "زمزمه", "در زد"]
RESOLVED_END = re.compile(r"(happily|the end\b|lived (on|happily)|everything (was|is) (fine|okay|ok|alright)|safe at "
                          r"last|finally safe|and that'?s (how|why|it)|they were (fine|safe)|all was well|پایان|"
                          r"خوشبخت)", re.I)
VAGUE = ["very", "really", "thing", "things", "stuff", "a lot", "kind of", "sort of", "somehow", "nice", "good", "bad",
         "big", "some kind", "basically", "pretty", "lots of", "many", "actually", "just"]
LIGHT_HINTS = {"neon": "neon signs", "candle": "candlelight", "fire": "firelight", "flashlight": "flashlight beams",
               "torch": "torchlight", "moon": "moonlight", "screen": "screen glow", "lamp": "lamp light",
               "lantern": "lantern light", "glow": "", "radio": "", "headlight": "headlights", "lightning": "lightning"}
PLACES = ["laboratory", "lab", "lighthouse", "house", "forest", "woods", "city", "street", "taxi", "car", "school",
          "hospital", "ship", "sea", "ocean", "desert", "cave", "castle", "office", "apartment", "church", "village",
          "mountain", "road", "highway", "motel", "hotel", "basement", "attic", "bunker", "station", "train", "subway",
          "plane", "island", "jungle", "prison", "farm", "cabin", "bridge", "tunnel", "mine", "space station",
          "spaceship", "museum", "library", "mall", "hallway", "kitchen", "bedroom", "bathroom", "garage", "lake",
          "river", "beach", "graveyard", "cemetery", "factory", "warehouse", "asylum", "camp", "tent", "bar", "diner"]
TIMES = [("night", r"\b(night|midnight|\d\s?a\.?m\b|[1-4] in the morning|three in the morning|dark|moon|stars)\b|شب"),
         ("dawn", r"\b(dawn|sunrise|early morning)\b|سحر|طلوع"),
         ("dusk", r"\b(sunset|dusk|evening|twilight)\b|غروب|عصر"),
         ("daytime", r"\b(noon|afternoon|sunny|daylight|morning|day)\b|روز|ظهر")]
WEATHER = [("heavy rain", r"\b(rain|raining|rainy|downpour)\b|باران"), ("storm", r"\b(storm|stormy|lightning|thunder)\b|طوفان"),
           ("snow", r"\b(snow|snowing|blizzard)\b|برف"), ("fog", r"\b(fog|foggy|mist|misty|haze)\b|مه"),
           ("wind", r"\b(wind|windy|gust)\b|باد")]
MOOD_LIGHT = {
    "dark": ("cold blue shadows with sickly green accents", "horror"),
    "tense": ("cold blue and amber light, deep shadows", "thriller"),
    "mysterious": ("misty teal and violet light", "mystery"),
    "sad": ("muted grey-blue light", "drama"),
    "hopeful": ("warm golden light", "uplifting drama"),
    "action": ("high-contrast orange and teal light", "action thriller"),
    "epic": ("dramatic orange and purple sky light", "epic adventure"),
    "romantic": ("warm pink and gold candlelight", "romance"),
    "calm": ("soft natural light", "drama"),
    "playful": ("bright saturated colors", "comedy"),
}
# facial expression from the words (never smiling unless the script clearly says so)
EXPRESSIONS = [
    ("smiling warmly", r"\b(smile[sd]?|smiling|laugh(s|ed|ing)?|grin(s|ned)?|happy|joy(ful)?|delighted|cheer(ed|ful)?)\b"
                       r"|لبخند|خندید|خوشحال"),
    ("terrified, wide eyes, mouth slightly open", r"\b(scream(s|ed|ing)?|terrified|afraid|scared|fear|horror|panic(ked)?"
                                                  r"|trembl(e|ed|ing)|shaking|monster|ghost|blood)\b|ترس|جیغ|وحشت|خون"),
    ("shocked, wide eyes, eyebrows raised", r"\b(shock(ed)?|gasp(ed)?|froze|frozen|realized|realised|couldn't believe|"
                                            r"stunned|impossible|no way)\b|شوکه|باورش نمی|فهمید"),
    ("angry, clenched jaw, furrowed brows", r"\b(angry|furious|rage|yell(ed)?|shout(ed)?|hate[sd]?|slammed|fight)\b"
                                           r"|عصبانی|فریاد زد|خشم"),
    ("sad, teary eyes, looking down", r"\b(cr(y|ied|ies|ying)|tears?|sad|grief|sorry|alone|goodbye|mourn|lost)\b"
                                      r"|گریه|اشک|غمگین|تنها|خداحافظ"),
    ("tense, alert, worried frown", r"\b(whisper(ed)?|quiet|listen(ed)?|careful|watch(ing|ed)?|someone|footsteps|"
                                    r"knock(ed|ing)?|wait(ed)?|behind)\b|زمزمه|صدای پا|در زد"),
    ("determined, focused stare", r"\b(must|decided|determined|no choice|fight back|will find|promise[sd]?)\b|تصمیم"),
    ("confused, frowning", r"\b(confused|strange|weird|why|how|didn't understand|doesn't make sense)\b|عجیب|چرا"),
]
MOOD_EXPRESSION = {"dark": "grim, serious", "tense": "tense, worried", "mysterious": "curious, uneasy",
                   "sad": "sad, serious", "action": "intense, determined", "hopeful": "hopeful, serious",
                   "epic": "determined, serious", "calm": "calm, serious", "romantic": "tender, serious",
                   "playful": "curious, serious"}


def norm(word: str) -> str:
    return re.sub(r"[^\w'’]", "", (word or "").lower()).replace("’", "'")


def has_any(text: str, words: list[str]) -> list[str]:
    low = " " + (text or "").lower() + " "
    found = []
    for w in words:
        if w == "?":
            if "?" in low or "؟" in low:
                found.append(w)
        elif re.search(r"(?<![\w'])" + re.escape(w) + r"(?![\w'])", low):
            found.append(w)
    return found


def count_any(text: str, words: list[str]) -> int:
    low = " " + (text or "").lower() + " "
    n = 0
    for w in words:
        if w == "?":
            n += low.count("?") + low.count("؟")
        else:
            n += len(re.findall(r"(?<![\w'])" + re.escape(w) + r"(?![\w'])", low))
    return n


def expression(text: str, mood: str = "") -> str:
    """Facial expression for a character in this moment. Not smiling unless the words clearly say so."""
    for expr, pattern in EXPRESSIONS:
        if re.search(pattern, text or "", re.I):
            return expr if expr.startswith("smiling") else expr + ", not smiling"
    return MOOD_EXPRESSION.get(mood, "serious") + ", not smiling"


def auto_mood_lock(text: str, mood: str = "mysterious") -> str:
    """Make a [STYLE] line from the script: time of day, weather, place, light/colors, genre."""
    low = (text or "").lower()
    time_of_day = next((name for name, pat in TIMES if re.search(pat, low)), "")
    if not time_of_day:
        time_of_day = "night" if mood in ("dark", "tense", "mysterious") else "overcast day"
    weather = [name for name, pat in WEATHER if re.search(pat, low)][:2]
    counts = {p: len(re.findall(r"\b" + re.escape(p) + r"s?\b", low)) for p in PLACES}
    place = max(counts, key=counts.get) if counts and max(counts.values()) else ""
    if time_of_day == "night" and mood in ("hopeful", "calm", "playful", "romantic"):
        mood = "mysterious"  # a night story doesn't get warm sunny colors
    light, genre = MOOD_LIGHT.get(mood, MOOD_LIGHT["mysterious"])
    sources = [v for k, v in LIGHT_HINTS.items() if v and re.search(r"\b" + k, low)][:2]
    parts = [time_of_day] + weather + ([place] if place else []) + sources + [light, genre]
    return ", ".join(dict.fromkeys(p for p in parts if p))


def first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?؟…])\s+", (text or "").strip())
    return parts[0] if parts else ""


def hook_text(first_line: str, lang: str = "en", max_words: int = 7) -> str:
    """Short on-screen hook text (top of the screen, first 3 s), from the first line."""
    s = first_sentence(first_line).strip().strip('"“”')
    s = SLOW_INTRO.sub("", s).strip(" ,.-") if SLOW_INTRO.match(s) and len(s.split()) > 4 else s
    words = s.split()
    if len(words) > max_words:
        s = " ".join(words[:max_words - 1]).rstrip(",;:،") + "…"
    return s[:1].upper() + s[1:] if lang != "fa" else s


def key_word_index(words: list[str]) -> int:
    """Which word of a short caption group is the 'key word' (highlighted)."""
    best, score = 0, -1.0
    strong = set(SHOCK + STAKES + SCARY)
    for i, w in enumerate(words):
        n = norm(w)
        s = 0.0
        if n in strong:
            s += 5
        if re.search(r"\d", n):
            s += 4
        if w[:1].isupper() and i > 0:
            s += 2  # a name
        if n not in STOP:
            s += min(len(n), 10) / 3
        if s > score:
            best, score = i, s
    return best


def is_key(word: str) -> bool:
    """A word strong enough to be highlighted on its own."""
    n = norm(word)
    return n in set(SHOCK + STAKES + SCARY) or bool(re.search(r"\d", n)) or (len(n) >= 7 and n not in STOP)


def phrase_times(words: list[dict], phrases: list[str]) -> list[float]:
    """Start times of the phrases in a timed word list [{'w', 's', 'e'}]."""
    toks = [norm(w["w"]) for w in words]
    out = []
    for ph in phrases:
        if ph == "?":
            continue
        parts = [norm(x) for x in ph.split()]
        n = len(parts)
        for i in range(len(toks) - n + 1):
            if toks[i:i + n] == parts:
                out.append(words[i]["s"])
    return sorted(set(round(t, 3) for t in out))


def thin(times: list[float], gap: float) -> list[float]:
    """Keep times at least `gap` seconds apart."""
    out: list[float] = []
    for t in sorted(times):
        if not out or t - out[-1] >= gap:
            out.append(t)
    return out


STRONG_REVEAL = ["turns out", "turned out", "realized", "realised", "was actually", "the truth", "revealed",
                 "that's when", "all along", "found out", "discovered", "recognized", "it was him", "it was her",
                 "it wasn't", "was dead", "was alive", "was never", "had been", "فهمید", "حقیقت", "معلوم شد"]


def find_beats(words: list[dict], total: float, length: str = "short") -> dict:
    """Times (seconds) of reveals (white flash + boom + music drop), scary words (shake), hook words (punch-in)."""
    reveal = phrase_times(words, STRONG_REVEAL)
    if len(reveal) < 2:  # few strong reveals: use twist words in the second half too
        extra = [t for t in phrase_times(words, ["suddenly", "and then", "but then", "instead", "until", "ناگهان"])
                 if t > total * 0.3]
        reveal = sorted(set(reveal + extra))
    reveal = thin(reveal, 8.0 if length == "short" else 20.0)
    scary = thin(phrase_times(words, SCARY), 2.5)
    return {"reveal": reveal, "scary": scary}


def hook_word_times(words: list[dict], start: float, end: float, n: int = 2) -> list[float]:
    """The 1-2 strongest words of the hook line (punch-in zoom on them)."""
    inside = [w for w in words if start <= w["s"] < end]
    if not inside:
        return []
    ranked = sorted(range(len(inside)), key=lambda i: -_strength(inside[i]["w"], i))
    picks = sorted(inside[i]["s"] for i in ranked[:n])
    return thin(picks, 0.6)


def _strength(word: str, i: int) -> float:
    n = norm(word)
    s = 0.0
    if n in set(SHOCK + STAKES + SCARY):
        s += 5
    if re.search(r"\d", n):
        s += 3
    if n not in STOP:
        s += min(len(n), 10) / 3
    return s - i * 0.05


# moods (music and the automatic style line)
MOOD_WORDS = {
    "dark": ["blood", "dead", "death", "kill", "grave", "corpse", "shadow", "demon", "مرگ", "خون", "مرده", "سایه"],
    "tense": ["run", "scream", "afraid", "fear", "danger", "knock", "heart", "suddenly", "ترس", "فریاد", "ناگهان", "خطر"],
    "mysterious": ["secret", "strange", "mystery", "whisper", "unknown", "fog", "راز", "عجیب", "زمزمه", "مه"],
    "sad": ["cry", "tears", "lost", "alone", "goodbye", "sorry", "گریه", "اشک", "تنها", "خداحافظ"],
    "hopeful": ["hope", "smile", "sunlight", "sun", "home", "safe", "امید", "لبخند", "خورشید"],
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
