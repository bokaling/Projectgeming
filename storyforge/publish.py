"""Thumbnail, titles, description, hashtags, credits, and platform checklist."""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from . import config, llm
from .project import Episode, Series, write_json

PLATFORM_CHECKLIST = [
    ("YouTube / Shorts", "Turn on 'Altered or synthetic content' if the video looks realistic. Keep your own voice/writing visible: "
     "templated mass uploads are not monetizable since July 2026."),
    ("TikTok", "Switch on the 'AI-generated content' label. Creator Rewards needs videos over 1 minute (and isn't in every country)."),
    ("Instagram / Facebook Reels", "Add the 'AI info' label for realistic AI pictures. Post original content, not reposts."),
    ("Snapchat Spotlight", "Since July 2026 wholly AI-generated videos are not recommended on Spotlight. "
     "Add real footage (e.g. a short filmed intro) or use Snapchat only to promote the series."),
]


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------


def _font(lang: str, size: int):
    from PIL import ImageFont  # noqa: PLC0415

    path = config.FONTS_DIR / ("Vazirmatn-Black.ttf" if lang == "fa" else "Anton-Regular.ttf")
    try:
        engine = ImageFont.Layout.RAQM if _has_raqm() else ImageFont.Layout.BASIC
        return ImageFont.truetype(str(path), size, layout_engine=engine)
    except Exception:
        return ImageFont.truetype(str(path), size)


def _has_raqm() -> bool:
    try:
        from PIL import features  # noqa: PLC0415

        return bool(features.check("raqm"))
    except Exception:
        return False


def shape_text(text: str, lang: str) -> tuple[str, dict]:
    """Text + Pillow kwargs so Farsi letters join and read right to left."""
    if lang != "fa":
        return text, {}
    if _has_raqm():
        return text, {"direction": "rtl", "language": "fa"}
    try:  # Pillow without raqm: reshape + reorder ourselves (fine for Pillow, never for libass)
        import arabic_reshaper  # noqa: PLC0415
        from bidi.algorithm import get_display  # noqa: PLC0415

        return get_display(arabic_reshaper.reshape(text)), {}
    except Exception:
        return text, {}


def _wrap_lines(draw, text: str, font, max_w: int, kw: dict) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font, **kw) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:3]


