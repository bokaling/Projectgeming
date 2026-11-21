"""Word-by-word TikTok style captions as an ASS subtitle file (burned in by FFmpeg/libass).

Farsi rules from research.md section 8:
* logical-order Unicode (no arabic-reshaper for libass),
* each RTL line wrapped in U+202B … U+202C,
* Vazirmatn font, Spacing 0 (letter spacing breaks Persian),
* burned with the `ass` filter and `shaping=complex`.
"""

from __future__ import annotations

from pathlib import Path

from . import config

RLE, PDF = "‫", "‬"
ACCENTS = {"yellow": (255, 230, 0), "pink": (255, 46, 151), "green": (57, 255, 136), "cyan": (0, 229, 255),
           "purple": (176, 92, 255)}
STYLES = {"highlight": "Word highlight (TikTok)", "karaoke": "Karaoke fill", "plain": "Simple lines"}
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


def _t(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(words: list[dict], size: tuple[int, int], fmt: str, lang: str, style: str = "highlight",
              accent: str = "yellow", uppercase: bool = True, total: float | None = None) -> str:
    W, H = size
    rtl = is_rtl(lang)
    font = FONT_FA if rtl else FONT_EN
    bold = -1 if rtl else 0
    base = min(W, H)
    fontsize = int(base * (0.08 if fmt == "9x16" else 0.066) * (1.18 if rtl else 1.0))  # Persian glyphs look smaller
    margin_v = int(H * (0.30 if fmt == "9x16" else 0.09))
    outline = max(3, int(fontsize * 0.075))
    acc = ACCENTS.get(accent, ACCENTS["yellow"])
    header = [
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
        f"{int(W * 0.07)},{int(W * 0.07)},{margin_v},{-1 if rtl else 1}",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = []
    lines = group_lines([w for w in words if w.get("w")], fmt, lang)
    hl = ass_color(acc)
    for li, line in enumerate(lines):
        texts = [escape(w["w"].upper() if (uppercase and not rtl) else w["w"]) for w in line]
        start = line[0]["s"]
        nxt = lines[li + 1][0]["s"] if li + 1 < len(lines) else (total or line[-1]["e"] + 0.6)
        end = min(nxt, line[-1]["e"] + 0.5) if nxt - line[-1]["e"] > 0.6 else nxt
        end = max(end, line[-1]["e"])
        pop = r"{\fad(80,0)}"  # each new line fades in quickly
        if style == "plain":
            body = " ".join(texts)
            events.append((start, end, pop + _wrap(body, rtl)))
            continue
        if style == "karaoke" and not rtl:  # RTL karaoke sweeps look wrong in libass: use highlight instead
            parts = []
            for k, w in enumerate(line):
                dur = (line[k + 1]["s"] if k + 1 < len(line) else w["e"]) - w["s"]
                parts.append(f"{{\\kf{max(1, int(dur * 100))}}}{texts[k]}")
            lead = max(0, int((line[0]["s"] - start) * 100))
            events.append((start, end, pop + (f"{{\\k{lead}}}" if lead else "") + " ".join(parts)))
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
            events.append((ws, we, prefix + _wrap(" ".join(parts), rtl)))
    body = [f"Dialogue: 0,{_t(s)},{_t(e)},Main,,0,0,0,,{text}" for s, e, text in events]
    return "\n".join(header + body) + "\n"


def _wrap(text: str, rtl: bool) -> str:
    return f"{RLE}{text}{PDF}" if rtl else text


def write_ass(path: Path, words: list[dict], size, fmt, lang, style="highlight", accent="yellow", total=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(words, size, fmt, lang, style, accent, total=total), encoding="utf-8")
    return path


def ass_filter(ass_path: Path) -> str:
    """FFmpeg filter that burns the captions with full text shaping (needed for Farsi)."""

    def q(p: Path) -> str:
        return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    return f"ass=filename='{q(ass_path)}':fontsdir='{q(config.FONTS_DIR)}':shaping=complex"
