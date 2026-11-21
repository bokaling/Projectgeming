"""Paste-script mode: reading your script and planning varied scenes."""
import json

from storyforge import characters, llm, net, paste, planner, project, script
from storyforge.messages import Reporter

SCRIPT = """[TITLE] The Night Radio
[SCENE] a yellow taxi parked in the rain at 3 a.m., neon signs
NARRATOR: The radio crackled at exactly three in the morning.
MIRA: Who's there?
[SCENE] the dashboard radio glowing red
NARRATOR: A voice answered with her own name.
Then it went silent.
"""

LONG_PLAIN = " ".join(f"Sentence number {i} tells a small part of the story with several words." for i in range(40))


def test_parse_tags_speakers_and_title():
    p = paste.parse_lines(SCRIPT)
    assert p["title"] == "The Night Radio" and p["language"] == "en" and p["speakers"] == ["MIRA"]
    b = p["blocks"]
    assert len(b) == 2 and b[0]["visual"].startswith("a yellow taxi")
    assert [ln["speaker"] for ln in b[0]["lines"]] == ["NARRATOR", "MIRA"]
    assert b[1]["lines"][-1] == {"speaker": "NARRATOR", "text": "Then it went silent.", "para": 0}


def test_plain_text_is_narration_and_not_fooled_by_colons():
    p = paste.parse_lines("Note: the radio was old.\nIt still worked.")
    assert all(ln["speaker"] == "NARRATOR" for b in p["blocks"] for ln in b["lines"])
    assert p["blocks"][0]["lines"][0]["text"] == "Note: the radio was old."


def test_farsi_script_and_narrator_word():
    p = paste.parse_lines("[TITLE] رادیو\nراوی: ساعت سه صبح رادیو روشن شد.\nمیرا: کی اونجاست؟")
    assert p["language"] == "fa" and p["speakers"] == ["میرا"]
    assert p["blocks"][0]["lines"][0]["speaker"] == "NARRATOR"


def test_batch_split():
    parts = paste.split_scripts("[TITLE] One\nA.\n=====\n[TITLE] Two\nB.\n\n========\n[TITLE] Three\nC.")
    assert [paste.parse_lines(t)["title"] for t in parts] == ["One", "Two", "Three"]


def test_auto_split_without_scene_tags():
    short = paste.to_scenes(paste.parse_lines(LONG_PLAIN), "short")
    long_ = paste.to_scenes(paste.parse_lines(LONG_PLAIN), "long")
    assert len(short) > len(long_) > 5
    words = [len(paste.narration_of(s["lines"]).split()) for s in short]
    assert max(words) <= 14 * 1.4 and min(words) >= 5


def test_long_scene_tag_split_into_shots():
    text = "[SCENE] a big empty hall\n" + LONG_PLAIN
    scenes = paste.to_scenes(paste.parse_lines(text), "short")
    assert len(scenes) > 3 and all(s["visual"] == "a big empty hall" for s in scenes)


def test_variety_rules():
    scenes = paste.to_scenes(paste.parse_lines(LONG_PLAIN + " MIRA: Help!"), "short")
    for i, s in enumerate(scenes):
        s["id"] = f"s{i + 1:02d}"
    scenes[3]["lines"].append({"speaker": "MIRA", "text": "Wait for me."})
    planner.assign_variety(scenes, ["Mira"], "Mira", seed=5)
    shots = [s["shot"] for s in scenes]
    assert all(a != b for a, b in zip(shots, shots[1:]))  # never the same shot twice in a row
    assert len(set(shots)) >= 6
    share = sum(s["show_character"] for s in scenes) / len(scenes)
    assert 0.35 <= share <= 0.7, share  # main character in about half the scenes
    assert scenes[3]["show_character"] and "Mira" in scenes[3]["characters"]  # a speaking character is shown
    for key in ("lighting", "composition", "camera"):
        vals = [s[key] for s in scenes]
        assert all(a != b for a, b in zip(vals, vals[1:])), key
    assert all(not s["characters"] for s in scenes if not s["show_character"])


