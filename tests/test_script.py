import json

import pytest

from storyforge import llm, project, script
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


def use_fake_ai(monkeypatch, replies):
    """Make every AI call return the next reply in the list."""
    replies = list(replies)

    def fake(messages, json_mode, temperature, max_tokens):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)

    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])


GOOD = ("[TITLE] How a Dam Makes Power\n[SCENE] a huge dam\nNARRATOR: This wall holds back 40 trillion liters.\n"
        "[SCENE] water rushes into a pipe\nNARRATOR: Water falls 200 meters.\n[SCENE] a turbine spins\n"
        "NARRATOR: It spins a turbine.\n[SCENE] houses light up\nNARRATOR: A million homes light up.")


def test_topic_to_script_with_ai(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, [{"script": GOOD}])
    text, provider = script.write_from_topic("how a dam makes power", "short")
    assert provider == "FakeAI" and text.startswith("[TITLE] How a Dam Makes Power")
    assert text.count("NARRATOR:") == 4 and "[SCENE] a turbine spins" in text


def test_topic_to_script_repair_then_template(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, ["not json at all", {"script": GOOD}])  # one repair with the same AI
    text, provider = script.write_from_topic("dams", "short")
    assert provider == "FakeAI" and "turbine" in text
    use_fake_ai(monkeypatch, [{"script": "too short"}, {"script": "still short"}])
    text, provider = script.write_from_topic("how a dam makes power", "short", rep=Reporter(echo=False))
    assert provider == "Template (no AI)" and text.startswith("[TITLE] How a dam makes power")
    with pytest.raises(Exception):
        script.write_from_topic("  ", "short")


def test_script_from_text_scenes_and_style(sf_root):
    series = project.Series.create("Dams")
    ep = series.episode(1)
    opts = project.EpisodeOptions()
    sc = script.script_from_text(series, ep, opts, "[STYLE] blue engineering look\n" + GOOD, Reporter(echo=False))
    assert sc["title"] == "How a Dam Makes Power" and len(sc["scenes"]) == 4 and sc["style"] == "blue engineering look"
    assert sc["scenes"][0]["kind"] == "hook" and sc["scenes"][-1]["kind"] == "cliffhanger"
    assert sc["scenes"][1]["visual"] == "water rushes into a pipe"
    assert ep.script_md_path.read_text(encoding="utf-8").startswith("[STYLE] blue")
    assert "[SCENE] a huge dam" in script.to_text(sc)
