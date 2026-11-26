"""Round 2 (mega prompt): busy Gemini, real part names, lengths, looks, hero / macro shots, rope snap, two-layer
captions, the StoryForge Videos folder, the plan cheatsheet and the CLI."""
import json

import numpy as np
import pytest

from storyforge import captions, formats, paste, project
from storyforge.messages import Reporter


# ---------------------------------------------------------------- Part 1
def test_explainers_never_get_a_part_x_card_and_never_sad_music():
    assert not formats.end_card("how_it_works", True) and not formats.end_card("documentary", True)
    assert formats.end_card("story", False) and formats.end_card("story", True)
    assert formats.music_mood("how_it_works", "auto", "sad") == "explainer"
    assert formats.music_mood("how_it_works", "sad") == "explainer"  # even a stale "sad" setting
    assert formats.music_mood("story", "auto", "sad") == "sad"


def test_unknown_mounts_snap_to_real_parts_not_the_ground():
    from storyforge.world import plan as P

    raw = {"areas": [{"id": "a"}], "objects": [
        {"id": "elevator1", "asset": "elevator", "area": "a"},
        {"id": "doors", "asset": "elevator_doors", "mount": "elevator1.doors", "area": "a"},
        {"id": "box1", "asset": "crate", "mount": "elevator1.safety_brake", "area": "a"}],
        "scenes": [{"camera": {"move": "close_up", "target": "doors"},
                    "actions": [{"do": "open", "target": "doors", "at": 0.2}]},
                   {"camera": {"move": "close_up", "target": "elevator1.cables"}}]}
    p, fixes = P.validate(raw, ["the doors open", "the cables hold it"])
    ids = {o["id"]: o for o in p["objects"]}
    assert "doors" not in ids  # the elevator already HAS doors: the stand-in object is folded into its real part
    assert p["scenes"][0]["camera"] == {"move": "close_up", "target": "elevator1", "part": "car_door"}
    assert p["scenes"][0]["actions"][0]["target"] == "elevator1.car_door"
    assert ids["box1"]["mount"] == "elevator1.safety_brakes"  # snapped, never on the ground
    assert p["scenes"][1]["camera"]["part"] == "ropes"


def test_the_catalog_lists_exact_part_names():
    from storyforge.world import assets

    cat = assets.catalog()
    line = next(x for x in cat.split("\n") if x.startswith("- elevator:"))
    assert "[parts:" in line and "safety_brakes" in line and "motor_shaft" in line and "passenger" in line


def test_same_topic_replaces_its_episode(sf_root):
    from storyforge import pipeline

    s = project.Series.create("How it works")
    ep = s.episode(1)
    ep.save_options(project.EpisodeOptions(idea="How an elevator works"))
    assert pipeline.same_topic_episode(s, project.EpisodeOptions(idea="how an ELEVATOR works"), "") == 1
    assert pipeline.same_topic_episode(s, project.EpisodeOptions(idea="how a fridge works"), "") is None


def test_noisy_library_warnings_are_hidden(capsys):
    import logging
    import warnings

    from storyforge import config

    config.quiet_warnings()
    logging.getLogger("phonemizer").warning("words count mismatch on 100.0% of the lines (1/1)")
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("default")
        config.quiet_warnings()
        warnings.warn("The secret `HF_TOKEN` does not exist in your Colab secrets.", UserWarning)
    assert not got and "mismatch" not in capsys.readouterr().err


# ---------------------------------------------------------------- Parts 3-5
def test_lengths_speed_and_pauses():
    assert paste.target_seconds("short") == 80 and paste.target_seconds("short", 180) == 180
    assert paste.target_seconds("short", 999) == 180 and paste.target_seconds("long", 540) == 540
    assert paste.narrator_speed("how_it_works") == 1.0 and paste.narrator_speed("story") == 1.1
    assert paste.count_words("It doesn't. [PAUSE] It lets in air.") == 6
    parsed = paste.parse_lines("[SCENE] a\nNARRATOR: What lifts an elevator?\n[SCENE] b\nNARRATOR: Ropes.\n"
                               "[SCENE] c\nNARRATOR: They go up over a wheel and down to a counterweight.\n"
                               "[SCENE] d\nNARRATOR: The end of this story is here now.")
    scenes = paste.to_scenes(parsed)
    assert len(scenes) == 3 and "Ropes." in " ".join(ln["text"] for ln in scenes[1]["lines"])  # tiny shots merge


