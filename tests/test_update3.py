"""T4 feedback round: characters, [SCENE] text first, blurry retries, motion, length, model files."""
import json
import struct

import numpy as np
import pytest
from PIL import Image, ImageFilter

from storyforge import characters, config, images, models, net, paste, planner, project, script
from storyforge.messages import FriendlyError, Reporter


@pytest.fixture()
def offline_net(monkeypatch):
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(net.ServiceError("offline")))


SCRIPT = """[TITLE] The Machine
[CHARACTER] NIKOLA: man, 40s, short dark hair, lab coat
[SCENE] close up of a speaker on an old wooden desk
NARRATOR: At midnight the speaker began to hum, and then it spoke in a voice nobody in the lab recognised at all.
[SCENE] Nikola leaning over the machine, sparks flying
NIKOLA: It is alive. I can hear it thinking.
NARRATOR: He did not sleep that night, or the next, while the voice kept whispering numbers to him."""


def test_character_tag_look_and_gender(sf_root, offline_net):
    series = project.Series.create("Lab")
    sc = script.script_from_text(series, series.episode(1), project.EpisodeOptions(), SCRIPT, Reporter(echo=False))
    nik = series.character("Nikola")
    assert nik["description"] == "man, 40s, short dark hair, lab coat" and nik["gender"] == "male"
    s1, s2 = sc["scenes"][0], sc["scenes"][-2] if len(sc["scenes"]) > 2 else sc["scenes"][1]
    # scene 1: your text first, close-up framing, nobody added (a speaker is a loudspeaker here)
    p1, _ = characters.scene_prompt(series, s1, with_refs=False)
    assert p1.startswith("close up of a speaker on an old wooden desk.") and "Shot: close-up shot" in p1
    assert "Nikola" not in p1 and "lab coat" not in p1 and "No text, no letters, no watermark." in p1
    # a scene that names him: his look is in EVERY shot of it
    nik_scene = next(x for x in sc["scenes"] if "Nikola leaning" in x["visual"])
    for k in range(1 + len(nik_scene["shots"])):
        pk, _ = characters.scene_prompt(series, nik_scene, with_refs=False, shot_index=k)
        assert "Nikola is man, 40s, short dark hair, lab coat" in pk, k


def test_new_picture_every_few_seconds_with_different_framing(sf_root, offline_net):
    series = project.Series.create("Shots")
    sc = script.script_from_text(series, series.episode(1), project.EpisodeOptions(), SCRIPT, Reporter(echo=False))
    words = sum(len(x["narration"].split()) for x in sc["scenes"])
    pictures = sum(1 + len(x["shots"]) for x in sc["scenes"])
    assert pictures >= words / (paste.WORDS_PER_SHOT["short"] * 1.5)  # about one picture per 2.5 s of voice
    frames = [f["shot"] for x in sc["scenes"] for f in [x] + x["shots"]]
    assert all(a != b for a, b in zip(frames, frames[1:]))  # never the same framing twice in a row
    assert planner.infer_shot("Top down view of the city") == "top_down" and planner.infer_shot("a cat") is None


def test_length_warning(sf_root, offline_net):
    assert "about 150 words" in paste.length_warning(SCRIPT, "short")
    assert paste.length_warning(" ".join(["word"] * 160), "short") == ""
    rep = Reporter(echo=False)
    series = project.Series.create("Len")
    script.script_from_text(series, series.episode(1), project.EpisodeOptions(), SCRIPT, rep)
    assert "📏" in rep.text() and any(p == "Script length" for _, p, _ in rep.summary)


def _sharp_image():
    rng = np.random.default_rng(0)
    return Image.fromarray((rng.random((320, 240, 3)) * 255).astype("uint8"))


def test_picture_problem_detects_blank_and_blurry():
    assert images.picture_problem(_sharp_image()) == ""
    assert "blank" in images.picture_problem(Image.new("RGB", (240, 320), (120, 120, 120)))
    blob = _sharp_image().resize((24, 32)).resize((240, 320)).filter(ImageFilter.GaussianBlur(12))
    assert images.picture_problem(blob) != ""


