"""Part 14: stable shadows, no z-fighting, no pops, no flicker, quiet sound, new object tools."""

from pathlib import Path

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


# ---------------------------------------------------------------- Part 3: quiet sound, no loops
def test_sfx_setting_off_subtle_full_and_old_true_false():
    from storyforge.project import EpisodeOptions

    assert EpisodeOptions().sfx == "subtle"
    assert EpisodeOptions.from_dict({"sfx": True}).sfx == "subtle"
    assert EpisodeOptions.from_dict({"sfx": False}).sfx == "off"
    assert EpisodeOptions.from_dict({"sfx": "FULL"}).sfx == "full"


def _engine_and_elevator_plan():
    from storyforge.world import plan as P

    raw = {"areas": [{"id": "a", "setting": "studio"}],
           "objects": [{"id": "e", "asset": "car_engine", "area": "a"}, {"id": "lift1", "asset": "elevator", "area": "a",
                                                                         "pos": [8, 0]}],
           "scenes": [{"camera": {"move": "orbit", "target": "e"},
                       "actions": [{"do": "spin", "target": "e", "at": 0.0}, {"do": "flow", "target": "e", "path": "intake",
                                                                               "at": 0.2}]},
                      {"camera": {"move": "close_up", "target": "lift1.ropes"},
                       "actions": [{"do": "snap", "target": "lift1.ropes", "at": 0.2}]},
                      {"camera": {"move": "close_up", "target": "lift1.safety_brakes"},
                       "actions": [{"do": "clamp", "target": "lift1.safety_brakes", "at": 0.2},
                                   {"do": "alarm", "target": "lift1", "at": 0.1}]}]}
    plan, _ = P.validate(raw, None)
    tl = {"scenes": [{"id": s["id"], "start": 5.0 * k, "dur": 5.0, "voice": 4.5} for k, s in enumerate(plan["scenes"])],
          "words": [], "total": 18.6, "end": {"start": 15.0, "dur": 3.6, "kind": "overview"}}
    return plan, tl


def test_subtle_sounds_are_whooshes_and_one_sound_per_big_moment():
    from storyforge import pipeline

    plan, tl = _engine_and_elevator_plan()
    assert pipeline.sound_events("off", tl, plan, "en", []) == []
    subtle = pipeline.sound_events("subtle", tl, plan, "en", [])
    names = [n for _, n, _ in subtle]
    assert set(names) <= {"low_whoosh", "snap", "clamp", "thud"}  # no hum, pour or alarm loops
    assert names.count("snap") == 1 and names.count("clamp") == 1
    full = pipeline.sound_events("full", tl, plan, "en", [])
    assert "hum" in [n for _, n, _ in full] and all(m <= 2.0 for _, _, m in full)


def test_mixer_never_loops_a_sound_and_keeps_it_short():
    from storyforge.audio import music

    sr = music.SR
    voice = np.zeros(int(10 * sr), np.float32)
    hum = music.make_sfx("hum", 1)  # a 4 s machine sound, asked to last 8 s
    out = music.mix(voice, 10.0, None, 0.0, [(1.0, hum, 0.5, 8.0)])
    env = np.abs(out[:, 0])
    assert float(env[int(3.2 * sr):].max()) < 1e-3  # silent after 2 s (it used to loop for the whole action)
    assert "pulse" not in music.PRESETS["explainer"]["layers"]  # no thumping beat under the voice


def test_new_one_shot_sounds_are_short_soft_and_low():
    from storyforge.audio import music

    for name in ("snap", "clamp", "thud"):
        x = music.make_sfx(name, 2)
        assert len(x) <= 1.0 * music.SR and np.isfinite(x).all()
        spec = np.abs(np.fft.rfft(x[:, 0]))
        f = np.fft.rfftfreq(len(x), 1 / music.SR)
        assert spec[f > 4000].sum() < 0.03 * spec.sum(), name  # lowpassed: nothing sharp


