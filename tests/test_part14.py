"""Part 14: stable shadows, no z-fighting, no pops, no flicker, quiet sound, new object tools."""

import numpy as np

from test_round2 import _world


# ---------------------------------------------------------------- Part 1: shadows that don't swim or speckle
def test_shadow_map_is_snapped_to_texels_and_sized_in_steps():
    from storyforge.world import gl

    sun = (-0.45, 0.8, 0.4)
    m1, texel, _ = gl.shadow_box(sun, (1.0, 0.5, 2.0), 3.0, 2048)
    m2, texel2, _ = gl.shadow_box(sun, (1.0 + texel * 0.3, 0.5, 2.0 - texel * 0.2), 3.02, 2048)  # the camera moved a bit
    assert texel == texel2  # the size comes in steps: a slowly changing subject keeps the same texels
    p = np.array([0.7, 0.3, 1.6, 1.0])
    uv1 = (m1 @ p)[:2] * 0.5 + 0.5
    uv2 = (m2 @ p)[:2] * 0.5 + 0.5
    shift = np.abs(uv1 - uv2) * 2048
    assert np.allclose(shift, np.round(shift), atol=1e-3)  # moved by whole texels only: no shimmer


def test_coplanar_faces_of_two_parts_are_pulled_apart():
    from storyforge.world import mesh as M

    m = M.Model()
    m.add("panel", M.xf(M.box(2.0, 1.0, 0.06), (0, 0.5, 0.86)), "#d9534f")
    m.add("cap", M.xf(M.cylinder(0.33, 0.22, 16, base=False), (0.3, 0.4, 0.78), (90, 0, 0)), "#222222")  # its end is flush
    notes = M.resolve_coplanar(m)
    assert notes and notes[0].startswith("cap")
    assert m.parts[1].geo.bounds()[1][2] > m.parts[0].geo.bounds()[1][2] + 1e-4  # in front now, not fighting
    assert not M._coplanar_pass(m)


def test_no_object_in_the_library_has_z_fighting_faces():
    from storyforge.world import assets
    from storyforge.world import mesh as M

    bad = [n for n in ("car", "car_engine", "elevator", "fridge", "toilet", "street_road", "tractor", "barn")
           if M._coplanar_pass(assets.build(n))]
    assert not bad


def test_hidden_panels_are_chosen_per_shot_and_fade_in_flights():
    w = _world([{"camera": {"move": "orbit", "target": "car1"}},
                {"camera": {"move": "push_in", "target": "eng1"}}],
               [{"id": "car1", "asset": "car", "area": "a"}, {"id": "eng1", "asset": "car_engine", "area": "a",
                                                               "mount": "car1.engine_bay"}])
    vis = w._shot_vis(1)
    assert "car1" in vis and vis["car1"][1]  # the car's panels in front of the engine are left out in shot 2

    def car_panels(T):
        fr = w.frame(T)
        return {d.key: round(d.opacity, 3) for d in fr.draws if d.key.startswith("car:")}

    late = [car_panels(5.0 + w.flight(1) + k * 0.4) for k in range(5)]
    assert all(x == late[0] for x in late)  # after the flight: the same parts every frame (no pop)
    mid = car_panels(5.0 + w.flight(1) * 0.5)
    assert any(0.05 < o < 0.95 for o in mid.values())  # during the flight they fade


def test_sun_and_shadow_box_stay_fixed_within_a_shot():
    w = _world([{"camera": {"move": "orbit", "target": "e"}}], [{"id": "e", "asset": "car_engine", "area": "a"}])
    a, b = w.frame(0.5), w.frame(4.5)
    assert a.eye != b.eye  # the camera moves …
    assert a.sun == b.sun and a.focus == b.focus and a.focus_radius == b.focus_radius  # … the light does not
    assert a.focus_radius < 3.0  # fitted to a 0.6 m engine (was at least 8 m: blurry stair steps)


def test_flat_surfaces_render_without_speckle(needs_gl):
    from storyforge.world import gl
    from storyforge.world import mesh as M

    r = gl.Renderer((240, 360), msaa=4, shadow_size=1024, shadow_taps=3)
    r.upload("slab", M.xf(M.box(3.0, 0.05, 3.0), (0, 0.4, 0), (8, 0, 0)))
    r.upload("box", M.xf(M.box(0.4, 0.4, 0.4), (0.5, 0.65, 0.2)))
    draws = [gl.Draw("slab", np.eye(4, dtype=np.float32), (0.85, 0.35, 0.3), shine=0.55),
             gl.Draw("box", np.eye(4, dtype=np.float32), (0.3, 0.5, 0.8))]
    imgs = []
    for k in range(2):  # the camera moves a little between two frames
        fr = gl.Frame(eye=(0.3 + 0.01 * k, 1.8, 2.8), target=(0, 0.4, 0), fov=40, draws=draws, focus=(0, 0.4, 0),
                      focus_radius=1.8, sun=(-0.9, 0.25, 0.3))
        imgs.append(r.render(fr).astype(np.float32).mean(-1))
    r.release()
    a = imgs[0][200:330, 20:120]  # the lit slab, away from the box and its shadow
    hf = np.abs(a[1:-1, 1:-1] - (a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]) / 4)
    assert float(hf.mean()) < 0.6  # no grain, no dither, no acne