def test_prompt_follows_shot_and_hides_people(sf_root):
    from PIL import Image

    series = project.Series.create("Prompts")
    c = characters.add_character(series, "Mira", "silver hair, yellow raincoat")
    ref = characters.ref_path(series, c)
    ref.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(ref)
    with_char = {"id": "s02", "visual": "Mira at the wheel", "shot": "close_up", "show_character": True,
                 "characters": ["Mira"], "lighting": "cold blue moonlight", "composition": "centered"}
    p, refs = characters.scene_prompt(series, with_char, with_refs=True)
    assert p.startswith("Close-up") and "new pose" in p and refs == [ref] and "cold blue moonlight" in p
    assert "not sepia" in p
    empty = {"id": "s03", "visual": "an empty street", "shot": "environment", "show_character": False,
             "characters": ["Mira"]}
    p2, refs2 = characters.scene_prompt(series, empty, with_refs=True)
    assert refs2 == [] and "No people" in p2 and "silver hair" not in p2


def _fake_ai(monkeypatch, reply):
    def fake(messages, json_mode, temperature, max_tokens):
        data = json.loads(messages[-1]["content"]) if messages[-1]["content"].startswith("{") else {}
        return json.dumps(reply(data))

    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])


def test_script_from_text_with_ai_prompts(sf_root, monkeypatch):
    def reply(data):
        return {"protagonist": "Mira",
                "new_characters": [{"name": "Mira", "gender": "female", "description": "a taxi driver, 30, silver hair"}],
                "scenes": [{"id": s["id"], "visual": f"VISUAL for {s['id']}", "location": "city"} for s in data["scenes"]]}

    _fake_ai(monkeypatch, reply)
    series = project.Series.create("Night Radio")
    ep = series.episode(1)
    opts = project.EpisodeOptions(length="short", hero_count=1)
    sc = script.script_from_text(series, ep, opts, "MIRA: Hello?\n" + LONG_PLAIN, Reporter(echo=False))
    assert sc["source"] == "paste" and sc["language"] == "en" and len(sc["scenes"]) >= 6
    assert all(s["visual"].startswith("VISUAL for") for s in sc["scenes"])
    assert series.character("Mira")["description"] == "a taxi driver, 30, silver hair"
    assert series.data["protagonist"] == "Mira"
    assert sum(s["hero"] for s in sc["scenes"]) == 1
    assert sc["scenes"][0]["lines"][0] == {"speaker": "MIRA", "text": "Hello?"}
    md = ep.script_md_path.read_text(encoding="utf-8")
    assert "MIRA: Hello?" in md and "Shot:" in md


def test_script_from_text_without_any_ai(sf_root, monkeypatch):
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(net.ServiceError("offline")))
    series = project.Series.create("Offline")
    rep = Reporter(echo=False)
    sc = script.script_from_text(series, series.episode(1), project.EpisodeOptions(), SCRIPT, rep)
    assert sc["title"] == "The Night Radio" and len(sc["scenes"]) == 2
    assert sc["scenes"][0]["visual"].startswith("a yellow taxi")  # your [SCENE] text is kept
    assert sc["scenes"][1]["visual"] == "the dashboard radio glowing red"
    assert series.character("Mira") is not None  # a speaking character joins the series


def test_farsi_paste_sets_language(sf_root, monkeypatch):
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(net.ServiceError("offline")))
    series = project.Series.create("FA paste")
    opts = project.EpisodeOptions(languages=["en"])
    sc = script.script_from_text(series, series.episode(1), opts,
                                 "راوی: ساعت سه صبح رادیو روشن شد. صدایی اسم او را صدا زد.", Reporter(echo=False))
    assert sc["language"] == "fa" and sc["scenes"][0]["narration_fa"].startswith("ساعت سه")
    assert opts.languages[0] == "fa"
