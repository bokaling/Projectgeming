import io

import numpy as np
import pytest
from PIL import Image

from storyforge import characters, images, net, project
from storyforge.messages import Reporter


def png_bytes(w=64, h=96, color=(200, 50, 120)):
    img = Image.new("RGB", (w, h), color)
    img.putpixel((3, 3), (0, 0, 0))  # not perfectly flat
    for x in range(w):
        img.putpixel((x, h // 2), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Resp:
    def __init__(self, content=b"", js=None):
        self.content = content
        self._js = js
        self.status_code = 200

    def json(self):
        return self._js


def test_gen_size_multiple_of_16():
    assert images.gen_size((1080, 1920)) == (752, 1344)
    w, h = images.gen_size((1920, 1080))
    assert w % 16 == 0 and h % 16 == 0 and max(w, h) <= 1344


def test_placeholder_looks_like_a_scene():
    img = images.placeholder("x", (360, 640), seed=3)
    arr = np.asarray(img)
    assert img.size == (360, 640) and arr.std() > 10  # not a flat card


def test_offline_falls_back_to_placeholder(sf_root, monkeypatch):
    def offline(*a, **k):
        raise net.ServiceError("network problem", None, True)

    monkeypatch.setattr(net, "request", offline)
    monkeypatch.setattr(images, "_last_pollinations", [0.0])
    out = sf_root / "s01.png"
    rep = Reporter(echo=False)
    counts = images.generate_batch([images.ImageJob("a cat", out, (1080, 1920), 5, label="Scene 1")], rep)
    assert counts == {"Placeholder": 1}
    im = Image.open(out)
    assert abs(im.width / im.height - 9 / 16) < 0.02


def test_pollinations_used_when_online(sf_root, monkeypatch):
    calls = []

    def fake(method, url, **kw):
        calls.append((url, kw.get("params")))
        return Resp(png_bytes(720, 1280))

    monkeypatch.setattr(net, "request", fake)
    monkeypatch.setattr(images, "_last_pollinations", [0.0])
    out = sf_root / "p.png"
    name = images.generate_to_file("a red fox at night", out, (1080, 1920), seed=9)
    assert name == "Pollinations" and out.exists()
    assert "a%20red%20fox" in calls[0][0] and calls[0][1]["seed"] == 9


def test_ai_horde_flow(sf_root, monkeypatch):
    seq = []

    def fake(method, url, **kw):
        seq.append(url)
        if url.endswith("/generate/async"):
            return Resp(js={"id": "job1"})
        if "/generate/check/" in url:
            return Resp(js={"done": True})
        if "/generate/status/" in url:
            return Resp(js={"generations": [{"img": "https://r2.example/img.webp"}]})
        return Resp(png_bytes(576, 1024))

    monkeypatch.setattr(net, "request", fake)
    monkeypatch.setattr(images.time, "sleep", lambda s: None)
    img = images.ai_horde("prompt", (1080, 1920), 1)
    assert img.size == (576, 1024) and seq[0].endswith("/generate/async")


def test_scene_prompt_has_bible_and_refs(sf_root):
    s = project.Series.create("Look")
    s.data["style"] = "ink comic"
    c = characters.add_character(s, "Mira", "silver hair, red coat")
    ref = characters.ref_path(s, c)
    ref.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 10)).save(ref)
    scene = {"visual": "Mira runs through rain", "characters": ["Mira", "Ghost"], "location": "harbor"}
    prompt, refs = characters.scene_prompt(s, scene, with_refs=True)
    assert refs == [ref] and "image 1 shows Mira" in prompt
    assert "silver hair, red coat" in prompt and "ink comic" in prompt and "harbor" in prompt
    prompt2, refs2 = characters.scene_prompt(s, scene, with_refs=False)
    assert refs2 == [] and "reference images" not in prompt2


def test_character_reference_made_once(sf_root, monkeypatch):
    # offline: no placeholder is saved as a reference (it would mislead the GPU model later)
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(net.ServiceError("offline")))
    s = project.Series.create("Refs")
    characters.add_character(s, "Leo", "")
    rep = Reporter(echo=False)
    characters.ensure_references(s, None, rep)
    assert not characters.has_ref(s, s.character("Leo")) and "No reference picture for Leo" in rep.text()
    # online: made once, then skipped
    images._down_until.clear()
    monkeypatch.setattr(net, "request", lambda *a, **k: Resp(png_bytes(512, 680)))
    characters.ensure_references(s, None, rep)
    assert characters.has_ref(s, s.character("Leo"))
    before = rep.text()
    characters.ensure_references(s, None, rep)  # nothing to do the second time
    assert rep.text() == before
    # your own picture replaces it
    mine = sf_root / "mine.png"
    Image.new("RGB", (50, 80), (1, 2, 3)).save(mine)
    characters.set_reference(s, "Leo", str(mine))
    assert characters.ref_fingerprint(s, s.character("Leo")) == "uploaded"
