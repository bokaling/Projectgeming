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


LONGER = SCRIPT + "".join(f"\n[SCENE] a dark hallway number {k}\nNARRATOR: Something moved in the dark hallway {k}, "
                          f"and the machine answered with a sound nobody had heard before." for k in range(3))


def make(series_name="Gem", length="short", text=SCRIPT):
    series = project.Series.create(series_name)
    opts = project.EpisodeOptions(length=length, resolution="480p")
    res = pipeline.gemini_prompts(series, opts, text, Reporter(echo=False))
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


def test_other_picture_types_become_png(offline, tmp_path):
    """Gemini saves .jfif; phones save .heic; .webp/.avif too. All are stored as PNG."""
    from PIL import features

    _, ep, _, res = make(text=LONGER)
    total = res["pictures"]
    assert total >= 4
    src = tmp_path / "in"
    src.mkdir()
    Image.new("RGB", (64, 64), "red").save(src / "1.jfif", format="JPEG")
    Image.new("RGB", (64, 64), "blue").save(src / "2.webp", format="WEBP")
    Image.new("RGB", (64, 64), "green").save(src / "Gemini_Generated_Image_ab12cd34ef.jpeg", format="JPEG")
    files = [src / "1.jfif", src / "2.webp", src / "Gemini_Generated_Image_ab12cd34ef.jpeg"]
    if features.check("avif"):
        Image.new("RGB", (64, 64), "white").save(src / "4.avif", format="AVIF")
        files.append(src / "4.avif")
    msgs = gemini.add_images(ep, files, total)
    assert any("Converted" in m and "1.jfif" in m for m in msgs)
    for n in range(1, 4):
        p = gemini.image_for(ep, n)
        assert p.suffix == ".png" and p.read_bytes()[:4] == b"\x89PNG"
    assert Image.open(gemini.image_for(ep, 1)).getpixel((5, 5))[0] > 200  # red stays red
    # a .jfif put straight into the Drive folder is converted, and the original moved out of the way
    Image.new("RGB", (64, 64), "yellow").save(gemini.folder(ep) / "4.jfif", format="JPEG")
    gemini.scan_folder(ep, total)
    assert gemini.image_for(ep, 4).name == "4.png"
    assert (gemini.folder(ep) / "originals" / "4.jfif").exists()
    assert gemini.scan_folder(ep, total) == []  # nothing new the second time
    # a broken file gives a friendly message, not a crash
    (src / "bad.heic").write_bytes(b"not a picture")
    assert any("Couldn't open bad.heic" in m for m in gemini.add_images(ep, [src / "bad.heic"], total))
    # replace with a .jfif
    gemini.set_image(ep, 2, src / "1.jfif")
    assert gemini.image_for(ep, 2).name == "002_1.png"


def test_heic_opens_when_pillow_heif_is_installed(tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")

    pillow_heif.register_heif_opener()
    try:
        Image.new("RGB", (64, 64), "red").save(tmp_path / "x.heic", format="HEIF")
    except Exception:  # noqa: BLE001 (no HEIF encoder in this build)
        pytest.skip("no HEIF encoder")
    out = gemini.to_png(tmp_path / "x.heic", tmp_path / "x.png")
    assert Image.open(out).size == (64, 64)
