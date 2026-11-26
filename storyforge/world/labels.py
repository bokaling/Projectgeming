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
        self.size = tuple(size)
        self.lang = lang
        self.px = max(14, int(min(size) * 0.036))  # small: the labels name parts, the keyword up top is the star
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
        if kind == "part":  # part names: a small clean white label with dark text (the look of the reference reels)
            d.rounded_rectangle([2, 2, w + 1, h + 1], radius=int(h * 0.3), fill=(255, 255, 255, 236),
                                outline=(20, 24, 30, 60), width=1)
            cx = (w + 4) // 2
            d.polygon([(cx - ptr * 0.5, h), (cx + ptr * 0.5, h), (cx, h + ptr)], fill=(255, 255, 255, 236))
            cy = 2 + h // 2
            dx = 2 + pad_x * 0.7
            d.ellipse([dx, cy - dot // 2, dx + dot, cy + dot // 2], fill=(255, 61, 154, 255))  # signature pink dot
            tx = dx + dot + int(px * 0.35)
            d.text((tx - bbox[0], 2 + pad_y - bbox[1]), shaped, font=font, fill=(22, 26, 32, 255), **kw)
            return np.asarray(img, np.uint8)
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


# ---------------------------------------------------------------------------------------------------------------
# 3D Documentary overlays: stat cards and a small map with a location marker (pictures drawn on top of the 3D)
# ---------------------------------------------------------------------------------------------------------------

# very simple continents (lon, lat): a low poly map, enough to show WHERE something happened
CONTINENTS = {
    "south_america": [(-80, 9), (-77, 8), (-72, 12), (-63, 11), (-60, 8), (-52, 5), (-50, 0), (-44, -2), (-35, -5),
                      (-35, -9), (-39, -15), (-41, -22), (-48, -26), (-53, -34), (-58, -38), (-62, -39), (-65, -42),
                      (-68, -50), (-69, -55), (-73, -53), (-75, -48), (-74, -42), (-73, -37), (-71, -30), (-70, -18),
                      (-76, -14), (-81, -6), (-80, -2), (-78, 2), (-79, 6)],
    "north_america": [(-168, 65), (-156, 71), (-140, 70), (-125, 70), (-95, 72), (-80, 66), (-62, 60), (-56, 52),
                      (-66, 45), (-70, 42), (-76, 35), (-81, 30), (-80, 25), (-83, 29), (-90, 29), (-97, 26), (-97, 20),
                      (-92, 18), (-87, 21), (-88, 15), (-83, 9), (-80, 8), (-85, 11), (-92, 15), (-105, 20),
                      (-110, 24), (-117, 32), (-124, 40), (-124, 48), (-135, 58), (-150, 60), (-165, 60)],
    "africa": [(-17, 21), (-10, 30), (-6, 36), (10, 37), (20, 32), (32, 31), (34, 28), (43, 12), (51, 12), (40, -2),
               (40, -12), (35, -24), (31, -30), (20, -35), (18, -30), (12, -17), (13, -6), (9, 4), (-5, 5), (-13, 8),
               (-17, 14)],
    "eurasia": [(-10, 36), (-9, 43), (-2, 44), (-5, 48), (3, 51), (8, 54), (10, 58), (5, 62), (16, 69), (28, 71),
                (60, 70), (80, 73), (105, 77), (140, 72), (180, 68), (170, 60), (160, 58), (142, 52), (135, 43),
                (128, 35), (122, 30), (120, 22), (108, 18), (106, 10), (100, 13), (98, 8), (102, 2), (98, 4), (92, 20),
                (80, 15), (77, 8), (72, 20), (66, 25), (57, 25), (50, 30), (48, 30), (36, 36), (28, 36), (23, 40),
                (16, 38), (12, 44), (7, 44), (3, 43), (-1, 38)],
    "australia": [(113, -22), (114, -34), (118, -35), (130, -32), (138, -35), (146, -39), (150, -37), (153, -28),
                  (146, -19), (142, -11), (136, -12), (130, -12), (125, -15), (122, -18)],
}


def _stat_card(self, big: str, small: str):
    key = f"stat|{self.lang}|{self.size}|{big}|{small}"
    if key in self.cache:
        return self.cache[key], key
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from ..publish import shape_text  # noqa: PLC0415

    W, H = self.size
    fb = _font(self.lang, int(min(W, H) * 0.11))
    fs = _font(self.lang, int(min(W, H) * 0.038))
    b_txt, kw = shape_text(big if self.lang == "fa" else big.upper(), self.lang)
    s_txt, kw2 = shape_text(small if self.lang == "fa" else small.upper(), self.lang)
    tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    bb = tmp.textbbox((0, 0), b_txt, font=fb, **kw)
    sb = tmp.textbbox((0, 0), s_txt, font=fs, **kw2) if small else (0, 0, 0, 0)
    pad = int(min(W, H) * 0.035)
    w = max(bb[2] - bb[0], sb[2] - sb[0]) + pad * 2
    h = (bb[3] - bb[1]) + (sb[3] - sb[1]) + pad * 2 + (int(pad * 0.5) if small else 0)
    img = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, w + 1, h + 1], radius=int(pad * 0.6), fill=(10, 12, 16, 200),
                        outline=(255, 214, 10, 230), width=max(2, pad // 10))
    d.text(((w + 4 - (bb[2] - bb[0])) / 2 - bb[0], 2 + pad - bb[1]), b_txt, font=fb, fill=(255, 255, 255, 255), **kw)
    if small:
        d.text(((w + 4 - (sb[2] - sb[0])) / 2 - sb[0], 2 + pad + (bb[3] - bb[1]) + int(pad * 0.5) - sb[1]), s_txt,
               font=fs, fill=(255, 214, 10, 255), **kw2)
    arr = np.asarray(img, np.uint8)
    self.cache[key] = arr
    return arr, key


def _map_inset(self, lat: float, lon: float, place: str = "", region: str = "", pulse: float = 0.0):
    key = f"map|{self.lang}|{self.size}|{lat:.2f}|{lon:.2f}|{place}|{pulse}"
    if key in self.cache:
        return self.cache[key], key
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from ..publish import shape_text  # noqa: PLC0415

    W, H = self.size
    w = int(min(W, H) * 0.42)
    h = int(w * 0.95)
    ss = 3  # drawn bigger, then scaled down: smooth edges
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(w * ss * 0.06)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=r, fill=(8, 18, 28, 215), outline=(120, 170, 200, 200),
                        width=2 * ss)
    span_lon, span_lat = 70.0, 66.0  # the window around the marker
    lon0, lat0 = float(lon) - span_lon / 2, float(lat) + span_lat / 2

    def xy(lo, la):
        return ((lo - lon0) / span_lon * w * ss, (lat0 - la) / span_lat * h * ss)

    for poly in CONTINENTS.values():
        pts = [xy(lo, la) for lo, la in poly]
        d.polygon(pts, fill=(64, 92, 92, 255), outline=(150, 190, 180, 255))
    for k in range(1, 4):  # faint grid lines
        d.line([(0, h * ss * k / 4), (w * ss, h * ss * k / 4)], fill=(120, 170, 200, 40), width=ss)
        d.line([(w * ss * k / 4, 0), (w * ss * k / 4, h * ss)], fill=(120, 170, 200, 40), width=ss)
    mx, my = xy(float(lon), float(lat))
    rr = (0.035 + 0.03 * pulse) * w * ss
    d.ellipse([mx - rr * 2, my - rr * 2, mx + rr * 2, my + rr * 2], outline=(255, 70, 60, int(200 * (1 - pulse))),
              width=2 * ss)
    d.ellipse([mx - rr * 0.6, my - rr * 0.6, mx + rr * 0.6, my + rr * 0.6], fill=(255, 70, 60, 255),
              outline=(255, 255, 255, 255), width=ss)
    img = img.resize((w, h), Image.LANCZOS)
    if place:
        d2 = ImageDraw.Draw(img)
        f = _font(self.lang, int(w * 0.085))
        txt, kw = shape_text(place if self.lang == "fa" else place.upper(), self.lang)
        bb = d2.textbbox((0, 0), txt, font=f, **kw)
        tx, ty = (w - (bb[2] - bb[0])) / 2 - bb[0], h - (bb[3] - bb[1]) - w * 0.06 - bb[1]
        d2.rounded_rectangle([tx + bb[0] - w * 0.03, ty + bb[1] - w * 0.02, tx + bb[2] + w * 0.03, ty + bb[3] + w * 0.02],
                             radius=int(w * 0.03), fill=(10, 12, 16, 220))
        d2.text((tx, ty), txt, font=f, fill=(255, 255, 255, 255), **kw)
    arr = np.asarray(img, np.uint8)
    self.cache[key] = arr
    return arr, key


LabelMaker.stat_card = _stat_card
LabelMaker.map_inset = _map_inset
