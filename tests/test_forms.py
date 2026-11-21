"""Backup forms mode (no web app): paste a script, run, done."""
from storyforge import forms, project

SCRIPT = """[TITLE] Forms Story
[SCENE] an empty train station at night
NARRATOR: The last train had already left.
LEO: Then why is the platform lit?
NARRATOR: Somewhere in the dark, a bell started to ring."""


def test_form_choices():
    assert forms._langs("English + Farsi") == ["en", "fa"] and forms._langs("Farsi") == ["fa"]
    assert forms._heroes("Auto") == -1 and forms._heroes("3") == 3 and forms._heroes("0 (motion effects only)") == 0


def test_generate_then_regenerate(offline, capsys):
    forms.run("🚀 Generate from my SCRIPT", SCRIPT, "Forms Show", quality="480p", hero_scenes="0")
    out = capsys.readouterr().out
    ep = project.Series("forms-show").episode(1)
    assert ep.video_path("en", "9x16").exists() and "Before you post" in out and "units" in out
    assert ep.load_script()["scenes"][0]["lines"][1]["speaker"] == "LEO"
    forms.run("🔄 Regenerate scenes", "", "Forms Show", episode=1, regenerate="1", quality="480p")
    assert ep.load_script()["scenes"][0]["regen"] == 1


def test_forms_friendly_messages(offline, capsys):
    forms.run("🚀 Generate from my SCRIPT", "", "Empty Show")
    assert "Paste your script" in capsys.readouterr().out
    forms.run("🚀 Generate from my SCRIPT", SCRIPT, "", quality="480p")
    assert "SERIES name" in capsys.readouterr().out
    forms.run("🔄 Regenerate scenes", "", "Empty Show", regenerate="")
    assert "REGENERATE" in capsys.readouterr().out
