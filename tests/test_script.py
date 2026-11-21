import json

import pytest

from storyforge import llm, net, project, script
from storyforge.messages import Reporter


def test_extract_json_variants():
    assert llm.extract_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert llm.extract_json('Sure! Here it is: {"a": "x}y", "b": [1,2]} hope it helps') == {"a": "x}y", "b": [1, 2]}
    assert llm.extract_json("<think>hmm {no}</think>{\u201ca\u201d: 2}") == {"a": 2}
    assert llm.extract_json('{"a": {"b": 1}') == {"a": {"b": 1}}  # cut-off reply gets closed
    with pytest.raises(ValueError):
        llm.extract_json("no json here")


def test_rank_models_prefers_flash_lite_and_free():
    ids = ["models/gemini-2.5-pro", "models/gemini-3.5-flash-lite", "models/gemini-3.1-flash-lite",
           "models/gemini-3.8-flash", "models/gemini-2.5-flash-image", "models/embedding-001"]
    assert llm.rank_models("gemini", ids)[:3] == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
    assert "gemini-2.5-pro" not in llm.rank_models("gemini", ids)
    assert llm.rank_models("openrouter", ["a/qwen-x", "a/qwen-y:free"]) == ["a/qwen-y:free"]


def test_no_keys_means_pollinations_only(sf_root, monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert [n for n, _ in llm.providers()] == ["Pollinations"]
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert [n for n, _ in llm.providers()] == ["Groq", "Pollinations"]


def fake_reply(n=4):
    return {
        "title": "The Signal",
        "style": "neon noir comic art",
        "characters": [{"name": "Mira", "description": "a woman with silver hair", "gender": "female"}],
        "scenes": [
            {"narration": f"Line {i}.", "visual": f"Picture {i}", "characters": ["Mira"] + (["Leo"] if i == 2 else []),
             "camera": "Push In" if i < 3 else "zoom", "effects": "dust, snow, lava", "sfx": ["whoosh"],
             "mood": "TENSE", "hero": i == 2}
            for i in range(1, n + 1)
        ],
        "cliffhanger": "Who sent it?",
        "summary": "Mira found a signal.",
        "thumbnail_text": "WHO SENT IT",
        "music_mood": "mysterious",
    }


def use_fake_ai(monkeypatch, replies):
    """Make every AI call return the next reply in the list."""
    replies = list(replies)

    def fake(messages, json_mode, temperature, max_tokens):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)

    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])


def test_write_script_with_ai(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, [fake_reply()])
    series = project.Series.create("Signal")
    ep = series.episode(1)
    opts = project.EpisodeOptions(idea="A radio picks up a voice from the future", scene_count=4, hero_count=2)
    s = script.write_script(series, ep, opts, Reporter(echo=False))
    assert [x["id"] for x in s["scenes"]] == ["s01", "s02", "s03", "s04"]
    assert s["scenes"][0]["kind"] == "hook" and s["scenes"][-1]["kind"] == "cliffhanger"
    cams = [x["camera"] for x in s["scenes"]]
    assert all(a != b for a, b in zip(cams, cams[1:])), cams  # never twice in a row
    assert s["scenes"][0]["effects"] == ["dust", "snow"] and s["scenes"][0]["mood"] == "tense"
    assert sum(x["hero"] for x in s["scenes"]) == 2 and s["scenes"][1]["hero"]
    assert series.character("Mira")["description"] == "a woman with silver hair"
    assert series.character("Leo") is not None  # used in a scene, added with a default look
    assert series.data["style"] == "neon noir comic art"
    assert ep.script_md_path.exists() and project.read_json(ep.script_path)["title"] == "The Signal"


def test_write_script_falls_back_to_template(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, [net.ServiceError("HTTP 503")])
    series = project.Series.create("Fallback")
    rep = Reporter(echo=False)
    s = script.write_script(series, series.episode(1), project.EpisodeOptions(idea="A cat finds a door.", scene_count=5), rep)
    assert len(s["scenes"]) == 5 and s["provider"] == "Template (no AI)"
    assert s["scenes"][0]["narration"] == "A cat finds a door."
    assert "starter script" in rep.text()


def test_bad_json_gets_one_repair(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, ["oops not json", fake_reply(3)])
    series = project.Series.create("Repair")
    s = script.write_script(series, series.episode(1), project.EpisodeOptions(scene_count=3), Reporter(echo=False))
    assert s["provider"] == "FakeAI" and len(s["scenes"]) == 3


