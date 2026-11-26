"""Read a pasted script (the main way to make videos now).

Format:
    [TITLE] The Night Radio
    [SCENE] a taxi at night in the rain, neon signs        <- optional
    NARRATOR: The radio crackled at exactly 3 a.m.
    MIRA: Who's there?
    plain lines without a speaker are narration too

* Several scripts in one box: separate them with a line of ===== (batch mode).
* No [SCENE] lines? The text is split into scenes automatically.
* A [SCENE] with a very long text is split into a few shots of the same scene.
* Optional: [CHAPTER] Chapter name (for long videos / YouTube chapters).
* Optional: [CHARACTER] NIKOLA: man, 40s (a second speaker: "man"/"woman" picks the voice).
* Optional: [STYLE] clean low poly farm, warm sunset light (the look of the 3D world).
* Farsi works the same way (راوی: for the narrator).
"""

from __future__ import annotations

import re

NARRATOR = "NARRATOR"
NARRATOR_WORDS = {"narrator", "narration", "voiceover", "voice over", "vo", "راوی", "گوینده"}
SEPARATOR = re.compile(r"^\s*={5,}\s*$", re.M)
TAG = re.compile(r"^\s*\[(TITLE|SCENE|CHAPTER|CHARACTER|STYLE)\]\s*:?\s*(.*)$", re.I)
SPEAKER = re.compile(r"^\s*([^\s:][^:]{0,30}?)\s*[:：]\s*(.+)$")
PERSIAN = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
NARRATOR_SPEED = 1.0  # explainers and documentaries: calm, clear 1.0x (stories: STORY_SPEED)
STORY_SPEED = 1.1  # stories talk a little faster (more energy)
WORDS_PER_MINUTE = 150  # at 1.0x
WORDS_PER_SECOND = WORDS_PER_MINUTE / 60 * NARRATOR_SPEED
WORDS_PER_SCENE = {"short": 15, "long": 22}  # a shot = 1-3 sentences about one thing (4-8 s of voice)
TARGET_SECONDS = {"short": 80, "long": 540}
TARGET_WORDS = {"short": 200, "long": 1400}
# Length choices for vertical videos (seconds) and the long 16:9 range
SHORT_SECONDS = (30, 60, 80, 90, 120, 180)
LONG_SECONDS = (480, 540, 600)
PAUSE = re.compile(r"\[\s*PAUSE\s*\]", re.I)
PAUSE_SECONDS = 0.75  # [PAUSE] after a reveal: the voice stops this long


def narrator_speed(video_format: str = "how_it_works") -> float:
    return STORY_SPEED if video_format == "story" else NARRATOR_SPEED


def target_seconds(length: str = "short", seconds: int | float = 0, video_format: str = "how_it_works") -> int:
    """How long the video should be: your choice, else the format's default (How it works 80 s, documentary 150 s)."""
    if seconds and float(seconds) > 0:
        sec = float(seconds)
        return int(min(600, max(240, sec)) if length == "long" else min(180, max(20, sec)))
    if length == "long":
        return TARGET_SECONDS["long"]
    from . import formats  # noqa: PLC0415

    return int(formats.get(video_format).get("seconds", TARGET_SECONDS["short"]))


def target_words(length: str = "short", seconds: int | float = 0, video_format: str = "how_it_works") -> int:
    """About 150 words a minute at 1.0x (a story at 1.1x says a little more)."""
    sec = target_seconds(length, seconds, video_format)
    return int(round(sec * WORDS_PER_MINUTE / 60 * narrator_speed(video_format) / 5.0) * 5)


def split_scripts(text: str) -> list[str]:
    """Batch mode: one script per block between ===== lines."""
    return [p.strip() for p in SEPARATOR.split(text or "") if p.strip()]


def detect_language(text: str) -> str:
    return "fa" if len(PERSIAN.findall(text or "")) > len(LATIN.findall(text or "")) else "en"


WORD_SPLIT = re.compile(r"[\s\u2014\u2013/]+|\.{2,}|\u2026")  # spaces, em/en dashes, slashes, "..." and "…"
LABEL = re.compile(r"^\s*(?:[-•*_>]+\s*)?([A-Za-z\u0600-\u06FF][\w.'\- \u0600-\u06FF\u200c]{0,30}?)\s*"
                   r"(?:\([^)]{0,30}\))?\s*[*_]*\s*[:：]")


def count_words(text: str) -> int:
    """Spoken words, the way the narrator says them: "whispered—then" and "Wait...what" are 2 words,
    "don't" and "3:15" are 1. Punctuation alone is not a word."""
    return sum(1 for t in WORD_SPLIT.split(PAUSE.sub(" ", text or "")) if any(ch.isalnum() for ch in t))


def _clean_name(name: str) -> str:
    """'**MIRA (whispering)**' → 'MIRA'."""
    n = re.sub(r"\([^)]*\)", " ", name or "")
    return re.sub(r"\s+", " ", n.strip().strip("*_-•> ").strip())


