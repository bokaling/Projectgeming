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