def test_markdown_round_trip_and_edits(sf_root):
    opts = project.EpisodeOptions(scene_count=4)
    s = script.normalize_script(fake_reply(), opts)
    md = script.to_markdown(s)
    assert "## Scene 1 [s01] · HOOK" in md and "NARRATOR: Line 1." in md
    back = script.from_markdown(md, s, opts)
    assert [x["narration"] for x in back["scenes"]] == [x["narration"] for x in s["scenes"]]
    assert [x["hero"] for x in back["scenes"]] == [x["hero"] for x in s["scenes"]]
    # user edits: change a line (multi-line), delete scene 2, add a new scene at the end
    edited = md.replace("NARRATOR: Line 1.", "NARRATOR: A brand new hook\nthat continues here.\nMIRA: Who is there?")
    start = edited.index("## Scene 2")
    edited = edited[:start] + edited[edited.index("## Scene 3"):]
    edited = edited.replace("## Cliffhanger", "## Scene\nNarration: Extra ending.\nCamera: tilt up\n\n## Cliffhanger")
    new = script.from_markdown(edited, s, opts)
    assert new["scenes"][0]["narration"] == "A brand new hook that continues here. Who is there?"
    assert [ln["speaker"] for ln in new["scenes"][0]["lines"]] == ["NARRATOR", "MIRA"]
    assert [x["id"] for x in new["scenes"]] == ["s01", "s03", "s04", "s05"]  # ids stay with their scenes
    assert new["scenes"][-1]["kind"] == "cliffhanger" and new["scenes"][-1]["camera"] == "tilt_up"
    assert new["scenes"][1]["visual"] == "Picture 3"  # unchanged fields kept
    with pytest.raises(Exception):
        script.from_markdown("# Only a title", s, opts)


def test_hero_count_respected():
    scenes = script.normalize_scenes([{"narration": f"x{i}", "mood": "action" if i == 3 else "calm"} for i in range(6)])
    for n in (0, 1, 2, 3):
        script.apply_hero_count(scenes, n)
        assert sum(s["hero"] for s in scenes) == n
    for s in scenes:
        s["hero"] = False
    script.apply_hero_count(scenes, 2)
    assert scenes[0]["hero"] and scenes[-1]["hero"]  # hook + cliffhanger first
    scenes[2]["hero"] = True  # the user's own pick is kept first
    script.apply_hero_count(scenes, 1)
    assert scenes[0]["hero"] and sum(s["hero"] for s in scenes) == 1


def test_farsi_translation(sf_root, monkeypatch):
    series = project.Series.create("FA")
    ep = series.episode(1)
    opts = project.EpisodeOptions(scene_count=3, languages=["en", "fa"])
    fa = {"title": "سیگنال", "thumbnail_text": "کی فرستاد؟", "cliffhanger": "چه کسی؟",
          "lines": [{"id": "s01", "text": "خط یک."}, {"id": "s02", "text": "خط دو."}, {"id": "s03", "text": "خط سه."}],
          "names": {"Mira": "میرا"}}
    use_fake_ai(monkeypatch, [fake_reply(3), fa])
    s = script.write_script(series, ep, opts, Reporter(echo=False))
    assert s["scenes"][1]["narration_fa"] == "خط دو." and s["title_fa"] == "سیگنال"
    assert series.character("Mira")["name_fa"] == "میرا"
    # only changed lines are translated again
    s["scenes"][2]["narration"] = "Changed."
    use_fake_ai(monkeypatch, [{"lines": [{"id": "s03", "text": "تغییر کرد."}]}])
    assert script.translate_script(series, ep, s, Reporter(echo=False))
    assert s["scenes"][2]["narration_fa"] == "تغییر کرد." and s["scenes"][0]["narration_fa"] == "خط یک."
    assert "Farsi: خط یک." in ep.script_md_path.read_text(encoding="utf-8")
    assert script.from_markdown(ep.script_md_path.read_text(encoding="utf-8"), s, opts)["scenes"][0]["narration_fa"] == "خط یک."


def test_prompt_includes_series_memory(sf_root):
    series = project.Series.create("Memory")
    from storyforge.characters import add_character
    add_character(series, "Mira", "silver hair, red coat")
    series.remember_episode(1, title="Pilot", summary="Mira found the radio.", cliffhanger="The radio spoke her name.")
    p = script.build_user_prompt("next", series, 2, project.EpisodeOptions(scene_count=8))
    assert "silver hair, red coat" in p and "The radio spoke her name." in p and "exactly 8 scenes" in p
