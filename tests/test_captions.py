import subprocess

import numpy as np
import pytest
from PIL import Image

from storyforge import captions
from storyforge.audio import align


def words_for(text, total=4.0):
    return align.proportional(align.split_words(text), 0.0, total)


def test_lines_are_short_and_break_at_sentences():
    w = words_for("The radio woke up. Nobody touched it, but it kept talking about tomorrow")
    lines = captions.group_lines(w, "9x16", "en")
    assert all(len(line) <= 4 for line in lines)
    assert lines[0][-1]["w"] == "up."  # a sentence end closes the line, and "up." isn't left alone
    assert all(len(line) > 1 for line in lines)
    assert max(len(line) for line in captions.group_lines(w, "16x9", "en")) > 3


def test_ass_has_one_event_per_word_and_farsi_rules():
    w = words_for("در سال ۱۴۰۵، میرا صدایی شنید!")
    ass = captions.build_ass(w, (1080, 1920), "9x16", "fa")
    style = [ln for ln in ass.splitlines() if ln.startswith("Style:")][0].split(",")
    assert style[1] == "Vazirmatn" and style[13] == "0"  # Spacing must be 0 for Persian
    assert style[-1] == "-1"  # Encoding -1: libass detects right-to-left (else words come out mirrored)
    events = [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]
    assert len(events) == len(w)
    assert all(captions.RLE in e and captions.PDF in e for e in events)
    en = captions.build_ass(words_for("Run now"), (1920, 1080), "16x9", "en")
    assert "RUN" in en and en.splitlines()[[i for i, ln in enumerate(en.splitlines()) if ln.startswith("Style:")][0]].endswith(",1")


def test_karaoke_and_plain_styles():
    w = words_for("One two three")
    assert "\\kf" in captions.build_ass(w, (1080, 1920), "9x16", "en", style="karaoke")
    fa_k = captions.build_ass(words_for("یک دو سه"), (1080, 1920), "9x16", "fa", style="karaoke")
    assert "\\kf" not in fa_k  # RTL karaoke falls back to word highlight
    plain = captions.build_ass(w, (1080, 1920), "9x16", "en", style="plain")
    assert sum(ln.startswith("Dialogue:") for ln in plain.splitlines()) == 1


def _yellow_position(png):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    text = a.sum(axis=2) > 450
    yellow = (a[..., 0] > 200) & (a[..., 1] > 180) & (a[..., 2] < 90)
    xs = np.where(text.any(0))[0]
    return (np.where(yellow.any(0))[0].mean() - xs.min()) / (xs.max() - xs.min())


@pytest.mark.parametrize("lang,text,expect_right", [("fa", "در سال ۱۴۰۵، میرا لا به", True),
                                                     ("en", "In the year twenty, Mira ran", False)])
def test_burned_highlight_is_on_the_correct_side(tmp_path, lang, text, expect_right):
    """Regression: the 2nd word must be highlighted near the RIGHT edge in Farsi, LEFT in English."""
    w = words_for(text, 3.0)
    ass = tmp_path / "c.ass"
    captions.write_ass(ass, w, (960, 540), "16x9", lang, total=3.0)
    t = (w[1]["s"] + w[1]["e"]) / 2
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x203040:s=960x540:d=3",
                    "-vf", captions.ass_filter(ass), "-ss", f"{t:.2f}", "-frames:v", "1", str(png)], check=True)
    pos = _yellow_position(png)
    assert (pos > 0.6) if expect_right else (pos < 0.4), pos
