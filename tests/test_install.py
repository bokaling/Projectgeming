"""Setup prints the real error when the Kokoro voice can't be installed."""
from storyforge import install


def test_kokoro_install_uses_pins_and_ignores_python_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(install, "_run", lambda cmd: (calls.append(cmd), (True, "ok"))[1])
    assert install.install_kokoro()
    pip_cmd = calls[0]
    assert "--ignore-requires-python" in pip_cmd and "thinc>=8.3,<8.4" in pip_cmd
    assert "from kokoro import" in calls[1][-1]  # a real import check, not just pip's exit code


def test_kokoro_failure_shows_the_error(monkeypatch, capsys):
    monkeypatch.setattr(install, "_run", lambda cmd: (False, "Collecting thinc\nERROR: Failed to build 'thinc'"))
    assert not install.install_kokoro()
    out = capsys.readouterr().out
    assert "failed to install" in out and "Failed to build 'thinc'" in out and "Python 3." in out
