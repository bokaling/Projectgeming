"""Backup forms mode (no web app) works step by step."""
from storyforge import forms, project


def test_form_choices():
    assert forms._langs("English + Farsi") == ["en", "fa"] and forms._langs("Farsi") == ["fa"]
    assert forms._formats("9:16 + 16:9") == ["9x16", "16x9"] and forms._formats("16:9") == ["16x9"]


def test_forms_flow_write_edit_pictures_video(offline, capsys):
    forms.run("1. Write script", "Forms Show", 1, idea="A radio", formats="9:16", scenes=3, quality="480p")
    out = capsys.readouterr().out
    assert "## Scene 1" in out and "script.md" in out
    series = project.Series("forms-show")
    ep = series.episode(1)
    # edit script.md on "Drive" like the user would, then make pictures: the edit is used
    import time

    time.sleep(1.1)
    md = ep.script_md_path.read_text(encoding="utf-8").replace("At midnight the radio spoke.", "My own hook line.")
    ep.script_md_path.write_text(md, encoding="utf-8")
    forms.run("2. Make pictures", "Forms Show", 1, formats="9:16", scenes=3, quality="480p")
    out = capsys.readouterr().out
    assert "Using your edits" in out and ep.load_script()["scenes"][0]["narration"] == "My own hook line."
    assert ep.image_path("s01", "9x16").exists()
    forms.run("🔄 Regenerate scenes", "Forms Show", 1, formats="9:16", scenes=3, quality="480p", regenerate="2")
    assert ep.load_script()["scenes"][1]["regen"] == 1
    forms.run("3. Make video", "Forms Show", 1, formats="9:16", scenes=3, quality="480p", hero_scenes=0)
    out = capsys.readouterr().out
    assert ep.video_path("en", "9x16").exists() and "Before you post" in out


def test_forms_friendly_messages(offline, capsys):
    forms.run("3. Make video", "Empty Show", 1)
    assert "no script yet" in capsys.readouterr().out
    forms.run("1. Write script", "", 1, idea="x")
    assert "SERIES name" in capsys.readouterr().out
