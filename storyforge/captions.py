"""Word-by-word TikTok style captions as an ASS subtitle file (burned in by FFmpeg/libass).

Farsi rules from research.md section 8:
* logical-order Unicode (no arabic-reshaper for libass),
* each RTL line wrapped in U+202B … U+202C,
* Vazirmatn font, Spacing 0 (letter spacing breaks Persian),
* burned with the `ass` filter and `shaping=complex`.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config

RLE, PDF = "‫", "‬"
ACCENTS = {"yellow": (255, 230, 0), "pink": (255, 46, 151), "green": (57, 255, 136), "cyan": (0, 229, 255),
           "purple": (176, 92, 255)}
STYLES = {"pop": "Big pop words (1-3 at a time, key word highlighted)", "highlight": "Word highlight (TikTok)",
          "karaoke": "Karaoke fill", "plain": "Simple lines"}
HOOK_SECONDS = 3.0  # on-screen hook text at the top
FONT_EN = "Montserrat ExtraBold"
FONT_FA = "Vazirmatn"


def ass_color(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def is_rtl(lang: str) -> bool:
    return lang == "fa"


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_lines(words: list[dict], fmt: str, lang: str) -> list[list[dict]]:
    """Split words into short caption lines (2-4 words on 9:16, up to 6 on 16:9)."""
    max_words = 3 if fmt == "9x16" else 6
    max_chars = 18 if fmt == "9x16" else 34
    if is_rtl(lang):
        max_chars += 4
    lines, cur = [], []
    for i, w in enumerate(words):
        text = w["w"]
        if cur:
            length = sum(len(x["w"]) + 1 for x in cur) + len(text)
            gap = w["s"] - cur[-1]["e"]
            if len(cur) >= max_words or length > max_chars or gap > 0.6:
                lines.append(cur)
                cur = []
        cur.append(w)
        if text[-1:] in ".!?؟…" and len(cur) >= 1:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    # don't leave one word alone: join it to the line before if it still fits
    merged: list[list[dict]] = []
    for line in lines:
        if (merged and len(line) == 1 and len(merged[-1]) <= max_words
                and merged[-1][-1]["w"][-1:] not in ".!?؟…"
                and sum(len(x["w"]) + 1 for x in merged[-1]) + len(line[0]["w"]) <= max_chars + 6
                and line[0]["s"] - merged[-1][-1]["e"] < 0.6):
            merged[-1] = merged[-1] + line
        else:
            merged.append(line)
    return merged


def group_pop(words: list[dict], fmt: str, lang: str) -> list[list[dict]]:
    """Big captions: 1-3 words at a time (a new group at sentence ends and pauses)."""
    max_chars = (13 if fmt == "9x16" else 20) + (3 if is_rtl(lang) else 0)
    groups, cur = [], []
    for w in words:
        if cur:
            length = sum(len(x["w"]) + 1 for x in cur) + len(w["w"])
            if len(cur) >= 3 or length > max_chars or w["s"] - cur[-1]["e"] > 0.35:
                groups.append(cur)
                cur = []
        cur.append(w)
        if w["w"][-1:] in ".!?؟…,،;":
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _t(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def header(size: tuple[int, int], fmt: str, lang: str, style: str = "highlight", accent: str = "yellow") -> list[str]:
    """ASS header: Main (captions) and Hook (the text at the top in the first 3 s) styles."""
    W, H = size
    rtl = is_rtl(lang)
    font = FONT_FA if rtl else FONT_EN
    bold = -1 if rtl else 0
    base = min(W, H)
    big = style == "pop"
    size_k = (0.096 if fmt == "9x16" else 0.085) if big else (0.08 if fmt == "9x16" else 0.066)
    fontsize = int(base * size_k * (1.12 if rtl else 1.0))  # Persian glyphs look smaller
    margin_v = int(H * (0.30 if fmt == "9x16" else 0.09))
    outline = max(3, int(fontsize * (0.09 if big else 0.075)))
    acc = ACCENTS.get(accent, ACCENTS["yellow"])
    hook_size = int(base * (0.07 if fmt == "9x16" else 0.056) * (1.1 if rtl else 1.0))
    enc = -1 if rtl else 1
    return [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        # Spacing must stay 0 (non-zero letter spacing reverses Persian letters in libass)
        f"Style: Main,{font},{fontsize},{ass_color((255, 255, 255))},{ass_color(acc)},{ass_color((0, 0, 0))},"
        f"{ass_color((0, 0, 0), 0x80)},{bold},0,0,0,100,100,0,0,1,{outline},{max(1, outline // 2)},2,"
        # Encoding -1 = libass detects the base direction; without it Farsi word order comes out mirrored
        f"{int(W * 0.07)},{int(W * 0.07)},{margin_v},{enc}",
        # Hook: black text on a white box at the top (BorderStyle 3 = box in the outline colour)
        f"Style: Hook,{font},{hook_size},{ass_color((10, 10, 14))},{ass_color((10, 10, 14))},{ass_color((255, 255, 255))},"
        f"{ass_color((0, 0, 0), 0xFF)},-1,0,0,0,100,100,0,0,3,{max(8, hook_size // 4)},0,8,"
        f"{int(W * 0.08)},{int(W * 0.08)},{int(H * (0.11 if fmt == '9x16' else 0.07))},{enc}",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def hook_event(text: str, lang: str, seconds: float = HOOK_SECONDS) -> tuple[float, float, str, str]:
    """The on-screen hook text (top of the screen, first 3 s), popping in."""
    rtl = is_rtl(lang)
    t = escape(text.strip().upper() if not rtl else text.strip())
    pop = r"{\fscx70\fscy70\t(0,120,\fscx104\fscy104)\t(120,200,\fscx100\fscy100)\fad(0,150)}"
    return (0.0, seconds, "Hook", pop + _wrap(t, rtl))


def caption_events(words: list[dict], size: tuple[int, int], fmt: str, lang: str, style: str = "highlight",
                   accent: str = "yellow", uppercase: bool = True, total: float | None = None) -> list[tuple]:
    """Caption events: (start, end, style name, text)."""
    rtl = is_rtl(lang)
    acc = ACCENTS.get(accent, ACCENTS["yellow"])
    hl = ass_color(acc)
    words = [w for w in words if w.get("w")]
    events = []
    if style == "pop":
        from .beats import is_key, key_word_index  # noqa: PLC0415

        groups = group_pop(words, fmt, lang)
        for gi, g in enumerate(groups):
            start = g[0]["s"]
            nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else (total or g[-1]["e"] + 0.5)
            end = max(g[-1]["e"], min(nxt, g[-1]["e"] + 0.35))
            texts = [escape(w["w"].upper() if (uppercase and not rtl) else w["w"]) for w in g]
            key = key_word_index([w["w"] for w in g]) if len(g) > 1 else (0 if is_key(g[0]["w"]) else -1)
            parts = [f"{{\\c{hl}}}{tx}{{\\c&H00FFFFFF&}}" if j == key else tx for j, tx in enumerate(texts)]
            pop = r"{\fscx78\fscy78\t(0,90,\fscx106\fscy106)\t(90,160,\fscx100\fscy100)}"
            events.append((start, end, "Main", pop + _wrap(" ".join(parts), rtl)))
        return events
    lines = group_lines(words, fmt, lang)
    for li, line in enumerate(lines):
        texts = [escape(w["w"].upper() if (uppercase and not rtl) else w["w"]) for w in line]
        start = line[0]["s"]
        nxt = lines[li + 1][0]["s"] if li + 1 < len(lines) else (total or line[-1]["e"] + 0.6)
        end = min(nxt, line[-1]["e"] + 0.5) if nxt - line[-1]["e"] > 0.6 else nxt
        end = max(end, line[-1]["e"])
        pop = r"{\fad(80,0)}"  # each new line fades in quickly
        if style == "plain":
            body = " ".join(texts)
            events.append((start, end, "Main", pop + _wrap(body, rtl)))
            continue
        if style == "karaoke" and not rtl:  # RTL karaoke sweeps look wrong in libass: use highlight instead
            parts = []
            for k, w in enumerate(line):
                dur = (line[k + 1]["s"] if k + 1 < len(line) else w["e"]) - w["s"]
                parts.append(f"{{\\kf{max(1, int(dur * 100))}}}{texts[k]}")
            lead = max(0, int((line[0]["s"] - start) * 100))
            events.append((start, end, "Main", pop + (f"{{\\k{lead}}}" if lead else "") + " ".join(parts)))
            continue
        for k, w in enumerate(line):
            ws = start if k == 0 else w["s"]
            we = line[k + 1]["s"] if k + 1 < len(line) else end
            if we <= ws:
                continue
            parts = []
            for j, tx in enumerate(texts):
                if j == k:
                    parts.append(f"{{\\c{hl}\\fscx112\\fscy112}}{tx}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
                else:
                    parts.append(tx)
            prefix = pop if k == 0 else ""
            events.append((ws, we, "Main", prefix + _wrap(" ".join(parts), rtl)))
    return events


def to_text(head: list[str], events: list[tuple]) -> str:
    body = [f"Dialogue: {1 if st == 'Hook' else 0},{_t(s)},{_t(e)},{st},,0,0,0,,{text}" for s, e, st, text in events]
    return "\n".join(head + body) + "\n"


def build_ass(words: list[dict], size: tuple[int, int], fmt: str, lang: str, style: str = "highlight",
              accent: str = "yellow", uppercase: bool = True, total: float | None = None, hook: str = "") -> str:
    events = caption_events(words, size, fmt, lang, style, accent, uppercase, total)
    if hook:
        events = [hook_event(hook, lang)] + events
    return to_text(header(size, fmt, lang, style, accent), events)


def slice_events(events: list[tuple], t0: float, t1: float) -> list[tuple]:
    """The events seen between t0 and t1, with times starting at 0 (captions of one scene clip)."""
    out = []
    for s, e, st, text in events:
        if e <= t0 + 1e-3 or s >= t1 - 1e-3:
            continue
        if s < t0 - 0.05:  # started in the scene before: no second pop animation
            text = re.sub(r"\\t\([^)]*\)|\\fscx\d+|\\fscy\d+|\\fad\(\d+,\d+\)", "", text).replace("{}", "")
        out.append((round(max(0.0, s - t0), 3), round(min(t1, e) - t0, 3), st, text))
    return out


def _wrap(text: str, rtl: bool) -> str:
    return f"{RLE}{text}{PDF}" if rtl else text


def write_ass(path: Path, words: list[dict], size, fmt, lang, style="highlight", accent="yellow", total=None,
              hook: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(words, size, fmt, lang, style, accent, total=total, hook=hook), encoding="utf-8")
    return path


def ass_filter(ass_path: Path) -> str:
    """FFmpeg filter that burns the captions with full text shaping (needed for Farsi)."""

    def q(p: Path) -> str:
        return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    return f"ass=filename='{q(ass_path)}':fontsdir='{q(config.FONTS_DIR)}':shaping=complex"


# ---------------------------------------------------------------------------
# 3D explainer: small keyword captions at the top, colored by meaning
# ---------------------------------------------------------------------------

KEY_COLORS = {"problem": (255, 92, 92), "part": (255, 170, 60), "number": (255, 255, 255), "info": (120, 235, 225)}


def keyword_header(size: tuple[int, int], fmt: str, lang: str) -> list[str]:
    """ASS styles for the top keywords (one style per meaning)."""
    W, H = size
    rtl = is_rtl(lang)
    font = FONT_FA if rtl else FONT_EN
    fs = int(min(W, H) * (0.088 if fmt == "9x16" else 0.062) * (1.1 if rtl else 1.0))  # big and bold on a phone
    outline = max(5, fs // 8)
    margin = int(H * (0.055 if fmt == "9x16" else 0.045))  # inside the top 15 % (the safe area for captions)
    enc = -1 if rtl else 1
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
             "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
             "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
             "MarginR, MarginV, Encoding"]
    for kind, rgb in KEY_COLORS.items():
        # Spacing must stay 0 (non-zero letter spacing reverses Persian letters in libass)
        lines.append(f"Style: Key_{kind},{font},{fs},{ass_color(rgb)},{ass_color(rgb)},{ass_color((6, 20, 24))},"
                     f"{ass_color((0, 0, 0), 0x90)},{-1 if rtl else 0},0,0,0,100,100,0,0,1,{outline},{max(1, outline // 2)},"
                     f"8,{int(W * 0.08)},{int(W * 0.08)},{margin},{enc}")
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    return lines


def keyword_events(items: list[dict], lang: str, total: float) -> list[tuple]:
    """items: [{"text", "kind", "start", "end"}] (seconds) → events (start, end, style, text). One at a time."""
    rtl = is_rtl(lang)
    items = sorted(items, key=lambda x: x["start"])
    events = []
    for k, it in enumerate(items):
        end = min(it["end"], items[k + 1]["start"]) if k + 1 < len(items) else min(it["end"], total)
        if end - it["start"] < 0.15:
            continue
        text = escape(it["text"].upper() if not rtl else it["text"])
        pop = r"{\blur1.5\fscx70\fscy70\t(0,110,\fscx106\fscy106)\t(110,180,\fscx100\fscy100)}"  # never faded
        style = f"Key_{it.get('kind') if it.get('kind') in KEY_COLORS else 'info'}"
        events.append((round(it["start"], 3), round(end, 3), style, pop + _wrap(text, rtl)))
    return events
