"""The web app builds, and the background job manager behaves."""
import time

import pytest

gr = pytest.importorskip("gradio")

from storyforge.messages import FriendlyError  # noqa: E402
from storyforge.ui import app, jobs  # noqa: E402


def wait(manager, timeout=10):
    t = time.time()
    while manager.busy and time.time() - t < timeout:
        time.sleep(0.05)


def test_app_builds(sf_root):
    demo = app.build_app()
    assert demo is not None
    assert "StoryForge" in app.header_html() and "No GPU" in app.header_html()
    assert "Ready" in app.progress_html() or "%" in app.progress_html()


def test_theme_and_css_build():
    from storyforge.ui import theme

    t = theme.build_theme()
    assert t is not None and "--sf-grad" in theme.CSS and "max-width: 768px" in theme.CSS


def test_job_runs_in_background_and_reports():
    m = jobs.JobManager()

    def work(rep):
        rep.step("Working")
        rep.progress(0.5, "half")
        time.sleep(0.2)
        return 42

    ok, _ = m.start("Test job", work)
    assert ok and m.busy
    ok2, msg = m.start("Second", work)
    assert not ok2 and "still running" in msg  # one job at a time
    wait(m)
    assert m.job.rep.result == 42 and m.finished_count == 1 and not m.busy


def test_job_failure_is_friendly():
    m = jobs.JobManager()

    def bad(rep):
        raise FriendlyError("No picture service is working.", "Wait a few minutes.")

    m.start("Bad job", bad)
    wait(m)
    assert m.job.rep.failed and "Wait a few minutes." in m.job.rep.text()


def test_stop_button_stops_between_steps():
    m = jobs.JobManager()

    def long(rep):
        for _ in range(100):
            rep.check_stop()
            time.sleep(0.02)

    m.start("Long", long)
    time.sleep(0.1)
    assert "Stopping" in m.stop()
    wait(m)
    assert m.job.rep.failed and "Stopped" in m.job.rep.text()


def test_current_project_is_remembered(sf_root):
    from storyforge import project

    s = project.Series.create("Remember Me")
    s.episode(2)
    app.set_current(s.slug, 2)
    series, ep = app.current()
    assert series.name == "Remember Me" and ep.number == 2
    assert "Remember Me" in app.project_html()
