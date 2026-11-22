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
* Optional: [CHARACTER] NIKOLA: man, 40s, short dark hair, lab coat
  (this look goes into every picture where he appears).
* Optional: [STYLE] night, rain, dark lab, green radio glow, horror thriller
  (the "mood lock": added to every picture so time of day, light and colors stay the same).
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
NARRATOR_SPEED = 1.1  # the narrator talks a little faster (more energy)
WORDS_PER_SECOND = 2.5 * NARRATOR_SPEED
WORDS_PER_SCENE = {"short": 14, "long": 28}  # a scene = whole sentences, so the voice sounds natural
# One picture per ~5 s (short) / ~10 s (long): about 12 pictures for a Short. The fast cuts in between
# (every 1.5-2.5 s / 3-5 s) are zooms and crops into different parts of the same picture.
SECONDS_PER_IMAGE = {"short": 5.0, "long": 10.0}
WORDS_PER_IMAGE = {k: round(v * WORDS_PER_SECOND) for k, v in SECONDS_PER_IMAGE.items()}
WORDS_PER_SHOT = WORDS_PER_IMAGE  # old name
CUT_SECONDS = {"short": (1.5, 2.5), "long": (3.0, 5.0)}  # a new shot (cut) this often
TARGET_SECONDS = {"short": 60, "long": 600}
TARGET_WORDS = {"short": 150, "long": 1500}  # at 1.1x speed, with short pauses and the cold open


def split_scripts(text: str) -> list[str]:
    """Batch mode: one script per block between ===== lines."""
    return [p.strip() for p in SEPARATOR.split(text or "") if p.strip()]


def detect_language(text: str) -> str:
    return "fa" if len(PERSIAN.findall(text or "")) > len(LATIN.findall(text or "")) else "en"


def _speaker(name: str, known: set[str]) -> str | None:
    """Is 'name' (text before a colon) a speaker? Returns the speaker name or None."""
    n = name.strip().strip("*").strip()
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

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            para += 1
            continue
        m = TAG.match(line)
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
        speaker, content = NARRATOR, line
        sm = SPEAKER.match(line)
        if sm:
            who = _speaker(sm.group(1), known)
            if who:
                speaker, content = who, sm.group(2).strip()
                if who != NARRATOR:
                    known.add(who)
        content = content.strip().strip('"“”').strip()
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
    return len(text.split())


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


def to_scenes(parsed: dict, length: str = "short") -> list[dict]:
    """Blocks → scenes. Blocks without [SCENE] (or very long ones) are split automatically."""
    target = WORDS_PER_SCENE.get(length, 14)
    scenes = []
    for b in parsed["blocks"]:
        words = sum(_word_count(ln["text"]) for ln in b["lines"])
        if b["from_tag"] and words <= target * 2.2:
            scenes.append({"visual": b["visual"].strip(), "chapter": b["chapter"], "part": 0, "from_tag": True,
                           "lines": [{"speaker": ln["speaker"], "text": ln["text"]} for ln in b["lines"]]})
        else:
            scenes.extend(split_block(b, target))
    return scenes


def narration_of(lines: list[dict]) -> str:
    return " ".join(ln["text"].strip() for ln in lines if ln.get("text", "").strip())


def length_warning(text: str, length: str) -> str:
    """'' if the script is long enough, else a friendly warning."""
    words = len(narration_of([ln for b in parse_lines(text)["blocks"] for ln in b["lines"]]).split())
    seconds = words / WORDS_PER_SECOND
    need = TARGET_WORDS.get(length, 150)
    if words >= need * 0.8:
        return ""
    kind = "Short (~60 s)" if length == "short" else "Long video (~10 min)"
    return (f"Your script has {words} words, about {seconds:.0f} seconds of voice. A {kind} needs about {need} words. "
            "The video will be shorter, or add more story.")