# ---------------------------------------------------------------- Part 4: CC0 models, CAD, exact cuts, sense
def _tiny_gltf(folder):
    """A 2-triangle quad as a real .gltf + .bin + 2x1 palette texture (red left, grey right)."""
    import json
    import struct

    from PIL import Image

    pos = np.array([[0, 0, 0], [1, 0, 0], [1, 2, 0], [0, 2, 0]], np.float32)
    uv = np.array([[0.1, 0.5], [0.1, 0.5], [0.1, 0.5], [0.1, 0.5]], np.float32)
    idx = np.array([0, 1, 2, 0, 2, 3], np.uint16)
    blob = pos.tobytes() + uv.tobytes() + idx.tobytes()
    (folder / "quad.bin").write_bytes(blob)
    Image.fromarray(np.array([[[200, 40, 40], [128, 128, 128]]], np.uint8)).save(folder / "pal.png")
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [{"mesh": 0, "translation": [5, 0, 0]}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
         "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
         "textures": [{"source": 0}], "images": [{"uri": "pal.png"}],
         "buffers": [{"uri": "quad.bin", "byteLength": len(blob)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 32},
                         {"buffer": 0, "byteOffset": 80, "byteLength": 12}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
                       {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2"},
                       {"bufferView": 2, "componentType": 5123, "count": 6, "type": "SCALAR"}]}
    (folder / "quad.gltf").write_text(json.dumps(g))
    assert struct
    return folder / "quad.gltf"


def test_gltf_models_load_in_our_look_and_real_size(tmp_path):
    from storyforge.world import imported

    prims = imported.read_gltf(_tiny_gltf(tmp_path))
    assert len(prims) == 1 and prims[0]["tris"].shape == (2, 3, 3)
    assert abs(float(prims[0]["tris"][..., 0].min()) - 5.0) < 1e-6  # the node's translation is applied
    m = imported.to_model(prims, ("h", 0.9))
    lo, hi = m.bounds()
    assert abs(float(hi[1] - lo[1]) - 0.9) < 1e-4 and abs(float(lo[1])) < 1e-6  # real height, on the floor
    assert abs(float(lo[0] + hi[0])) < 1e-4  # centred
    r, g, b = (int(m.parts[0].color[i:i + 2], 16) for i in (1, 3, 5))
    assert r > g + 60  # the palette texture's red, pulled only a little toward our palette


def test_cc0_objects_fall_back_offline_and_settings_use_boxes(sf_root):
    from storyforge.world import assets, imported

    assert "sofa" in assets.REGISTRY and "cc0" in assets.REGISTRY["stove"].tags
    assert not imported.available("stove")  # tests never download
    m = assets.build("sofa")  # the old box-built sofa stands in
    assert m.parts and m.tris > 0
    assert all(i.size[1] > 0 for i in imported.CATALOG) and all(i.pack in imported.PACKS for i in imported.CATALOG)
    lic = (Path(__file__).resolve().parents[1] / "LICENSES" / "assets.md").read_text()
    assert "CC0" in lic and all(p in lic for p in imported.PACKS)


def test_cad_shapes_build_with_or_without_the_cad_kernel():
    from storyforge.world import cad

    specs = [{"cad": "box", "size": [0.6, 0.85, 0.6], "fillet": 0.03},
             {"cad": "revolve", "profile": [[0.3, 0.0], [0.28, 0.4], [0.18, 0.8]]},
             {"cad": "gear", "module": 0.003, "teeth": 20, "thickness": 0.01},
             {"cad": "sweep", "path": [[0, 0, 0], [0.3, 0, 0], [0.3, 0.3, 0]], "r": 0.02},
             {"cad": "extrude", "poly": [[0, 0], [0.2, 0], [0.2, 0.05], [0.05, 0.05], [0.05, 0.2], [0, 0.2]],
              "size": [0.03]}]
    for s in specs:
        for g in ([cad._build_cad(s)] if cad.available() else []) + [cad.fallback(s)]:
            lo, hi = g.bounds()
            assert g.tris > 0 and np.all(np.isfinite(g.pos)) and float(np.max(hi - lo)) < 1.5, s["cad"]
    box = cad.fallback(specs[0])
    lo, hi = box.bounds()
    assert np.allclose(hi - lo, [0.6, 0.85, 0.6], atol=1e-4)


def test_cad_parts_in_a_recipe_are_smooth_and_cached(sf_root):
    from storyforge.world import builder, cad

    recipe = {"name": "test_drum", "parts": [
        {"name": "cabinet", "cad": "box", "size": [0.6, 0.85, 0.6], "pos": [0, 0.425, 0], "fillet": 0.02, "shell": True},
        {"name": "drum", "cad": "cylinder", "size": [0.22, 0.4], "axis": "z", "pos": [0, 0.45, 0], "color": "#c8cdd2"}]}
    m = builder.model_from_recipe(recipe)
    drum = next(p for p in m.parts if p.name == "drum")
    assert drum.geo.nrm is not None or not cad.available()  # CAD parts carry smooth normals
    lo, hi = drum.geo.bounds()
    assert abs(float(hi[2] - lo[2]) - 0.4) < 0.02  # along z, as asked


def test_exact_cut_gives_each_blade_its_own_small_face():
    from storyforge.world import cad
    from storyforge.world import mesh as M

    if not cad.manifold_available():
        return
    blades = M.merge(*[M.xf(M.box(0.3, 0.04, 0.01), (0.2, 0, 0), (0, 0, 360.0 * k / 8)) for k in range(8)])
    kept, caps, loose = cad.cut(blades.pos, (0, 0, 1), 0.0)
    assert len(loose) == 0 and len(kept) and len(caps)
    cap_area = float(np.linalg.norm(np.cross(caps[:, 1] - caps[:, 0], caps[:, 2] - caps[:, 0]), axis=1).sum() / 2)
    assert cap_area < 8 * 0.3 * 0.04 * 1.05  # the blades' own sections, not the convex 'comb' around them
    shell = M.cylinder(0.2, 0.6, 16, base=False)
    _, solid_cap, _ = cad.cut(shell.pos, (1, 0, 0), 0.0)
    _, rim_cap, _ = cad.cut(shell.pos, (1, 0, 0), 0.0, hollow=0.01)
    area = lambda t: float(np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() / 2)  # noqa: E731
    assert area(rim_cap) < 0.3 * area(solid_cap)  # a hollow capsule shows a thin rim, not a big slab


def test_sense_check_finds_floating_parts_wrong_axes_and_supports_them():
    from storyforge.world import mesh as M
    from storyforge.world import sense

    m = M.Model()
    m.add("cabinet", M.xf(M.box(0.6, 0.85, 0.6), (0, 0.425, 0)), shell=True)
    m.add("drum", M.xf(M.cylinder(0.2, 0.3, 16, base=False), (0, 0.45, 0), (90, 0, 0)),
          motion={"type": "spin", "axis": "z"}, pivot=(0, 0.45, 0))
    m.add("pulley", M.xf(M.cylinder(0.08, 0.02, 16, base=False), (0.1, 0.45, -0.25), (90, 0, 0)),
          motion={"type": "spin", "axis": "z"}, pivot=(0.1, 0.45, -0.25))
    bp = {"size_m": [0.6, 0.85, 0.6], "parts": [{"name": "drum", "moves": "spins", "axis": "z"},
                                                {"name": "door", "faces": "front"}],
          "shared_axes": [["drum", "pulley"]]}
    problems = sense.check(m, bp)
    text = " | ".join(problems)
    assert "float" in text and "door is missing" in text and "not on the drum's axis" in text
    notes = sense.add_supports(m)
    assert notes and not sense.floating_parts(m)  # every floating part now stands on a support


def test_no_closed_part_is_inside_out_and_boxes_are_bevelled():
    from storyforge.world import assets

    for name in ("car_engine", "elevator", "house", "fridge", "tractor", "generator"):
        m = assets.build(name)
        for p in m.parts:
            if p.geo.nrm is not None or not p.geo.closed():
                continue
            t = p.geo.pos.reshape(-1, 3, 3).astype(np.float64)
            vol = np.einsum("ij,ij->i", np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), t[:, 0]).sum() / 6
            assert vol >= -1e-9, (name, p.name)  # faces point out (a cut would show inside-out faces dark)
    raw = assets.REGISTRY["house"].fn()
    assert assets.build("house").tris > raw.tris  # bevelled edges
    assert any(p.geo.nrm is not None for p in assets.build("tank").parts)  # round parts are smooth


