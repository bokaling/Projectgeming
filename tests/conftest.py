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
def fresh_services():
    """Each test starts with every online service 'up' and no waiting."""
    from storyforge import images

    images._down_until.clear()
    images._last_pollinations[0] = 0.0
    images.KleinEngine.failed_reason = ""
    yield
