"""🩺 Script doctor: scores your script for retention and can rewrite it (you choose which one to use).

Scores (0-10 each, never changes your script by itself):
  🪝 hook in the first 2 seconds · ⚠️ stakes · ⚡ something new every 5 seconds ·
  ❓ curiosity gaps · 🎁 payoff (a twist every ~15 s) · 🧗 cliffhanger.
Weak lines are listed with the reason and what to do.

✨ Improve: the free AI chain rewrites the wording for retention and keeps your format
([TITLE], [CHARACTER], [STYLE], [SCENE] lines and speaker names). Without any AI it does a
light polish (slow intro moved, long sentences split, filler words removed).
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

from . import beats, llm, paste

CATEGORIES = [
    ("hook", "🪝 Hook in the first 2 s"), ("stakes", "⚠️ Stakes"), ("novelty", "⚡ Something new every 5 s"),
    ("curiosity", "❓ Curiosity gaps"), ("payoff", "🎁 Payoff and twists"), ("cliffhanger", "🧗 Cliffhanger"),
]
KEEP_TAGS = ("TITLE", "CHARACTER", "STYLE")


@dataclass
class Line:
    no: int  # line number in your script (1 = first line)
    speaker: str
    text: str
    raw: str


@dataclass
class Report:
    scores: dict = field(default_factory=dict)
    total: int = 0
    weak: list = field(default_factory=list)  # {"no", "text", "why"}
    tips: list = field(default_factory=list)
    words: int = 0
    seconds: float = 0.0
    style_line: str = ""  # the mood lock that will be used ([STYLE] or made from the script)
    has_style: bool = False
    lines: int = 0  # spoken lines
    speakers: list = field(default_factory=list)


def spoken_lines(text: str) -> list[Line]:
    """The lines that are spoken (not [TAG] lines), with their line numbers."""
    known: set[str] = set(paste.frequent_labels(text))
    out = []
    title_seen = False
    for no, raw in enumerate((text or "").replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or re.fullmatch(r"={5,}", line):
            continue
        if line.startswith("#") and not title_seen:
            title_seen = True
            continue
        line = re.sub(r"^[-•>]\s+", "", line)
        m = paste.TAG.match(line)
        if m:
            kind = m.group(1).upper()
            if kind == "TITLE":
                title_seen = True
            if kind == "CHARACTER":
                name = m.group(2).partition(":")[0].strip()
                if name:
                    known.add(name.upper() if paste.LATIN.search(name) else name)
            if kind != "SCENE":
                continue
            inline = re.search(r"\s((?:NARRATOR|Narrator|[A-Z][A-Z.'\-]{1,20}(?: [A-Z][A-Z.'\-]{1,20})?)\s*:\s*\S.*)$",
                               m.group(2))
            if not (inline and paste._speaker(inline.group(1).split(":")[0], known)):
                continue
            line = inline.group(1).strip()
        speaker, content = paste.split_label(line, known)
        if any(ch.isalnum() for ch in content):
            out.append(Line(no, speaker, content, raw))
    return out


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?؟…])\s+", text.strip()) if s.strip()]


def score(text: str, length: str = "short") -> Report:
    """Score a script. Instant and offline."""
    first = (paste.split_scripts(text) or [""])[0]
    lines = spoken_lines(first)
    rep = Report()
    parsed = paste.parse_lines(first)
    all_text = " ".join(ln.text for ln in lines)
    rep.words = paste.count_words(all_text)
    rep.lines = len(lines)
    rep.speakers = sorted({ln.speaker for ln in lines}, key=lambda x: (x != paste.NARRATOR, x))
    rep.seconds = round(rep.words / paste.WORDS_PER_SECOND, 1)
    rep.has_style = bool(parsed.get("style"))
    from .beats import guess_mood  # noqa: PLC0415

    rep.style_line = parsed.get("style") or beats.auto_mood_lock(
        all_text + " " + " ".join(b["visual"] for b in parsed["blocks"]), guess_mood(all_text))
    if not lines:
        rep.scores = {k: 0 for k, _ in CATEGORIES}
        rep.tips.append("Paste a script to get a score.")
        return rep
    weak: dict[int, list[str]] = {}

    def flag(ln: Line, why: str) -> None:
        weak.setdefault(ln.no, [])
        if why not in weak[ln.no]:
            weak[ln.no].append(why)

    # 🪝 hook: the first sentence (about 2 seconds)
    hook_line = lines[0]
    hook = _sentences(hook_line.text)[0] if _sentences(hook_line.text) else hook_line.text
    n = len(hook.split())
    h = 10.0
    if beats.SLOW_INTRO.match(hook):
        h -= 5
        flag(hook_line, "Slow intro. Start with the shocking part (a statement or question, max 10 words).")
    if n > 10:
        h -= 3 if n <= 15 else 4
        flag(hook_line, f"The first sentence has {n} words. Keep it under 10 so it lands in 2 seconds.")
    punchy = beats.has_any(hook, beats.SHOCK + beats.STAKES + ["?"]) or re.search(r"\d", hook)
    if not punchy:
        h -= 3
        flag(hook_line, "The hook has no shock: add danger, a mystery, a number or a question.")
    rep.scores["hook"] = int(max(0, min(10, round(h))))

    # ⚠️ stakes
    per100 = 100 / max(rep.words, 1)
    stakes = beats.count_any(all_text, beats.STAKES)
    early = beats.count_any(" ".join(ln.text for ln in lines[: max(1, len(lines) // 3)]), beats.STAKES)
    rep.scores["stakes"] = int(min(10, round(stakes * per100 * 2.2 + (2 if early else 0))))
    if not stakes:
        rep.tips.append("⚠️ No stakes yet: say early what the hero can lose (a life, a family member, freedom, time).")

    # ⚡ something new every ~5 seconds (≈14 words)
    window = round(5 * paste.WORDS_PER_SECOND)
    seen: set[str] = set()
    good = total = 0
    words_by_line = [(ln, [beats.norm(w) for w in paste.WORD_SPLIT.split(ln.text) if beats.norm(w)]) for ln in lines]
    flat = [(ln, w) for ln, ws in words_by_line for w in ws]
    for k in range(0, len(flat), window):
        chunk = flat[k:k + window]
        if len(chunk) < window * 0.5 and total:
            break
        new = {w for _, w in chunk if len(w) >= 4 and w not in beats.STOP and w not in seen}
        seen |= {w for _, w in chunk}
        total += 1
        if len(new) >= 3:
            good += 1
        else:
            flag(chunk[0][0], "Nothing new for about 5 seconds: add a new detail, action or question.")
    nov = 10.0 * good / max(total, 1)
    for ln in lines:
        for s in _sentences(ln.text):
            if len(s.split()) > 20:
                nov -= 1
                flag(ln, f"A {len(s.split())}-word sentence. Split it into short, punchy sentences.")
        vague = beats.has_any(ln.text, beats.VAGUE)
        if vague:
            nov -= 0.5
            flag(ln, f"Vague word(s): {', '.join(vague[:3])}. Use a specific detail instead.")
    rep.scores["novelty"] = int(max(0, min(10, round(nov))))

    # ❓ curiosity gaps
    cur = beats.count_any(all_text, beats.CURIOSITY)
    rep.scores["curiosity"] = int(min(10, round(cur * per100 * 1.6)))
    if cur == 0:
        rep.tips.append("❓ Open a question early (who? why? what is behind the door?) and answer it late.")

    # 🎁 payoff: a twist or reveal about every 15 seconds, and a real reveal in the second half
    twists = beats.count_any(all_text, beats.TWIST) + beats.count_any(all_text, beats.REVEAL) // 2
    expected = max(1.0, rep.seconds / 15)
    pay = 10 * min(1.0, twists / expected)
    second_half = " ".join(ln.text for ln in lines[len(lines) // 2:])
    if not beats.has_any(second_half, beats.REVEAL):
        pay -= 3
        rep.tips.append("🎁 Add a reveal in the second half (\"that's when she realized…\", \"it was never…\").")
    rep.scores["payoff"] = int(max(0, min(10, round(pay))))

    # 🧗 cliffhanger: the last line
    last = lines[-1]
    if beats.RESOLVED_END.search(last.text):
        c = 2
        flag(last, "The ending is closed. End on a question, a threat or a reveal for the next episode.")
    elif last.text.rstrip().endswith(("?", "؟", "…", "...")) or beats.has_any(last.text, beats.SHOCK + beats.SCARY
                                                                                + beats.REVEAL):
        c = 10 if len(last.text.split()) <= 14 else 8
    else:
        c = 5
        flag(last, "The last line doesn't pull into the next episode. End on an open question or a new threat.")
    rep.scores["cliffhanger"] = c

    rep.total = int(round(sum(rep.scores.values()) / (10 * len(CATEGORIES)) * 100))
    by_no = {ln.no: ln for ln in lines}
    rep.weak = [{"no": no, "text": by_no[no].text, "why": why} for no, why in sorted(weak.items())]
    target = paste.TARGET_WORDS.get(length, 150)
    if rep.words < target * 0.8:
        rep.tips.append(f"📏 {rep.words} words (~{rep.seconds:.0f} s). Aim for about {target} words.")
    elif rep.words > target * 1.3:
        rep.tips.append(f"📏 {rep.words} words (~{rep.seconds:.0f} s). Aim for about {target}: cut slow parts.")
    return rep


def _bar(v: int) -> str:
    color = "#39ff88" if v >= 8 else ("#ffd23f" if v >= 5 else "#ff4f7b")
    return (f'<div style="background:#ffffff14;border-radius:6px;height:8px;overflow:hidden">'
            f'<div style="width:{v * 10}%;height:8px;background:{color}"></div></div>')


def report_html(r: Report, title: str = "🩺 Script doctor") -> str:
    """The score card shown in the app."""
    if not r.words:
        return '<div class="sf-note">🩺 Paste a script to see its retention score.</div>'
    color = "#39ff88" if r.total >= 75 else ("#ffd23f" if r.total >= 50 else "#ff4f7b")
    rows = "".join(
        f'<div style="display:grid;grid-template-columns:minmax(150px,1.4fr) 1fr 28px;gap:8px;align-items:center;'
        f'margin:3px 0">'
        f'<span>{label}</span>{_bar(r.scores.get(key, 0))}<b style="text-align:right">{r.scores.get(key, 0)}</b></div>'
        for key, label in CATEGORIES)
    weak = "".join(
        f'<li><b>Line {w["no"]}</b>: <mark style="background:#ff2e9733;color:inherit;border-radius:4px;padding:0 3px">'
        f'{html.escape(w["text"][:140])}</mark><br><span style="opacity:.85">→ {html.escape(" ".join(w["why"]))}</span></li>'
        for w in r.weak[:12])
    tips = "".join(f"<li>{html.escape(t)}</li>" for t in r.tips)
    style = (f'<div style="margin-top:8px">🎨 <b>Mood lock</b> ({"your [STYLE] line" if r.has_style else "made from your script"}): '
             f'<code>{html.escape(r.style_line)}</code></div>')
    return (f'<div class="sf-doctor"><div style="display:flex;justify-content:space-between;align-items:baseline">'
            f'<b>{title}</b><span style="font-size:28px;font-weight:800;color:{color}">{r.total}<small>/100</small></span>'
            f'</div><div style="opacity:.75;margin-bottom:6px">{r.words} spoken words in {r.lines} lines '
            f'({html.escape(", ".join(r.speakers))}) · about {r.seconds:.0f} s of voice · speaker names like '
            f'NARRATOR: are not counted</div>'
            f'{rows}{style}'
            + (f'<div style="margin-top:8px"><b>Weak lines</b><ul style="margin:4px 0 0 18px">{weak}</ul></div>' if weak else
               '<div style="margin-top:8px">✅ No weak lines found.</div>')
            + (f'<div style="margin-top:6px"><b>Tips</b><ul style="margin:4px 0 0 18px">{tips}</ul></div>' if tips else "")
            + "</div>")


# ---------------------------------------------------------------------------
# ✨ Improve
# ---------------------------------------------------------------------------

IMPROVE_SYSTEM = """You are a top viral short-form story editor (MrBallen, Zack D. Films style). You rewrite scripts for retention.
Rules:
- The first spoken line is a shocking statement or question, max 10 words. No slow intros ("At 3am", "Once upon a time", "One day", "This is the story of").
- Short, punchy sentences that sound natural out loud.
- A twist or reveal about every 15 seconds of voice (about every 40 words).
- Specific details instead of vague ones (names, numbers, objects, sounds) - never "something strange" or "very scary".
- End on a cliffhanger for the next episode (an open question, a new threat or a reveal).
- Loop the last line back to the first line only if it fits the story naturally.
- Keep the story, the characters and the names. Improve the wording; change events only if it makes the story stronger.
FORMAT (very important):
- Keep EVERY [TITLE], [CHARACTER] and [STYLE] line exactly as it is.
- Keep the [SCENE] lines; update a [SCENE] line only if the story in that part changed.
- Every spoken line starts with a speaker name and a colon (NARRATOR: or a character name). Use only the speaker names from the original.
- Same language as the original.
Reply with JSON only: {"script": "the full script, one line per line, with \\n between lines", "changes": ["short note", "..."]}"""


def _tag_lines(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw in (text or "").split("\n"):
        m = paste.TAG.match(raw.strip())
        if m:
            out.setdefault(m.group(1).upper(), []).append(raw.strip())
    return out


def keep_format(original: str, new: str) -> str:
    """Put back your [TITLE], [CHARACTER] and [STYLE] lines exactly, and fix speaker names to your spelling."""
    orig_tags = _tag_lines(original)
    speakers = {sp.upper(): sp for sp in paste.parse_lines(original)["speakers"]}
    narrator = "NARRATOR"  # your narrator label (NARRATOR, Narrator, راوی…)
    for raw in (original or "").split("\n"):
        sm = paste.SPEAKER.match(raw.strip())
        if sm and paste._speaker(sm.group(1), set()) == paste.NARRATOR:
            narrator = sm.group(1).strip()
            break
    body = []
    for raw in (new or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        m = paste.TAG.match(line.strip())
        if m and m.group(1).upper() in KEEP_TAGS:
            continue
        sm = paste.SPEAKER.match(line)
        if sm and sm.group(1).strip().upper() in speakers:
            line = f"{speakers[sm.group(1).strip().upper()]}: {sm.group(2).strip()}"
        elif sm and paste._speaker(sm.group(1), set()) == paste.NARRATOR:
            line = f"{narrator}: {sm.group(2).strip()}"
        body.append(line)
    head = orig_tags.get("TITLE", [])[:1] + orig_tags.get("CHARACTER", []) + orig_tags.get("STYLE", [])
    while body and not body[0].strip():
        body.pop(0)
    text = "\n".join(head + body).strip()
    return re.sub(r"\n{3,}", "\n\n", text) + "\n"


def check_rewrite(original: str, new: str, length: str) -> None:
    """Raise ValueError (the AI then gets one chance to fix it) if the rewrite broke the format."""
    p_old, p_new = paste.parse_lines(original), paste.parse_lines(new)
    if sum(len(b["lines"]) for b in p_new["blocks"]) < 2:
        raise ValueError("the script has no spoken lines")
    allowed = {s.upper() for s in p_old["speakers"]} | {paste.NARRATOR}
    bad = [s for s in p_new["speakers"] if s.upper() not in allowed]
    if bad:
        raise ValueError(f"unknown speaker(s) {', '.join(bad)}: only use NARRATOR and {', '.join(p_old['speakers']) or 'no one else'}")
    n_old = sum(1 for b in p_old["blocks"] if b["from_tag"])
    n_new = sum(1 for b in p_new["blocks"] if b["from_tag"])
    if n_old and n_new < max(1, int(n_old * 0.6)):
        raise ValueError(f"keep the [SCENE] lines (the original has {n_old}, yours has {n_new})")
    if p_new["language"] != p_old["language"]:
        raise ValueError("write in the same language as the original")
    words = len(" ".join(ln["text"] for b in p_new["blocks"] for ln in b["lines"]).split())
    old_words = len(" ".join(ln["text"] for b in p_old["blocks"] for ln in b["lines"]).split())
    target = paste.TARGET_WORDS.get(length, 150)
    if words < min(target * 0.5, old_words * 0.75) or words > max(target * 2, old_words * 1.3):
        raise ValueError(f"the script has {words} words; it must be about {target} words")


def improve(text: str, length: str = "short", rep=None) -> dict:
    """Rewrite for retention. Returns {"script", "changes", "provider", "ai"}. Never changes your text in place."""
    original = (paste.split_scripts(text) or [""])[0]
    if not original.strip():
        raise ValueError("empty script")
    target = paste.TARGET_WORDS.get(length, 150)
    payload = {
        "length": "YouTube Short / TikTok, about 60 seconds" if length == "short" else
                  "long YouTube video, about 10 minutes, with a mini cliffhanger every 2 minutes (about every 300 words)",
        "target_words": target,
        "speakers_allowed": ["NARRATOR"] + paste.parse_lines(original)["speakers"],
        "original_script": original,
    }

    def validate(obj):
        if not isinstance(obj, dict) or not str(obj.get("script", "")).strip():
            raise ValueError("need a 'script' text")
        check_rewrite(original, keep_format(original, str(obj["script"])), length)

    try:
        provider, obj = llm.generate_json(IMPROVE_SYSTEM, json.dumps(payload, ensure_ascii=False), validate=validate,
                                          rep=rep, task="script doctor", temperature=0.8, max_tokens=6000,
                                          strong=True)
        new = keep_format(original, str(obj["script"]))
        changes = [str(c) for c in (obj.get("changes") or []) if str(c).strip()][:8]
        return {"script": new, "changes": changes, "provider": provider, "ai": True}
    except Exception as exc:  # noqa: BLE001 - every AI busy: light polish, never a dead end
        from .messages import StopRequested  # noqa: PLC0415

        if isinstance(exc, StopRequested):
            raise
        return {"script": light_polish(original), "provider": "Built-in (no AI)", "ai": False,
                "changes": ["The AI writers are busy right now, so this is only a light polish: slow intro moved, "
                            "long sentences split, filler words removed. Try ✨ Improve again later for a full rewrite."]}


FILLER = re.compile(r"\b(basically|actually|literally|really|very|just|kind of|sort of|pretty much)\s+", re.I)
INTRO = re.compile(r"^((?:at|on|in|one|once|long|years|it was)\b[^,]{2,60}),\s*(.+)$", re.I)


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def light_polish(text: str) -> str:
    """No AI: small safe edits only (your story stays the same)."""
    out, first_done = [], False
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        m = paste.TAG.match(line.strip())
        if not line.strip() or m:
            out.append(line)
            continue
        sm = paste.SPEAKER.match(line)
        prefix, content = (f"{sm.group(1).strip()}: ", sm.group(2).strip()) if sm else ("", line.strip())
        content = FILLER.sub("", content)
        if not first_done:
            first_done = True
            sents = _sentences(content)
            if sents:
                mi = INTRO.match(sents[0])
                if mi and beats.SLOW_INTRO.match(sents[0]):  # "At 3am, the radio spoke." → "The radio spoke. At 3am."
                    sents[0] = f"{_cap(mi.group(2).rstrip('.'))}. {_cap(mi.group(1))}."
                content = " ".join(sents)
        fixed = []
        for s in _sentences(content):
            if len(s.split()) > 18:
                s = re.sub(r",\s+(and|but|so|then)\s+", lambda m_: f". {_cap(m_.group(1))} ", s, count=1)
            fixed.append(s)
        out.append(prefix + " ".join(fixed))
    return "\n".join(out).strip() + "\n"


def compare_html(old: Report, new: Report) -> str:
    """Score before → after, per category."""
    rows = "".join(
        f'<tr><td>{label}</td><td style="text-align:center">{old.scores.get(k, 0)}</td>'
        f'<td style="text-align:center"><b>{new.scores.get(k, 0)}</b></td></tr>' for k, label in CATEGORIES)
    return (f'<div class="sf-doctor"><table style="width:100%"><tr><th></th><th>Yours</th><th>Improved</th></tr>{rows}'
            f'<tr><td><b>Total</b></td><td style="text-align:center">{old.total}</td>'
            f'<td style="text-align:center"><b>{new.total}</b></td></tr></table></div>')
