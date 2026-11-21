"""StoryForge Free: a 100% free AI story video maker.

All the real work lives in this package. The Colab notebook only installs it
and calls `storyforge.launch()` (web app) or `storyforge.forms` (backup mode).
"""

__version__ = "1.0.0"


def launch(public_link: bool = False, root: str | None = None, **kwargs):
    """Start the web app. Used by the notebook's Launch cell."""
    from .ui.app import launch as _launch

    return _launch(public_link=public_link, root=root, **kwargs)
