import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["STORYFORGE_FORCE_CPU"] = "1"


@pytest.fixture()
def sf_root(tmp_path, monkeypatch):
    """A fresh StoryForge folder for each test."""
    from storyforge import config

    monkeypatch.setenv("STORYFORGE_CACHE", str(tmp_path / "cache"))
    config.init(root=tmp_path / "StoryForge")
    return tmp_path / "StoryForge"


@pytest.fixture(autouse=True)
def fresh_services(monkeypatch):
    """Each test starts with no remembered voices, and the ONNX backup voice never downloads (no internet in tests)."""
    from storyforge.audio import tts

    tts._resolved.clear()  # voices remembered in a session must not leak between tests
    tts._broken.clear()

    def no_onnx(*a, **k):
        raise RuntimeError("Kokoro ONNX is off in tests")

    monkeypatch.setattr(tts, "kokoro_onnx", no_onnx)  # a test can still replace it with its own fake
    yield


SCRIPT = {
    "title": "The Signal", "style": "moody painting",
    "characters": [{"name": "Mira", "description": "short silver hair, yellow raincoat", "gender": "female"}],
    "scenes": [
        {"narration": "At midnight the radio spoke.", "visual": "Mira and a glowing radio", "characters": ["Mira"],
         "camera": "push_in", "effects": ["dust"], "sfx": ["impact"], "mood": "tense", "hero": True},
        {"narration": "It knew her name.", "visual": "storm over a lighthouse", "camera": "pan_left",
         "effects": ["rain"], "sfx": ["whoosh"], "mood": "dark"},
        {"narration": "Don't open the door.", "visual": "a door with light under it", "characters": ["Mira"],
         "camera": "dolly_zoom", "effects": ["fog"], "sfx": [], "mood": "tense"},
    ],
    "cliffhanger": "Who knocks?", "summary": "Mira got a warning.", "thumbnail_text": "DON'T OPEN IT", "music_mood": "mysterious",
}
FA = {"title": "سیگنال", "thumbnail_text": "باز نکن", "lines": [
    {"id": "s01", "text": "نیمه‌شب رادیو حرف زد."}, {"id": "s02", "text": "اسمش را می‌دانست."}, {"id": "s03", "text": "در را باز نکن!"}]}


@pytest.fixture()
def offline(sf_root, monkeypatch):
    """No internet; the AI writer is faked."""
    from storyforge import llm, net

    def no_net(*a, **k):
        raise net.ServiceError("network problem", None, True)

    def fake(messages, json_mode, temperature, max_tokens):
        sysmsg = messages[0]["content"].lower()
        if "translate" in sysmsg:
            return json.dumps(FA, ensure_ascii=False)
        if "titles" in sysmsg:
            return json.dumps({"titles": ["T1"], "description": "D", "hashtags": {"youtube": ["shorts"]}})
        return json.dumps(SCRIPT)

    monkeypatch.setattr(net, "request", no_net)
    monkeypatch.setattr(llm, "providers", lambda allow_local=True: [("FakeAI", fake)])
    from storyforge.audio import tts

    def no_engine(*a, **k):
        raise RuntimeError("offline")

    for name in ("kokoro", "kokoro_onnx", "edge", "piper"):
        monkeypatch.setattr(tts, name, no_engine)
    return sf_root


_GL = {}


def gl_available() -> bool:
    """Can this machine draw 3D without a screen (EGL / Mesa)? Rendering tests skip if not."""
    if "ok" not in _GL:
        try:
            from storyforge.world import gl

            gl.create_context().release()
            _GL["ok"] = True
        except Exception:
            _GL["ok"] = False
    return _GL["ok"]


@pytest.fixture()
def needs_gl():
    if not gl_available():
        pytest.skip("no OpenGL on this machine (install libegl1 libgl1-mesa-dri)")