def test_gpu_retries_blurry_pictures_with_new_seeds(sf_root, monkeypatch, tmp_path):
    monkeypatch.setattr(config.get(), "gpu", config.GPUInfo(True, "Tesla T4", 15.0))
    seeds = []

    def fake_generate(self, job):
        seeds.append(job.seed)
        return Image.new("RGB", (240, 320), (128, 128, 128)) if len(seeds) < 3 else _sharp_image()

    monkeypatch.setattr(images.KleinEngine, "generate", fake_generate)
    monkeypatch.setattr(images.KleinEngine, "encode", lambda self, prompts, rep=None: None)
    rep = Reporter(echo=False)
    counts = images.generate_batch([images.ImageJob("p", tmp_path / "a.png", (1080, 1920), 5, label="Scene 9")], rep)
    assert len(set(seeds)) == 3 and seeds[0] == 5 and "try 3" in next(iter(counts))
    assert "blank" in rep.text() and (tmp_path / "a.png").exists()


def test_gpu_error_is_shown_not_hidden_behind_online_queue(sf_root, monkeypatch, tmp_path):
    monkeypatch.setattr(config.get(), "gpu", config.GPUInfo(True, "Tesla T4", 15.0))
    online = []
    monkeypatch.setattr(images, "pollinations", lambda *a, **k: online.append(1))
    monkeypatch.setattr(images.KleinEngine, "encode", lambda self, prompts, rep=None: None)

    def broken(self, job):
        raise RuntimeError("SafetensorError: header too large")

    monkeypatch.setattr(images.KleinEngine, "generate", broken)
    with pytest.raises(FriendlyError) as err:
        images.generate_batch([images.ImageJob("p", tmp_path / "a.png", (1080, 1920), 5)], Reporter(echo=False))
    assert "header too large" in err.value.what and not online


def _write_safetensors(path, n_bytes=16, header_override=None):
    header = json.dumps({"w": {"dtype": "F32", "shape": [n_bytes // 4], "data_offsets": [0, n_bytes]}}).encode()
    n = header_override if header_override is not None else len(header)
    path.write_bytes(struct.pack("<Q", n) + header + b"\0" * n_bytes)


def test_safetensors_check(tmp_path):
    good, huge, cut = tmp_path / "good.safetensors", tmp_path / "huge.safetensors", tmp_path / "cut.safetensors"
    _write_safetensors(good)
    _write_safetensors(huge, header_override=10**12)
    _write_safetensors(cut)
    cut.write_bytes(cut.read_bytes()[:-8])
    assert models.safetensors_problem(good) == ""
    assert "header" in models.safetensors_problem(huge) and "cut off" in models.safetensors_problem(cut)
    assert "wrong size" in models.safetensors_problem(good, expected_size=5)


def test_zoom_punch_and_stronger_motion():
    from storyforge.motion import effects

    move = effects.camera_move("push_in")
    assert move.zoom[1] - move.zoom[0] > 0.18  # stronger than before (0.13)
    move.punch, move.punches = 0.16, (0.12,)
    ov = effects.Overlay((90, 160), [], 1, 1.0, grain=False, vignette=False)
    z_before = effects.camera_state(move, ov, 2, 30, 30)[1]   # t = 0.07 s
    z_punch = effects.camera_state(move, ov, 8, 30, 30)[1]    # t = 0.27 s
    assert z_punch > z_before * 1.12


def test_multi_shot_scene_clip(sf_root, tmp_path):
    from storyforge import media
    from storyforge.motion import clip

    shots = []
    for k in range(3):
        img = tmp_path / f"{k}.png"
        images.placeholder("x", (180, 320), seed=k).save(img)
        shots.append({"image": str(img), "depth": "", "camera": ["push_in", "pan_left", "tilt_up"][k], "fx": [],
                      "seed": k, "punch": 0.16 if k == 0 else 0.0, "shake": [], "strength": 1.0})
    out = tmp_path / "scene.mp4"
    how = clip.from_shots(shots, out, (180, 320), 2.5, 24, use_gpu=False)
    assert "3 shots" in how and abs(media.duration(out) - 2.5) < 0.1
