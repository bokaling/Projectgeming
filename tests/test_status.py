"""PART C: the live progress panel, step checklist, clean log, toasts and badges."""
import time

from storyforge.messages import Reporter
from storyforge.ui import status


class FakeJob:
    def __init__(self, rep, name="Making the video"):
        self.rep, self.name = rep, name


def run_some(rep):
    rep.step("📝 Reading your script")
    rep.ok("Script ready: “Cows”, 13 scenes")
    rep.step("🧭 Scene plan (the 3D world and every shot)")
    rep.ok("Plan by Built-in example plan")
    rep.step("🎬 3D render (9:16, 14 clip(s), CPU)")
    rep.info("/usr/lib/python3/site-packages/x.py:12: UserWarning: something internal")
    rep.ok("Scene 4/13 (3.1 s video, 10 s)")
    rep.progress(0.5, "3D render 4/13")


def test_checklist_and_friendly_step():
    rep = Reporter(echo=False)
    run_some(rep)
    states = dict(status.checklist(rep))
    assert states["📝 Writing script"] == "done" and states["🧭 Planning scenes"] == "done"
    assert states["🎬 Rendering shots"] == "running" and states["🎵 Sound"] == "waiting"
    assert status.friendly_step(rep) == "🎬 Rendering shot 4 of 13"
    rep.done({"videos": ["x.mp4"]}, "ok")
    states = dict(status.checklist(rep))
    assert states["🎬 Rendering shots"] == "done" and states["🗣️ Voiceover"] == "skipped"  # reused from before


def test_panel_shows_progress_time_left_log_and_errors():
    rep = Reporter(echo=False)
    rep.started = time.time() - 30
    run_some(rep)
    html = status.panel(FakeJob(rep))
    assert "Rendering shot 4 of 13" in html and "50%" in html and "left" in html and "sf-steps-live" in html
    assert "UserWarning" not in html and "Scene 4/13" in html  # plain English only
    rep.error("The GPU ran out of memory.", "Restart the session, then press the button again.")
    rep.fail(RuntimeError("x")) if hasattr(rep, "fail") else None
    rep.failed, rep.finished = True, True
    html = status.panel(FakeJob(rep))
    assert "sf-error" in html and "ran out of memory" in html and "Restart the session" in html
    assert "Nothing is running" in status.panel(None)


def test_toasts_for_important_moments():
    rep = Reporter(echo=False)
    run_some(rep)
    msgs, n = status.new_toasts(rep, 0)
    assert "📝 Script ready" in msgs and "🧭 Scene plan ready" in msgs
    rep.ok("Shot 7 changed (Built-in fixer): camera closer")
    rep.ok("how-things-work_ep01_en_9x16.mp4 (0:54 video, 14 clips joined without re-encoding)")
    msgs2, _ = status.new_toasts(rep, n)
    assert msgs2 == ["🔧 Shot 7 fixed", "🎬 Video saved to Drive"]  # only the new ones


def test_badges(sf_root, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    html = status.badges()
    assert "Gemini key ✅" in html and "HF token ❌" in html and "Drive" in html and "units this session" in html