def frequent_labels(text: str, min_count: int = 2) -> set[str]:
    """Title Case names used as a label at least twice ('Dr. Shaw: …' twice) are speakers too."""
    counts: dict[str, int] = {}
    for raw in (text or "").split("\n"):
        m = LABEL.match(raw)
        if m:
            n = _clean_name(m.group(1))
            if 1 <= len(n.split()) <= 3 and all(w[:1].isupper() for w in n.split() if w[:1].isalpha()):
                counts[n] = counts.get(n, 0) + 1
    return {n for n, c in counts.items() if c >= min_count}


def split_label(line: str, known: set[str]) -> tuple[str, str]:
    """'MIRA (whispering): "Who?"' → ('MIRA', 'Who?'). No label → (NARRATOR, line). Adds new speakers to `known`."""
    speaker, content = NARRATOR, line.strip()
    lm = LABEL.match(line)
    sm = SPEAKER.match(line)
    who = _speaker(lm.group(1), known) if lm else None
    if who:  # "MIRA (whispering): …", "**NARRATOR:** …"
        speaker, content = who, line[lm.end():].strip()
    elif sm and _speaker(sm.group(1), known):
        speaker, content = _speaker(sm.group(1), known), sm.group(2).strip()
    if speaker != NARRATOR:
        known.add(speaker)
    content = content.strip().strip("*_").strip()
    if content.count('"') % 2 == 1 or (content[:1] in '"“' and content[-1:] in '"”'):
        content = content.strip('"“”').strip()  # unbalanced or whole-line quotes
    return speaker, content


def _speaker(name: str, known: set[str]) -> str | None:
    """Is 'name' (text before a colon) a speaker? Returns the speaker name or None."""
    n = _clean_name(name)
    low = n.lower()
    if low in NARRATOR_WORDS:
        return NARRATOR
    if n.upper() in known or low in {k.lower() for k in known}:
        return n.upper() if LATIN.search(n) else n
    words = n.split()
    if 1 <= len(words) <= 3 and LATIN.search(n) and n == n.upper() and re.fullmatch(r"[A-Z][A-Z .'\-]*", n):
        return n  # ALL CAPS name, e.g. MIRA or DR. SHAW
    if PERSIAN.search(n) and len(words) <= 2 and not re.search(r"[.!?؟،]", n):
        return n  # Persian name followed by a colon
    return None


def parse_lines(text: str, known: set[str] = frozenset()) -> dict:
    """Turn script text into {'title', 'language', 'blocks': [{'visual', 'chapter', 'lines', 'para_breaks'}]}."""
    title = ""
    style = ""
    characters: list[dict] = []
    blocks: list[dict] = []
    cur: dict | None = None
    chapter = ""
    known = set(known)
    para = 0

    def new_block(visual: str = ""):
        nonlocal cur, chapter
        cur = {"visual": visual, "chapter": chapter, "lines": [], "from_tag": bool(visual)}
        chapter = ""
        blocks.append(cur)

    known |= frequent_labels(text)
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            para += 1
            continue
        if line.startswith("#") and not title:  # a markdown heading = the title
            title = line.lstrip("#").strip()
            continue
        line = re.sub(r"^[-•>]\s+", "", line)  # bullet points
        m = TAG.match(line)
        if m and m.group(1).upper() == "SCENE":  # "[SCENE] dark room NARRATOR: text" on one line: split it
            inline = re.search(r"\s((?:NARRATOR|Narrator|[A-Z][A-Z.'\-]{1,20}(?: [A-Z][A-Z.'\-]{1,20})?)\s*:\s*\S.*)$",
                               m.group(2))
            if inline and _speaker(inline.group(1).split(":")[0], known):
                new_block(m.group(2)[: inline.start()].strip() or " ")
                line = inline.group(1).strip()
                m = None
        if m:
            kind, value = m.group(1).upper(), m.group(2).strip()
            if kind == "TITLE":
                title = value
            elif kind == "STYLE":
                style = value
            elif kind == "CHARACTER":
                name, _, desc = value.partition(":")
                if name.strip():
                    characters.append({"name": name.strip(), "description": desc.strip()})
                    known.add(name.strip().upper() if LATIN.search(name) else name.strip())
            elif kind == "CHAPTER":
                chapter = value
                if cur is not None and not cur["lines"]:
                    cur["chapter"] = value
                    chapter = ""
                else:
                    cur = None  # a chapter always starts a new block
            else:
                new_block(value or " ")
            continue
        speaker, content = split_label(line, known)
        if not content:
            continue
        if cur is None:
            new_block("")
        cur["lines"].append({"speaker": speaker, "text": content, "para": para})
    blocks = [b for b in blocks if b["lines"]]
    all_text = " ".join(ln["text"] for b in blocks for ln in b["lines"])
    return {"title": title, "style": style, "language": detect_language(all_text), "blocks": blocks,
            "characters": characters,
            "speakers": sorted({ln["speaker"] for b in blocks for ln in b["lines"]} - {NARRATOR})}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟…])\s+", text.strip())
    return [p for p in parts if p.strip()]


