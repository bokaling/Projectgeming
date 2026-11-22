"""Reading your script: tags, speakers, scenes, Farsi, batch."""
import json

from storyforge import net, paste, project, script
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
    assert sc["language"] == "fa" and sc["scenes"][0]["narration"].startswith("ساعت سه")
    assert opts.languages[0] == "fa"
