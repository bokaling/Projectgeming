import subprocess

import numpy as np
import pytest
from PIL import Image

from storyforge import images, media, script
from storyforge.motion import clip, depth, effects, i2v


@pytest.fixture()
def scene_png(tmp_path):
    p = tmp_path / "img.png"
    images.placeholder("x", (384, 672), seed=4).save(p)
    return p


def test_every_camera_move_exists():
    for cam in script.CAMERAS:
        m = effects.camera_move(cam)
        assert m.zoom[0] >= 1.0 and m.zoom[1] >= 1.0, cam  # never shows the edge of the picture


def test_frames_move_and_have_right_shape(scene_png):
    rgb = np.asarray(Image.open(scene_png).convert("RGB"))
    d = depth.smooth(depth.fake_depth(rgb))
    frs = list(effects.frames(rgb, d, (180, 320), 1.0, 12, "orbit_left", ["dust"], seed=1))
    assert len(frs) == 12 and frs[0].shape == (320, 180, 3) and frs[0].dtype == np.uint8
    assert np.abs(frs[0].astype(int) - frs[-1].astype(int)).mean() > 2  # it really moves


@pytest.mark.parametrize("fx", script.EFFECTS)
def test_each_effect_renders(scene_png, fx):
    rgb = np.asarray(Image.open(scene_png).convert("RGB"))
    out = list(effects.frames(rgb, None, (160, 284), 0.5, 10, "push_in", [fx], seed=2, shake_times=[0.1]))
    assert len(out) == 5 and all(f.shape == (284, 160, 3) for f in out)


def test_blur_fill_for_other_shapes(scene_png):
    rgb = np.asarray(Image.open(scene_png).convert("RGB"))  # tall picture
    canvas, dcanvas = effects.prepare_canvas(rgb, None, (320, 180))  # wide video
    assert canvas.shape[1] > canvas.shape[0] and dcanvas is not None
    assert dcanvas[0, 0] < 0.1 and dcanvas[dcanvas.shape[0] // 2, dcanvas.shape[1] // 2] > 0.5


def test_depth_falls_back_without_model(sf_root, scene_png, tmp_path):
    out = tmp_path / "d.png"
    method = depth.make_depth(scene_png, out)
    assert out.exists() and method in ("simple depth (no model)", "Depth Anything V2 Small")
    d = depth.load_depth(out, (100, 60))
    assert d.shape == (100, 60) and 0 <= d.min() and d.max() <= 1
    # bottom of a landscape is nearer than the sky
    assert d[90:].mean() > d[:10].mean()


def test_image_clip_exact_length(sf_root, scene_png, tmp_path):
    out = tmp_path / "c.mp4"
    method = clip.from_image(scene_png, None, out, (180, 320), 1.5, 24, "pan_left", ["snow"], seed=3)
    assert method == "Ken Burns" and abs(media.duration(out) - 1.5) < 0.1
    assert media.video_size(out) == (180, 320)


def test_user_video_is_fitted_and_lengthened(sf_root, tmp_path):
    src = tmp_path / "wide.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:d=1:r=24",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    out = tmp_path / "fit.mp4"
    note = clip.from_video(src, out, (180, 320), 2.5, 24)
    assert "slowed" in note and abs(media.duration(out) - 2.5) < 0.1 and media.video_size(out) == (180, 320)
    assert not media.has_audio(out)


def test_hero_clip_skipped_without_gpu(sf_root, scene_png, tmp_path):
    ok, why = i2v.make_hero_clip(scene_png, {"visual": "x"}, tmp_path / "h.mp4", "9x16", 5, 1, None)
    assert ok is False and "GPU" in why
    assert "dolly in" in i2v.hero_prompt({"visual": "A ship", "camera": "push_in"})


def test_gpu_renderer_matches_cpu_renderer(scene_png):
    torch = pytest.importorskip("torch")  # noqa: F841
    from storyforge.motion import gpu

    rgb = np.asarray(Image.open(scene_png).convert("RGB"))
    d = depth.smooth(depth.fake_depth(rgb))
    for cam, fx in (("orbit_left", []), ("push_in", ["fog", "god_rays", "light_leak", "dust", "flicker"])):
        a = list(effects.frames(rgb, d, (180, 320), 0.5, 12, cam, fx, seed=3, shake_times=[0.1], grain=False))
        b = list(gpu.frames(rgb, d, (180, 320), 0.5, 12, cam, fx, seed=3, shake_times=[0.1], grain=False, device="cpu"))
        assert len(a) == len(b)
        assert max(np.abs(x.astype(int) - y.astype(int)).mean() for x, y in zip(a, b)) < 0.5, cam


def test_parallel_scene_rendering(sf_root, scene_png, tmp_path):
    import concurrent.futures

    jobs = [{"video": "", "image": str(scene_png), "depth": "", "out": str(tmp_path / f"c{i}.mp4"), "size": [90, 160],
             "seconds": 0.5, "fps": 12, "camera": cam, "fx": [], "seed": i, "shake": [], "strength": 1.0,
             "extras": True} for i, cam in enumerate(["push_in", "pan_left", "tilt_up"])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(clip.run_in_subprocess, jobs))
    assert all(r.startswith("Ken Burns") for r in results)
    assert all(abs(media.duration(j["out"]) - 0.5) < 0.1 for j in jobs)