def make_thumbnail(image: Path, text: str, lang: str, size: tuple[int, int], out: Path, badge: str = "",
                   accent: tuple[int, int, int] = (255, 46, 151)) -> Path:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps  # noqa: PLC0415

    W, H = size
    img = ImageOps.fit(Image.open(image).convert("RGB"), (W, H), method=Image.LANCZOS)
    img = ImageEnhance.Contrast(ImageEnhance.Color(img).enhance(1.25)).enhance(1.12)
    # dark gradient where the text goes
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(255 * max(0.0, (y / H - 0.35) / 0.65) ** 1.4 * 0.92))
    shade = Image.new("RGB", (W, H), (5, 2, 12))
    img = Image.composite(shade, img, grad.resize((W, H)))
    draw = ImageDraw.Draw(img)
    txt = (text or "").strip() or "WATCH THIS"
    if lang != "fa":
        txt = txt.upper()
    fsize = int(min(W, H) * (0.17 if W > H else 0.13))
    font = _font(lang, fsize)
    shaped, kw = shape_text(txt, lang)
    lines = _wrap_lines(draw, shaped, font, int(W * 0.88), kw)
    while len(lines) > 2 and fsize > 30:
        fsize = int(fsize * 0.86)
        font = _font(lang, fsize)
        lines = _wrap_lines(draw, shaped, font, int(W * 0.88), kw)
    line_h = int(fsize * 1.12)
    y = H - int(H * 0.08) - line_h * len(lines)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for i, ln in enumerate(lines):
        tw = draw.textlength(ln, font=font, **kw)
        x = (W - tw) / 2
        yy = y + i * line_h
        gdraw.text((x, yy), ln, font=font, fill=accent + (255,), **kw)
    glow = glow.filter(ImageFilter.GaussianBlur(fsize * 0.18))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    draw = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        tw = draw.textlength(ln, font=font, **kw)
        x = (W - tw) / 2
        yy = y + i * line_h
        color = (255, 255, 255) if i < len(lines) - 1 or len(lines) == 1 else (255, 230, 0)
        draw.text((x, yy), ln, font=font, fill=color, stroke_width=max(3, fsize // 14), stroke_fill=(0, 0, 0), **kw)
    if badge:
        bfont = _font("en", int(fsize * 0.32))
        bw = draw.textlength(badge, font=bfont)
        pad = int(fsize * 0.14)
        x0, y0 = int(W * 0.05), int(H * 0.05)
        draw.rounded_rectangle([x0, y0, x0 + bw + pad * 2, y0 + bfont.size + pad * 2], radius=pad * 2,
                               fill=accent + (235,))
        draw.text((x0 + pad, y0 + pad * 0.7), badge, font=bfont, fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    return out


# ---------------------------------------------------------------------------
# Titles, description, hashtags
# ---------------------------------------------------------------------------


def _tag(word: str) -> str:
    return "#" + re.sub(r"[^\w]", "", word.replace(" ", ""), flags=re.UNICODE)


def template_metadata(series: Series, ep: Episode, script: dict, lang: str) -> dict:
    name = series.name
    if lang == "fa":
        title = script.get("title_fa") or script.get("title", "")
        hook = (script["scenes"][0].get("narration_fa") or script["scenes"][0]["narration"]) if script["scenes"] else ""
        return {
            "titles": [f"{title} | {name} قسمت {ep.number}", f"{hook[:60]}… | قسمت {ep.number}", f"{name} - قسمت {ep.number}"],
            "description": f"{hook}\n\nقسمت {ep.number} از سریال «{name}».\n{script.get('cliffhanger_fa', '')}\nقسمت بعد را از دست ندهید!",
            "hashtags": {"youtube": ["#داستان", "#داستان_کوتاه", _tag(name), "#shorts"],
                         "tiktok": ["#داستان", "#سریال", _tag(name), "#fyp"],
                         "instagram": ["#داستان", "#ریلز", _tag(name)]},
        }
    hook = script["scenes"][0]["narration"] if script["scenes"] else ""
    return {
        "titles": [f"{script.get('title', '')} | {name} Ep. {ep.number}", f"{hook[:70]}", f"{name}: Episode {ep.number}"],
        "description": f"{hook}\n\nEpisode {ep.number} of {name}. {script.get('logline', '')}\n"
                       f"{script.get('next_tease', '')}\nFollow so you don't miss the next part!",
        "hashtags": {"youtube": ["#shorts", "#story", "#storytime", _tag(name)],
                     "tiktok": ["#story", "#storytime", "#series", _tag(name), "#fyp"],
                     "instagram": ["#reels", "#story", "#storytelling", _tag(name)]},
    }


def ai_metadata(series: Series, ep: Episode, script: dict, lang: str, rep=None) -> tuple[str, dict]:
    system = ("You write viral but honest titles, descriptions and hashtags for a serialized story channel. "
              "No clickbait lies, no misleading claims. Reply with JSON only.")
    lang_name = "Persian (Farsi)" if lang == "fa" else "English"
    user = json.dumps({
        "language": lang_name, "series": series.name, "episode": ep.number, "title": script.get("title"),
        "logline": script.get("logline"), "hook": script["scenes"][0]["narration"] if script["scenes"] else "",
        "cliffhanger": script.get("cliffhanger"), "next": script.get("next_tease"),
        "reply_format": {"titles": ["3 title options, max 70 characters"], "description": "3-5 short lines",
                         "hashtags": {"youtube": ["5 tags"], "tiktok": ["5 tags"], "instagram": ["8 tags"]}},
    }, ensure_ascii=False)

    def validate(obj):
        if not isinstance(obj, dict) or not obj.get("titles") or not obj.get("description"):
            raise ValueError("need titles and description")

    return llm.generate_json(system, user, validate=validate, rep=rep, task="metadata", temperature=0.7,
                             max_tokens=1200, allow_local=False)


def variation_warnings(series: Series, ep: Episode, script: dict, music_name: str) -> list[str]:
    """Warn if this episode looks too much like recent ones (helps against 'templated content' rules)."""
    warns = []
    prev = series.previous_summaries(ep.number, limit=10)
    if not prev:
        return warns
    title = script.get("title", "")
    for p in prev:
        if p.get("title") and difflib.SequenceMatcher(a=title.lower(), b=p["title"].lower()).ratio() > 0.8:
            warns.append(f"The title is very close to episode {p['episode']} (“{p['title']}”). Try a fresh title.")
            break
    if music_name and any(p.get("music") == music_name for p in prev[-3:]):
        warns.append("Same music as one of the last 3 episodes. Add more tracks to your library for variety.")
    cams = [s["camera"] for s in script["scenes"]]
    for p in prev[-3:]:
        if p.get("cameras") == cams:
            warns.append(f"Same camera moves, in the same order, as episode {p['episode']}. Change a few on the Scenes step.")
            break
    return warns


def write_metadata(series: Series, ep: Episode, script: dict, langs: list[str], credits: list[str],
                   creator_note: str, rep=None, warnings=()) -> dict:
    result = {"languages": {}, "credits": credits, "checklist": PLATFORM_CHECKLIST, "warnings": list(warnings)}
    disclosure = {"en": "Made with AI-generated images and voices. Story and editing by the creator.",
                  "fa": "تصاویر و صدا با هوش مصنوعی ساخته شده‌اند. داستان و تدوین توسط سازنده."}
    for lang in langs:
        provider = "Template"
        try:
            provider, meta = ai_metadata(series, ep, script, lang, rep)
        except Exception:
            meta = template_metadata(series, ep, script, lang)
        desc = str(meta.get("description", "")).strip()
        if creator_note.strip():
            desc += "\n\n" + creator_note.strip()
        if credits:
            desc += "\n\n" + ("موسیقی و صدا:" if lang == "fa" else "Music & sound:") + "\n" + "\n".join(credits)
        desc += "\n\n" + disclosure[lang]
        tags = meta.get("hashtags") or {}
        if isinstance(tags, list):
            tags = {"youtube": tags, "tiktok": tags, "instagram": tags}
        result["languages"][lang] = {
            "titles": [str(t) for t in meta.get("titles", [])][:3],
            "description": desc,
            "hashtags": {k: [t if str(t).startswith("#") else "#" + str(t) for t in v][:10] for k, v in tags.items()},
            "provider": provider,
        }
    write_json(ep.export_dir / "metadata.json", result)
    (ep.export_dir / "metadata.md").write_text(to_markdown(series, ep, result), encoding="utf-8")
    return result


def to_markdown(series: Series, ep: Episode, meta: dict) -> str:
    out = [f"# {series.name} · Episode {ep.number}", ""]
    for lang, m in meta["languages"].items():
        out += [f"## {'Farsi' if lang == 'fa' else 'English'}", "", "**Title ideas**"]
        out += [f"- {t}" for t in m["titles"]]
        out += ["", "**Description**", "", m["description"], ""]
        for platform, tags in m["hashtags"].items():
            out.append(f"**{platform.title()}**: {' '.join(tags)}")
        out.append("")
    out += ["## Before you post", ""]
    out += [f"- **{p}**: {t}" for p, t in meta["checklist"]]
    if meta.get("warnings"):
        out += ["", "## Variety check", ""] + [f"- ⚠️ {w}" for w in meta["warnings"]]
    return "\n".join(out) + "\n"