def test_a_part_inside_a_machine_is_filmed_from_its_clear_side():
    scenes = [{"camera": {"move": "orbit", "target": "w1"}} for _ in range(5)]
    scenes.append({"camera": {"move": "close_up", "target": "w1.motor"}})  # shot 6: the plain angle is the front
    w = _world(scenes, [{"id": "w1", "asset": "washing_machine", "area": "a"}], [{"id": "a", "setting": "laundry"}])
    assert w._cam_part(5) == "motor"
    assert 10 <= w._cams[5]["az"] <= 95  # not through the drum and the pump from the front, and never behind the wall


def test_labels_stay_above_the_bottom_subtitles():
    from storyforge.world.scene import label_floor

    W, H = 720, 1280
    assert H - label_floor(W, H) <= H - 0.215 * H - 0.06 * W  # above the subtitle line (captions.two_layer_header)
    w = _world([{"camera": {"move": "close_up", "target": "w1.control_panel"},  # the feet are far below the picture
                 "labels": [{"target": "w1.feet", "text": "Feet", "kind": "part", "at": 0.0}]}],
               [{"id": "w1", "asset": "washing_machine", "area": "a"}])
    tex = lambda text, kind: (np.zeros((14, 60, 4), np.uint8), text)  # noqa: E731
    W, H = w.size
    ys = [lb.y for T in (1.0, 2.5, 4.0) for lb in w.frame(T, tex).labels]
    assert ys and all(y <= H - label_floor(W, H) + 1e-6 for y in ys)
    assert max(ys) > H - label_floor(W, H) - 1  # it was pushed up to the limit (not lower, over the subtitles)
