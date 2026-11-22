import json

import pytest

from storyforge import config, messages, net, project


def test_settings_folders(sf_root):
    s = config.get()
    assert s.root == sf_root
    assert s.series_dir.is_dir() and s.music_dir.is_dir()
    assert s.gpu.available is False  # forced CPU in tests
    assert "cpu" in s.gpu.label.lower()
    assert s.model_cache("kokoro").startswith(str(sf_root))  # small model -> Drive


def test_secrets_never_required(monkeypatch, sf_root):
    for name in config.SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    found = config.load_secrets()
    assert set(found) == set(config.SECRET_NAMES) and not any(found.values())
    monkeypatch.setenv("GROQ_API_KEY", " abc ")
    assert config.load_secrets()["GROQ_API_KEY"] is True
    assert config.secret("GROQ_API_KEY") == "abc"


def test_slugify():
    assert project.slugify("The Last Signal!") == "the-last-signal"
    assert project.slugify("سیگنال آخر") == "سیگنال-آخر"
    assert project.slugify("   ") == "series"


def test_state_resume(tmp_path):
    st = project.State(tmp_path / "state.json")
    f = tmp_path / "a.png"
    f.write_text("x")
    fp = project.fingerprint("prompt", 1)
    assert not st.fresh("image:s01:9x16", fp)
    st.done("image:s01:9x16", fp, provider="test")
    st.done("image:s02:9x16", fp)
    # reload from disk, like after a disconnect
    st2 = project.State(tmp_path / "state.json")
    assert st2.fresh("image:s01:9x16", fp, files=[f])
    assert not st2.fresh("image:s01:9x16", project.fingerprint("new prompt", 1))
    assert not st2.fresh("image:s01:9x16", fp, files=[tmp_path / "missing.png"])
    st2.forget("image:s01")
    assert not st2.fresh("image:s01:9x16", fp) and st2.fresh("image:s02:9x16", fp)
    assert json.loads((tmp_path / "state.json").read_text())["steps"]["image:s02:9x16"]["fp"] == fp


def test_options_clamped():
    o = project.EpisodeOptions.from_dict({"hero_count": 99, "languages": ["xx"], "formats": [], "junk": 1})
    assert o.languages == ["en"] and o.formats == ["9x16"] and not hasattr(o, "hero_count")
    d = project.EpisodeOptions()
    assert d.source == "paste" and d.sfx is True and d.captions  # your script, soft sounds on, keyword captions
    assert d.end_card and not d.final_episode and d.quality_check
    assert project.EpisodeOptions.from_dict({"length": "long"}).formats == ["16x9"]


def test_series_and_episodes(sf_root):
    s = project.Series.create("My Show")
    assert s.next_episode_number() == 1
    ep = s.episode(1)
    ep2 = s.episode(2)
    assert s.next_episode_number() == 3 and s.episode_numbers() == [1, 2]
    assert ep.still_path("s01", "9x16").name == "s01_9x16.jpg" and ep.clip_path("s01", "9x16", "en").suffix == ".mp4"
    assert project.dims("9x16") == (1080, 1920) and project.dims("16x9", "720p") == (1280, 720)
    s.remember_episode(1, title="Pilot", summary="It begins.")
    again = project.list_series()[0]
    assert again.name == "My Show" and again.previous_summaries(2)[0]["title"] == "Pilot"


def test_explain_messages():
    what, todo = messages.explain(RuntimeError("CUDA out of memory. Tried to allocate 2 GiB"))
    assert "GPU ran out of memory" in what and "Restart" in todo
    what, _ = messages.explain(OSError(28, "No space left on device"))
    assert "disk is full" in what
    what, todo = messages.explain(messages.FriendlyError("A", "B"))
    assert (what, todo) == ("A", "B")


def test_reporter_collects():
    r = messages.Reporter(echo=False)
    r.step("Pictures")
    r.ok("Scene 1/3 picture (4 s)")
    r.progress(0.5)
    r.record("ok", "Images", "GPU")
    assert "Scene 1/3" in r.text() and r.fraction == 0.5 and r.summary[0][1] == "Images"
    r.request_stop()
    with pytest.raises(messages.StopRequested):
        r.check_stop()


class FakeResp:
    def __init__(self, code, text="", headers=None):
        self.status_code = code
        self.text = text
        self.headers = headers or {}


def test_request_retries_then_succeeds(monkeypatch):
    import requests

    calls = []

    def fake(method, url, **kw):
        calls.append(url)
        return FakeResp(429 if len(calls) < 3 else 200, "busy")

    monkeypatch.setattr(requests, "request", fake)
    monkeypatch.setattr(net, "_sleep", lambda s: None)
    assert net.request("GET", "http://x", retries=3).status_code == 200
    assert len(calls) == 3


def test_request_no_retry_on_401(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResp(401, "bad key"))
    with pytest.raises(net.ServiceError) as err:
        net.request("GET", "http://x")
    assert err.value.status == 401


def test_try_in_order_falls_back(sf_root):
    def broken():
        raise net.ServiceError("HTTP 503")

    name, result = net.try_in_order("test", [("A", broken), ("B", lambda: 42)])
    assert (name, result) == ("B", 42)
    with pytest.raises(net.AllProvidersFailed):
        net.try_in_order("test", [("A", broken)])
    usage = json.loads((sf_root / "usage.json").read_text())
    assert list(usage.values())[0]["B"] == 1


def test_gpu_profiles(sf_root):
    t4 = config.gpu_profile(config.GPUInfo(True, "Tesla T4", 15.0))
    l4 = config.gpu_profile(config.GPUInfo(True, "NVIDIA L4", 22.5))
    a100 = config.gpu_profile(config.GPUInfo(True, "NVIDIA A100-SXM4-40GB", 40.0))
    cpu = config.gpu_profile(config.GPUInfo(False))
    assert (t4.dtype, l4.dtype, a100.dtype) == ("fp16", "bf16", "bf16")
    assert cpu.cu_per_hour < t4.cu_per_hour < l4.cu_per_hour < a100.cu_per_hour


def test_session_meter_and_big_model_cache(sf_root, monkeypatch, tmp_path):
    assert "units" in config.session_label() and config.session_seconds() > 0
    monkeypatch.setattr(config, "free_disk_gb", lambda p: 120.0)
    s = config.init(root=tmp_path / "x", cache_big_models_on_drive="auto")
    assert s.cache_big_models_on_drive is False  # not on Drive: keep big models local
    s = config.init(root=tmp_path / "y", cache_big_models_on_drive="yes")
    assert s.cache_big_models_on_drive is True and s.big_model_cache == s.root / "models"
