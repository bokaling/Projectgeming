"""Phase 3 polish: seamless horizon, camera drift, explainer music, bigger keyword captions, more action sounds."""
import numpy as np

from storyforge import captions, script
from storyforge.audio import music
from storyforge.world import examples
from storyforge.world import plan as P
from storyforge.world.scene import World, freeze_layout
from test_world import fake_timeline, make_script


def _cow_world(size=(180, 320)):
    sc = make_script(examples.COW_POOP_SCRIPT)
    texts = [s["narration"] for s in sc["scenes"]]
    return World(freeze_layout(P.validate(examples.COW_POOP_PLAN, texts)[0]), fake_timeline(texts), size)


def test_no_hard_horizon_line(needs_gl):
    """An empty floor seen from low down: far floor fades into the exact background colour (no band)."""
    from storyforge.world import gl

    r = gl.Renderer((180, 320), msaa=2, shadow_size=256)
    try:
        img = r.render(gl.Frame(eye=(0.0, 3.0, 0.0), target=(0.0, 2.0, -30.0), draws=[], focus=(0.0, 0.0, -30.0),
                                focus_radius=8.0, grid_center=(9000.0, 9000.0))).astype(np.float32)
    finally:
        r.release()
    rows = img.mean(axis=(1, 2))  # brightness of every row, top to bottom
    assert np.abs(np.diff(rows)).max() < 2.0


def test_camera_drifts_gently_and_smoothly():
    w = _cow_world()
    i = 4
    a = w.camera(i, 1.0)[0]
    b = w.camera(i, 1.0 + 1 / 30)[0]
    raw_a, raw_b = w._camera(i, 1.0)[0], w._camera(i, 1.0 + 1 / 30)[0]
    d = float(np.linalg.norm(np.asarray(raw_a) - np.asarray(w._camera(i, 1.0)[1])))
    assert 0 < np.linalg.norm(np.asarray(a) - raw_a) < 0.03 * d  # it moves, but only a little
    assert np.linalg.norm((b - a) - (raw_b - raw_a)) < 0.002 * d  # and slowly (no shaking from frame to frame)


def test_explainer_music_is_the_default_and_soft():
    assert script._explainer_mood("The tank fills and the generator spins.") == "explainer"
    assert script._explainer_mood("A deadly explosion. Danger everywhere. Panic.") in ("tense", "dark", "action")
    x = music.generate_music("explainer", 12, 3)
    spec = np.abs(np.fft.rfft(x[:, 0]))
    freqs = np.fft.rfftfreq(len(x), 1 / music.SR)
    assert spec[freqs > 8000].sum() / spec.sum() < 0.01


def test_keywords_are_big_enough_for_a_phone():
    head = [ln for ln in captions.keyword_header((1080, 1920), "9x16", "en") if ln.startswith("Style: Key_part")][0]
    assert int(head.split(",")[2]) >= 75  # font size in pixels on a 1080×1920 video
    ev = captions.keyword_events([{"text": "agitator", "kind": "part", "start": 0, "end": 2}], "en", 2)
    assert "\\blur" in ev[0][3]