def test_pause_marks_become_real_pauses(offline):
    from storyforge import pipeline

    from storyforge import script

    series = project.Series.create("P")
    ep = series.episode(1)
    opts = project.EpisodeOptions()
    script.script_from_text(series, ep, opts, "NARRATOR: It doesn't. [PAUSE] It lets in air.", Reporter(echo=False))
    pipe = pipeline.Pipeline(series, ep, Reporter(echo=False), opts)
    parts = pipe.scene_speech({"lines": [{"speaker": "NARRATOR", "text": "It doesn't. [PAUSE] It lets in air."}],
                               "narration": ""}, "en")
    assert [t for t, _, _ in parts] == ["It doesn't.", "It lets in air."] and parts[1][2] == paste.PAUSE_SECONDS


def test_two_layer_captions():
    head = captions.two_layer_header((1080, 1920), "9x16", "en")
    assert any(h.startswith("Style: Sub,") for h in head) and any(h.startswith("Style: Key_wow,") for h in head)
    words = [{"w": w, "s": k * 0.3, "e": k * 0.3 + 0.25} for k, w in enumerate("It lets in more air.".split())]
    ev = captions.subtitle_events(words, "9x16", "en", 3.0)
    assert all(e[2] == "Sub" for e in ev) and all(1 <= len(e[3].split("}")[-1].split()) <= 3 for e in ev)


def test_one_wow_keyword_per_shot_and_new_fields():
    from storyforge.world import plan as P

    raw = {"areas": [{"id": "a", "look": "outdoor"}], "objects": [{"id": "e", "asset": "car_engine", "area": "a"}],
           "scenes": [{"camera": {"move": "hero", "target": "e.piston"}, "look": "macro", "cut": True,
                       "keywords": [{"text": "piston", "kind": "part"}, {"text": "MORE AIR", "kind": "wow"}]}]}
    p, _ = P.validate(raw, ["x"])
    sc = p["scenes"][0]
    assert sc["keywords"] == [{"text": "MORE AIR", "kind": "wow"}] and sc["look"] == "macro_dark" and sc["cut"]
    assert p["areas"][0]["look"] == "outdoor_day" and sc["camera"]["move"] == "hero"
    assert P.validate(p, ["x"])[0] == p  # still idempotent


# ---------------------------------------------------------------- Parts 2, 6, 7 in the world
def _world(scenes, objects, areas=None):
    from storyforge.world import plan as P
    from storyforge.world.scene import World, freeze_layout

    raw = {"areas": areas or [{"id": "a", "setting": "studio"}], "objects": objects, "scenes": scenes}
    plan, _ = P.validate(raw, None)
    freeze_layout(plan)
    tl = {"scenes": [{"id": s["id"], "start": 5.0 * k, "dur": 5.0, "voice": 4.5} for k, s in enumerate(plan["scenes"])],
          "words": [], "total": 5.0 * len(plan["scenes"]) + 3.6,
          "end": {"start": 5.0 * len(plan["scenes"]), "dur": 3.6, "kind": "overview"}}
    return World(plan, tl, (270, 480))


def test_hero_shot_shows_one_part_cut_with_pink_faces_on_a_light_studio():
    from storyforge.world.scene import HERO_COLOR

    w = _world([{"camera": {"move": "orbit", "target": "e"}},
                {"camera": {"move": "hero", "target": "e.piston"}}],
               [{"id": "e", "asset": "car_engine", "area": "a"}, {"id": "c", "asset": "crate", "area": "a", "pos": [3, 0]}])
    assert w._looks[1][0] == "studio_light" and w._cams[1]["cut"]  # a clean cut into the hero shot
    fr = w.frame(7.5)
    names = {d.key.split("|")[0] for d in fr.draws}
    assert all(not k.startswith("c") or k.startswith("e") for k in names) or len(fr.draws) < 20
    assert fr.dyn and all(np.allclose(rgb, [int(HERO_COLOR[i:i + 2], 16) / 255 for i in (1, 3, 5)])
                          for _, rgb, _ in fr.dyn)
    lo, hi = w._cams[1]["lo"], w._cams[1]["hi"]
    assert float(np.max(hi - lo)) < 0.4  # one cylinder (about 10 cm), not the whole 0.6 m engine


