"""Gemini images mode: prompts → your images → video without the image model."""
import pytest
from PIL import Image

from storyforge import gemini, images, media, pipeline, project
from storyforge.messages import FriendlyError, Reporter

SCRIPT = """[TITLE] The Machine
[CHARACTER] NIKOLA: man, 40s, short dark hair, lab coat
[SCENE] Nikola leaning over a humming machine in a dark lab
NIKOLA: It is alive. I can hear it thinking.
[SCENE] close up of an old speaker on a desk
NARRATOR: At midnight the speaker began to hum, and then it spoke in a voice nobody recognised."""


def make(series_name="Gem", length="short"):
    series = project.Series.create(series_name)
    opts = project.EpisodeOptions(length=length, resolution="480p")
    res = pipeline.gemini_prompts(series, opts, SCRIPT, Reporter(echo=False))
    ep = series.episode(res["episode"])
    return series, ep, opts, res


def pic(path, size=(300, 200), color=(200, 40, 90)):
    Image.new("RGB", size, color).save(path)
    return path


def test_prompts_are_standalone(offline):
    series, ep, opts, res = make()
    text = (ep.dir / "prompts.txt").read_text(encoding="utf-8")
    assert (ep.export_dir / "prompts.txt").exists() and gemini.folder(ep).is_dir()
    blocks = [b for b in text.split("\n\n") if b[:1].isalnum()]
    assert blocks[0].startswith("C1. CHARACTER SHEET · Nikola") and "Front view" in blocks[0]
    scene_blocks = [b for b in blocks if b[0].isdigit()]
    assert len(scene_blocks) == res["pictures"] >= 2
    for b in blocks:
        assert "vertical 9:16" in b and b.rstrip().endswith("cinematic, highly detailed, no text, no letters, no watermark.")
    nik = [b for b in scene_blocks if "Nikola leaning" in b]
    assert nik and all("Nikola: man, 40s, short dark hair, lab coat." in b for b in nik)  # full look every time
    long_prompt = gemini.scene_prompt(series, ep.load_script()["scenes"][0], 0, "long")
    assert "horizontal 16:9" in long_prompt


def test_file_name_matching():
    assert gemini._number("1.png") == ("", 1) and gemini._number("scene_03.jpg") == ("", 3)
    assert gemini._number("C2.png") == ("C", 2) and gemini._number("character_1.webp") == ("C", 1)
    assert gemini._number("Gemini_Generated_Image_k3x9q2abcd.png") is None


def test_upload_match_replace_move_and_missing(offline, tmp_path):
    series, ep, opts, res = make()
    total = res["pictures"]
    files = [pic(tmp_path / "scene_02.png"), pic(tmp_path / "Gemini_Generated_Image_aaaa.png", color=(1, 2, 3))]
    gemini.add_images(ep, files, total)
    assert gemini.image_for(ep, 2).name == "scene_02.png"  # by number
    assert gemini.image_for(ep, 1).name.startswith("Gemini_Generated")  # no number: next free one
    assert gemini.missing(ep, total) == list(range(3, total + 1))
    gemini.move(ep, 1, 2, total)
    assert gemini.image_for(ep, 2).name.startswith("Gemini_Generated")
    gemini.set_image(ep, 1, pic(tmp_path / "new.png"))
    assert gemini.image_for(ep, 1).name == "001_new.png"
    # from your phone: dropped straight into the Drive folder
    pic(gemini.folder(ep) / f"{total}.jpg")
    gemini.scan_folder(ep, total)
    assert gemini.image_for(ep, total) is not None


def test_fit_fills_frame(tmp_path):
    out = tmp_path / "o.png"
    gemini.fit(pic(tmp_path / "wide.png", (1600, 400)), out, (1080, 1920))
    im = Image.open(out)
    assert im.size == (1080, 1920) and im.getpixel((5, 5)) == (200, 40, 90)  # no black bars


def test_video_with_my_images_skips_flux(offline, tmp_path, monkeypatch):
    series, ep, opts, res = make()
    for n in range(1, res["pictures"] + 1):
        pic(gemini.folder(ep) / f"{n}.png", color=(20 * n % 255, 80, 160))
    monkeypatch.setattr(images, "generate_batch", lambda *a, **k: pytest.fail("FLUX must not run"))
    o = ep.load_options()
    result = pipeline.Pipeline(series, ep, Reporter(echo=False), o).make_video()
    assert media.video_size(result["videos"][0]) == (480, 854)
    assert ep.state.info("image:s01:9x16")["provider"] == "your image"


def test_missing_images_ask_then_nearest_or_flux(offline, tmp_path, monkeypatch):
    series, ep, opts, res = make()
    pic(gemini.folder(ep) / "1.png")
    o = ep.load_options()
    with pytest.raises(FriendlyError) as err:  # default: ask
        pipeline.Pipeline(series, ep, Reporter(echo=False), o).my_images()
    assert "missing" in err.value.what
    o.missing_policy = "nearest"
    pipeline.Pipeline(series, ep, Reporter(echo=False), o).my_images()
    assert "reused" in ep.state.info("image:s02:9x16")["provider"]
    asked = []
    monkeypatch.setattr(images, "generate_batch", lambda jobs, rep, **k: asked.extend(j.key for j in jobs) or {})
    series2, ep2, _, res2 = make("Gem2")
    pic(gemini.folder(ep2) / "1.png")
    o2 = ep2.load_options()
    o2.missing_policy = "flux"
    pipeline.Pipeline(series2, ep2, Reporter(echo=False), o2).my_images()
    assert asked and all(not k.startswith("image:s01:9x16") or k.count(":") == 3 for k in asked)
    assert "image:s01:9x16" not in asked  # your picture #1 is kept, only missing ones go to FLUX
