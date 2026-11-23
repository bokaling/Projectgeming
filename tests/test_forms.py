"""Backup forms mode (no web app): paste a script, run, done."""
from storyforge import forms, project

SCRIPT = """[TITLE] Forms Story
[SCENE] an empty train station at night
NARRATOR: The last train had already left.
LEO: Then why is the platform lit?
NARRATOR: Somewhere in the dark, a bell started to ring."""


def test_form_choices():
    assert forms._langs("English + Farsi") == ["en", "fa"] and forms._langs("Farsi") == ["fa"]
    assert forms.ACTIONS[1].startswith("✍️")


def test_generate_from_script(offline, needs_gl, capsys):
    forms.run("🚀 Generate from my SCRIPT", SCRIPT, "Forms Show", quality="480p", end_card=False)
    out = capsys.readouterr().out
    ep = project.Series("forms-show").episode(1)
    assert ep.video_path("en", "9x16").exists() and "Before you post" in out and "units" in out
    assert ep.load_script()["scenes"][0]["lines"][1]["speaker"] == "LEO"


def test_forms_friendly_messages(offline, capsys):
    forms.run("🚀 Generate from my SCRIPT", "", "Empty Show")
    assert "Paste your script" in capsys.readouterr().out
    forms.run("✍️ AI writes from my TOPIC", "", "Empty Show")
    assert "TOPIC" in capsys.readouterr().out


def test_forms_fix_one_shot_needs_a_shot_and_an_instruction(offline, capsys):
    forms.run("🔧 Fix one shot", "", "Nothing Yet")
    assert "no episodes yet" in capsys.readouterr().out
    series = project.Series.create("Has One")
    series.episode(1).save_options(project.EpisodeOptions())
    forms.run("🔧 Fix one shot", "", "Has One", shot=0, fix="")
    assert "Fill in SHOT" in capsys.readouterr().out