def test_rope_snap_whips_and_brakes_spark():
    w = _world([{"camera": {"move": "close_up", "target": "lift1.ropes"},
                 "actions": [{"do": "snap", "target": "lift1.ropes", "at": 0.1}]}],
               [{"id": "lift1", "asset": "elevator", "area": "a"}])
    inst = w.groups["lift1"][0]
    st = w.state(inst, 3.0)
    assert st["snaps"] and st["sag"] > 0.4
    parts = w.particles(0, 1.5)
    assert parts is not None and len(parts) > 40  # sparks at the safety brakes


def test_outdoor_settings_are_sunny_and_comparisons_frame_the_whole_table():
    w = _world([{"camera": {"move": "orbit", "target": "car1"}}, {"camera": {"move": "push_in", "target": "b"},
                                                                  "cut": True}],
               [{"id": "car1", "asset": "car", "area": "street"}, {"id": "b", "asset": "bottle", "area": "t"},
                {"id": "g", "asset": "shot_glass", "area": "t", "pos": [0.2, 0]}],
               [{"id": "street", "setting": "street"}, {"id": "t", "setting": "table"}])
    assert w._looks[0][0] == "outdoor_day" and w._looks[0][1]["sky_mode"] == 1
    assert w._looks[1][0] == "studio_light" and set(w._focus[1]) == {"b", "g"}


def test_new_renderer_effects_draw(needs_gl):
    from storyforge.world import gl

    w = _world([{"camera": {"move": "macro", "target": "e.spark"}, "actions": [{"do": "glow", "target": "e.spark"}]}],
               [{"id": "e", "asset": "car_engine", "area": "a"}])
    r = gl.Renderer((90, 160), msaa=0, shadow_size=512)
    try:
        w.upload(r)
        fr = w.frame(2.5)
        assert fr.dof > 0 and fr.style["grade"] == "dark"
        img = r.render(fr)
        assert img.shape == (160, 90, 3) and img.mean() < 120  # a dark macro shot
    finally:
        r.release()


# ---------------------------------------------------------------- Parts 8-9
def test_videos_folder_names_captions_and_posted(sf_root, tmp_path):
    from storyforge import videos

    v = tmp_path / "x.mp4"
    v.write_bytes(b"video")
    th = tmp_path / "t.jpg"
    th.write_bytes(b"jpg")
    meta = {"titles": ["How an elevator works"], "description": "Ropes and a counterweight.",
            "hashtags": {"youtube": ["#shorts"], "tiktok": ["#elevator"], "instagram": ["#howitworks"]}}
    out = videos.add(v, "How an elevator works?", "9x16", "en", meta, th)
    assert out.parent.name == "StoryForge Videos" and out.name.endswith("How an elevator works (Short 9x16).mp4")
    txt = out.with_suffix(".txt").read_text(encoding="utf-8")
    assert "TikTok" in txt and "Instagram" in txt and "Facebook" in txt and "#elevator" in txt
    assert out.with_suffix(".jpg").exists()
    moved = videos.mark_posted(out)
    assert moved.exists() and moved.parent.name == "Posted" and not out.exists()


def test_cheatsheet_is_short_and_has_real_part_names(tmp_path):
    from storyforge.world import cheatsheet

    text = cheatsheet.write(tmp_path / "c.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 150 and "safety_brakes" in text and "`hero`" in text
    plan = json.loads(text.split("```json")[1].split("```")[0])
    from storyforge.world import plan as P

    _, fixes = P.validate(plan, ["a", "b", "c"])
    assert not [f for f in fixes if "not a part" in f or "unknown" in f]


def test_cli_parses_and_needs_a_script(tmp_path, capsys):
    from storyforge import make

    with pytest.raises(SystemExit):
        make.main([])
    assert "--script" in capsys.readouterr().err
