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


def test_no_keys_means_no_ai_and_never_pollinations(sf_root, monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert llm.providers() == []
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert [n for n, _ in llm.providers()] == ["Groq"]
    assert not hasattr(llm, "_pollinations")


def test_busy_gemini_waits_5_15_30_then_flash_lite(sf_root, monkeypatch):
    from storyforge import net

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setitem(llm._model_cache, "gemini", ["gemini-3.5-flash-lite", "gemini-3.5-flash"])
    waits, calls = [], []
    monkeypatch.setattr(net, "_sleep", lambda s: waits.append(s))

    class Resp:
        def __init__(self, code, model):
            self.status_code, self.headers = code, {}
            self.text = "high demand" if code == 503 else ""
            self._model = model

        def json(self):
            return {"choices": [{"message": {"content": '{"script": "ok"}'}}]}

    def fake_request(method, url, headers=None, timeout=None, **kw):
        model = kw["json"]["model"]
        calls.append(model)
        return Resp(503 if model == "gemini-3.5-flash" else 200, model)

    import requests
    monkeypatch.setattr(requests, "request", fake_request)
    rep = Reporter(echo=False)
    lines = []
    monkeypatch.setattr(rep, "info", lambda m: lines.append(m))
    name, obj = llm.generate_json("s", "u", rep=rep, strong=True)
    assert waits[:3] == [5, 15, 30] and calls[:4] == ["gemini-3.5-flash"] * 4
    assert name == "Gemini (gemini-3.5-flash-lite)" and obj == {"script": "ok"}
    assert any("Gemini busy" in m for m in lines) and llm.gemini_busy()
    monkeypatch.setitem(llm.BUSY, "main", 0.0)


def use_fake_ai(monkeypatch, replies):
    """Make every AI call return the next reply in the list."""
    replies = list(replies)

    def fake(messages, json_mode, temperature, max_tokens):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)

    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])


GOOD = ("[TITLE] How a Dam Makes Power\n[SCENE] a huge dam\nNARRATOR: This concrete wall holds back 40 trillion liters "
        "of water, more than a whole lake.\n"
        "[SCENE] water rushes into a pipe\nNARRATOR: At the bottom, the water rushes into a steel pipe and falls 200 "
        "meters.\n[SCENE] a turbine spins\n"
        "NARRATOR: It hits the blades of a turbine and spins it very fast.\n[SCENE] houses light up\nNARRATOR: The "
        "spinning generator makes power, and a million homes light up.")


def test_topic_to_script_with_ai(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, [{"script": GOOD}])
    text, provider = script.write_from_topic("how a dam makes power", "short", seconds=20)
    assert provider == "FakeAI" and text.startswith("[TITLE] How a Dam Makes Power")
    assert text.count("NARRATOR:") == 4 and "[SCENE] a turbine spins" in text


def test_topic_to_script_repair_then_template(sf_root, monkeypatch):
    use_fake_ai(monkeypatch, ["not json at all", {"script": GOOD}])  # one repair with the same AI
    text, provider = script.write_from_topic("dams", "short", seconds=20)
    assert provider == "FakeAI" and "turbine" in text
    use_fake_ai(monkeypatch, [{"script": "too short"}, {"script": "still short"}])
    text, provider = script.write_from_topic("how a dam makes power", "short", rep=Reporter(echo=False))
    assert provider == "Template (no AI)" and text.startswith("[TITLE] How a dam makes power")
    with pytest.raises(Exception):
        script.write_from_topic("  ", "short")


def test_script_must_hit_the_target_length(sf_root, monkeypatch):
    """A 60 s Short needs ~150 words: a short reply goes back once with its word count."""
    from storyforge import paste

    assert paste.target_words("short", 60) == 150 and paste.target_words("short") == 200  # How it works: 80 s
    assert paste.target_words("short", 60, "story") == 165 and paste.target_words("long") == 1350
    seen = []
    long_script = GOOD.replace("NARRATOR: ", "NARRATOR: " + "and then the water keeps moving down " * 4)

    def fake(messages, json_mode, temperature, max_tokens):
        seen.append(messages[-1]["content"])
        return json.dumps({"script": GOOD if len(seen) == 1 else long_script})

    monkeypatch.setattr(llm, "providers", lambda allow_local=False: [("FakeAI", fake)])
    text, provider = script.write_from_topic("how a dam makes power", "short", seconds=60)
    assert provider == "FakeAI" and "words" in seen[1] and "needs about 150" in seen[1]
    assert paste.count_words(text) > 130


def test_busy_gemini_stops_with_a_friendly_message(sf_root, monkeypatch):
    from storyforge import net
    from storyforge.messages import FriendlyError

    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def busy(*a):
        raise net.ServiceError("HTTP 503 high demand", 503, True)

    monkeypatch.setattr(llm, "providers", lambda allow_local=False: [("Gemini (x)", busy)])
    with pytest.raises(FriendlyError, match="Gemini is busy"):
        script.write_from_topic("how an elevator works", "short")


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