# ---------------------------------------------------------------- Part 2: no flashes, pops or strobing
def test_jump_detector_finds_flashes_and_ignores_cuts_and_fades():
    from storyforge.world import checker

    n = 60
    L = np.full((n, 10), 0.5, np.float32)
    L[:, 0] = np.linspace(0.5, 0.8, n)  # a slow fade: fine
    L[20:23, 4] = 0.9  # a flash in one ninth of the picture
    L[40:, :] = 0.2  # a hard cut at frame 40
    held = L.copy()
    found = checker.brightness_jumps(L, 30, cuts=[40 / 30], held=held)
    kinds = {(round(j["t"] * 30), j["kind"]) for j in found}
    assert (20, "pop") in kinds and not any(k in (39, 40, 41) for k, _ in kinds)
    L2 = L.copy()
    L2[50, 0] = 0.45  # the whole picture jumps 125 % → 20 %
    assert any(j["kind"] == "jump" for j in checker.brightness_jumps(L2, 30, cuts=[40 / 30]))
    strobe = np.full((60, 10), 0.5, np.float32)
    strobe[::2, 3] = 0.6
    assert any(j["kind"] == "strobe" for j in checker.brightness_jumps(strobe, 30, cuts=[]))


def test_glows_alarms_and_sparks_pulse_slowly_and_fade_in():
    from storyforge.world import motion
    from storyforge.world.scene import slow_pulse, soft_ramp

    vals = [slow_pulse(t, 5.0) for t in np.arange(0, 2, 1 / 60)]  # asked for 5 Hz: capped at 2 per second
    peaks = sum(1 for k in range(1, len(vals) - 1) if vals[k] > vals[k - 1] and vals[k] >= vals[k + 1])
    assert peaks <= 4 and vals[0] == 0.0
    assert soft_ramp(0.0, 10.0, float("inf")) == 0.0 and soft_ramp(1.0, 11.0, float("inf")) == 1.0
    assert soft_ramp(5.0, 10.2, 10.0) < 1.0  # fades out after its shot instead of switching off
    from storyforge.world import assets

    eng = assets.build("car_engine")
    spark = next(p for p in eng.parts if p.name == "spark1")
    glows = [motion.evaluate(spark, {"spin": th, "spin_on": True}, 0.0)[1] for th in np.linspace(0, 8 * np.pi, 400)]
    steps = np.abs(np.diff(glows))
    assert max(glows) <= 1.2 and float(steps.max()) < 0.12  # a soft bell, no one-frame flash
    gas = next(p for p in eng.parts if p.name == "gas1")
    cols = [motion.evaluate(gas, {"spin": th, "spin_on": True}, 0.0) for th in np.linspace(0, 8 * np.pi, 800)]
    dc = max(float(np.max(np.abs(np.subtract(a[2], b[2])))) for a, b in zip(cols, cols[1:]))
    assert dc < 0.08  # the stroke colours blend into each other (the bang no longer snaps on)


def test_no_white_flash_in_the_renderer():
    from storyforge.world import gl

    assert "flash" not in gl.Frame.__dataclass_fields__ and "u_flash" not in gl.FINAL_FRAG


def test_brightness_has_no_jumps_except_hard_cuts(needs_gl):
    """The whole chain in a small world: spinning engine sparks, a glow, an alarm, a cutaway, a rope snap and the
    brakes, camera flights between shots. Every frame is checked with the camera moving and held still."""
    from storyforge.world import checker, gl

    w = _world([{"camera": {"move": "orbit", "target": "e"},
                 "actions": [{"do": "spin", "target": "e", "at": 0.0, "speed": 0.5},
                             {"do": "cutaway", "target": "e", "at": 0.2, "keep": True}]},
                {"camera": {"move": "close_up", "target": "e"},
                 "actions": [{"do": "glow", "target": "e", "at": 0.1}, {"do": "alarm", "target": "e", "at": 0.4}]},
                {"camera": {"move": "close_up", "target": "lift1.ropes"},
                 "actions": [{"do": "snap", "target": "lift1.ropes", "at": 0.2}]}],
               [{"id": "e", "asset": "car_engine", "area": "a"}, {"id": "lift1", "asset": "elevator", "area": "a",
                                                                  "pos": [8, 0]}])
    r = gl.Renderer((54, 96), msaa=4, shadow_size=512, shadow_taps=3)
    w.upload(r)
    L, H = checker.scan_video(w, r, fps=30.0, t0=0.0, t1=15.0)
    r.release()
    problems = checker.brightness_jumps(L, 30.0, checker.cut_times(w), held=H)
    assert not problems, problems[:5]
