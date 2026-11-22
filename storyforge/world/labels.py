"""Floating labels next to objects: a small dark tag with colored text and a pointer, made with Pillow.

Colors by meaning: problem = red, part = orange, number = white, info = teal.
Farsi works (shaped with raqm, or arabic-reshaper when Pillow has no raqm; that's fine for Pillow).
"""

from __future__ import annotations

import numpy as np

from .. import config

KIND_COLORS = {"problem": (255, 92, 92), "part": (255, 170, 60), "number": (255, 255, 255), "info": (120, 235, 225)}
KIND_HEX = {k: "#%02X%02X%02X" % v for k, v in KIND_COLORS.items()}


def _font(lang: str, px: int):
    from PIL import ImageFont  # noqa: PLC0415

    from ..publish import _has_raqm  # noqa: PLC0415

    name = "Vazirmatn-Black.ttf" if lang == "fa" else "Montserrat-ExtraBold.ttf"
    path = config.FONTS_DIR / name
    if not path.exists():
        cands = sorted(config.FONTS_DIR.glob("Montserrat*.ttf")) if lang != "fa" else sorted(config.FONTS_DIR.glob("Vazir*.ttf"))
        path = cands[0] if cands else None
    try:
        engine = ImageFont.Layout.RAQM if _has_raqm() else ImageFont.Layout.BASIC
        return ImageFont.truetype(str(path), px, layout_engine=engine)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


class LabelMaker:
    """label(text, kind) → (RGBA numpy image, cache key). Size follows the video size."""

    def __init__(self, size: tuple[int, int], lang: str = "en"):
        self.lang = lang
        self.px = max(16, int(min(size) * 0.042))
        self.cache: dict = {}

    def __call__(self, text: str, kind: str = "part"):
        key = f"{kind}|{self.lang}|{self.px}|{text}"
        if key not in self.cache:
            self.cache[key] = self._make(text, kind)
            if len(self.cache) > 500:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[key], key

    def _make(self, text: str, kind: str) -> np.ndarray:
        from PIL import Image, ImageDraw  # noqa: PLC0415

        from ..publish import shape_text  # noqa: PLC0415

        px = self.px
        font = _font(self.lang, px)
        shown = text if self.lang == "fa" else text.upper()
        shaped, kw = shape_text(shown, self.lang)
        tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        bbox = tmp.textbbox((0, 0), shaped, font=font, **kw)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad_x, pad_y, ptr = int(px * 0.55), int(px * 0.38), int(px * 0.45)
        dot = int(px * 0.32)
        w = tw + pad_x * 2 + dot + int(px * 0.35)
        h = th + pad_y * 2
        img = Image.new("RGBA", (w + 4, h + ptr + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        color = KIND_COLORS.get(kind, KIND_COLORS["info"])
        d.rounded_rectangle([2, 2, w + 1, h + 1], radius=int(h * 0.45), fill=(8, 26, 31, 225),
                            outline=color + (255,), width=max(2, px // 12))
        cx = (w + 4) // 2
        d.polygon([(cx - ptr * 0.6, h), (cx + ptr * 0.6, h), (cx, h + ptr)], fill=color + (255,))
        cy = 2 + h // 2
        dx = 2 + pad_x * 0.7
        d.ellipse([dx, cy - dot // 2, dx + dot, cy + dot // 2], fill=color + (255,))
        tx = dx + dot + int(px * 0.35)
        d.text((tx - bbox[0], 2 + pad_y - bbox[1]), shaped, font=font, fill=color + (255,), **kw)
        return np.asarray(img, np.uint8)


def card_image(text: str, lang: str, size: tuple[int, int]) -> np.ndarray:
    """The end card ("PART 2 👀" / "THE END") as a full-frame RGBA picture."""
    import tempfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    from ..publish import end_card_png  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        p = end_card_png(text, lang, size, Path(tmp) / "card.png")
        return np.asarray(Image.open(p).convert("RGBA"), np.uint8)