def _word_count(text: str) -> int:
    return count_words(text)


def _pieces(sentence: str, target: int) -> list[str]:
    """Only very long sentences are split, and only at commas (natural pauses for the voice)."""
    if _word_count(sentence) <= target * 2:
        return [sentence]
    merged: list[str] = []
    for chunk in re.split(r"(?<=[,;:،؛])\s+", sentence):
        if merged and _word_count(merged[-1]) + _word_count(chunk) <= target * 1.3:
            merged[-1] += " " + chunk
        else:
            merged.append(chunk)
    return merged


def split_block(block: dict, target: int) -> list[dict]:
    """Split one block into scenes of about `target` words, at sentence ends (and paragraph breaks)."""
    units = []  # (speaker, sentence piece, para)
    for ln in block["lines"]:
        for s in _sentences(ln["text"]):
            for piece in _pieces(s, target):
                units.append((ln["speaker"], piece, ln["para"]))
    scenes, cur, words = [], [], 0
    last_para = units[0][2] if units else 0
    for speaker, sent, para in units:
        n = _word_count(sent)
        para_break = para != last_para
        if cur and (words + n > target * 1.35 or (para_break and words >= target * 0.6)):
            scenes.append(cur)
            cur, words = [], 0
        if cur and cur[-1]["speaker"] == speaker:
            cur[-1]["text"] += " " + sent
        else:
            cur.append({"speaker": speaker, "text": sent})
        words += n
        last_para = para
    if cur:
        if scenes and words < target * 0.35:  # tiny leftover: join the previous scene
            for ln in cur:
                if scenes[-1][-1]["speaker"] == ln["speaker"]:
                    scenes[-1][-1]["text"] += " " + ln["text"]
                else:
                    scenes[-1].append(ln)
        else:
            scenes.append(cur)
    out = []
    for k, lines in enumerate(scenes):
        out.append({"visual": block["visual"].strip(), "chapter": block["chapter"] if k == 0 else "",
                    "lines": lines, "part": k, "from_tag": block["from_tag"]})
    return out


MIN_SHOT_WORDS = 6  # a [SCENE] shorter than this (~2 s) joins the next one: shots last 4-8 s, no jumpy cuts


def to_scenes(parsed: dict, length: str = "short", merge_short: bool = True) -> list[dict]:
    """Blocks → scenes. Blocks without [SCENE] (or very long ones) are split automatically.
    merge_short: a tiny [SCENE] (one short sentence) joins the next one, so one shot covers both lines."""
    target = WORDS_PER_SCENE.get(length, 14)
    scenes = []
    blocks = [dict(b, lines=list(b["lines"])) for b in parsed["blocks"]]
    if merge_short:
        k = 1  # never the hook (block 0): a short question is a fine first shot
        while k < len(blocks) - 1:
            b, nxt = blocks[k], blocks[k + 1]
            words = sum(_word_count(ln["text"]) for ln in b["lines"])
            both = words + sum(_word_count(ln["text"]) for ln in nxt["lines"])
            if words < MIN_SHOT_WORDS and both <= target * 2.0 and not nxt.get("chapter") and b["from_tag"]:
                vis = " / ".join(x for x in (b["visual"].strip(), nxt["visual"].strip()) if x)
                blocks[k] = dict(b, visual=vis, lines=b["lines"] + nxt["lines"], from_tag=True)
                blocks.pop(k + 1)
                continue
            k += 1
    for b in blocks:
        words = sum(_word_count(ln["text"]) for ln in b["lines"])
        if b["from_tag"] and words <= target * 2.2:
            scenes.append({"visual": b["visual"].strip(), "chapter": b["chapter"], "part": 0, "from_tag": True,
                           "lines": [{"speaker": ln["speaker"], "text": ln["text"]} for ln in b["lines"]]})
        else:
            scenes.extend(split_block(b, target))
    return scenes


def narration_of(lines: list[dict]) -> str:
    return " ".join(ln["text"].strip() for ln in lines if ln.get("text", "").strip())


def length_warning(text: str, length: str, seconds: int | float = 0, video_format: str = "how_it_works") -> str:
    """'' if the script is long enough, else a friendly warning."""
    words = count_words(narration_of([ln for b in parse_lines(text)["blocks"] for ln in b["lines"]]))
    sec_said = words / (WORDS_PER_MINUTE / 60 * narrator_speed(video_format))
    need = target_words(length, seconds, video_format)
    if words >= need * 0.8:
        return ""
    want = target_seconds(length, seconds, video_format)
    kind = f"{'Short' if length == 'short' else 'Long video'} (~{want} s)" if want < 240 else f"Long video (~{want // 60} min)"
    seconds = sec_said
    return (f"Your script has {words} words, about {seconds:.0f} seconds of voice. A {kind} needs about {need} words. "
            "The video will be shorter, or add more story.")
