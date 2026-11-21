"""Backup mode: plain Colab forms, no web app.

Use it if Colab blocks the web app link. Pick an ACTION in the form and run the
cell; run it again with the next ACTION. Progress is printed in the cell.

Editing without the web app:
* Script: open the Files panel (📁 on the left) → drive → MyDrive → StoryForge →
  series → <your series> → episodes → epNN → script.md. Double-click, edit, Ctrl+S.
* Your own picture/clip for a scene: put a file named upload.png (or upload.mp4)
  into that scene's folder: .../epNN/scenes/s03/
"""

from __future__ import annotations

import re

from . import config, pipeline
from . import script as script_mod
from .audio import tts
from .messages import Reporter, explain
from .project import EpisodeOptions, Series, write_json

ACTIONS = ["⚡ Quick test", "1. Write script", "2. Make pictures", "3. Make video", "🔄 Regenerate scenes"]


def _langs(choice: str) -> list[str]:
    c = (choice or "").lower()
    if "+" in c or "both" in c:
        return ["en", "fa"]
    return ["fa"] if "farsi" in c else ["en"]


def _formats(choice: str) -> list[str]:
    c = (choice or "").replace(" ", "")
    if "+" in c:
        return ["9x16", "16x9"]
    return ["16x9"] if c.startswith("16") else ["9x16"]


def _show_images(paths, labels, width=180) -> None:
    try:
        import base64  # noqa: PLC0415
        import io  # noqa: PLC0415

        from IPython.display import HTML, display  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        cells = []
        for p, label in zip(paths, labels):
            if p is None:
                cells.append(f"<div style='width:{width}px;color:#aaa'>{label}: no picture</div>")
                continue
            im = Image.open(p).convert("RGB")
            im.thumbnail((width * 2, width * 2))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()
            cells.append(f"<div style='width:{width}px;text-align:center;font:13px sans-serif'>"
                         f"<img src='data:image/jpeg;base64,{b64}' style='width:100%;border-radius:10px'><br>{label}</div>")
        display(HTML("<div style='display:flex;flex-wrap:wrap;gap:10px'>" + "".join(cells) + "</div>"))
    except Exception:
        for p, label in zip(paths, labels):
            print(f"   {label}: {p}")


def _show_videos(paths) -> None:
    try:
        from IPython.display import Video, display  # noqa: PLC0415

        for p in paths:
            print(f"🎬 {p}")
            display(Video(str(p), embed=True, width=320))
    except Exception:
        for p in paths:
            print(f"🎬 {p}")


def _sync_script_edits(ep, opts) -> None:
    """If you edited script.md on Drive, use your edits."""
    md, js = ep.script_md_path, ep.script_path
    if md.exists() and js.exists() and md.stat().st_mtime > js.stat().st_mtime + 1:
        new = script_mod.from_markdown(md.read_text(encoding="utf-8"), ep.load_script(), opts)
        script_mod.save_script(ep, new)
        print("✏️ Using your edits from script.md")


def run(action: str, series_name: str, episode: int, idea: str = "", languages: str = "English",
        formats: str = "9:16 + 16:9", scenes: int = 10, hero_scenes: int = 2, quality: str = "1080p",
        english_voice: str = "kokoro:am_fenrir", farsi_voice: str = "edge:fa-IR-FaridNeural", regenerate: str = "") -> None:
    s = config.init()
    config.load_secrets()
    print(f"✅ StoryForge forms mode · {s.gpu.label} · saving to {s.root}\n")
    rep = Reporter(echo=True)
    try:
        opts = EpisodeOptions.from_dict({
            "idea": idea, "languages": _langs(languages), "formats": _formats(formats), "scene_count": scenes,
            "hero_count": hero_scenes, "resolution": quality,
        })
        if action.startswith("⚡"):
            res = pipeline.quick_test(rep, idea, opts.languages, opts.primary_format)
            _show_videos(res["videos"])
            return
        if not (series_name or "").strip():
            print("❌ Type a SERIES name in the form first.")
            return
        series = Series.create(series_name.strip())
        series.data.setdefault("voices", {}).update({"en": english_voice, "fa": farsi_voice})
        series.save()
        ep = series.episode(int(episode or 1))
        old = ep.load_options()
        if ep.load_script() and not idea:
            opts.idea = old.idea
        ep.save_options(opts)
        write_json(s.root / "app.json", {"series": series.slug, "episode": ep.number})  # web app opens it too
        pipe = pipeline.Pipeline(series, ep, rep, opts)
        if action.startswith("1"):
            if not idea.strip() and ep.number == 1:
                print("❌ Type your story IDEA in the form first.")
                return
            sc = pipe.write_script()
            print("\n" + "=" * 70 + "\n" + script_mod.to_markdown(sc) + "=" * 70)
            print(f"\n✏️ To edit: Files panel (📁) → {ep.script_md_path}\n   Double-click it, change what you like, "
                  "press Ctrl+S. Then set ACTION to '2. Make pictures' and run this cell again.")
            if "fa" in opts.languages and tts.EDGE_WARNING:
                print("ℹ️ " + tts.EDGE_WARNING)
            return
        if not ep.load_script():
            print("❌ This episode has no script yet. Run ACTION '1. Write script' first.")
            return
        _sync_script_edits(ep, opts)
        if action.startswith("🔄"):
            nums = [int(n) for n in re.findall(r"\d+", regenerate or "")]
            if not nums:
                print("❌ Type the scene numbers in REGENERATE, e.g. 3, 5")
                return
            sc = ep.load_script()
            for n in nums:
                if 1 <= n <= len(sc["scenes"]):
                    pipe.regenerate(sc["scenes"][n - 1]["id"], keep_loaded=True)
            action = "2"
        if action.startswith("2"):
            pipe.character_pictures()
            pipe.scene_pictures(keep_loaded=True)
            sc = ep.load_script()
            paths = [ep.scene_source_image(x["id"], opts.primary_format, opts.formats) for x in sc["scenes"]]
            _show_images(paths, [f"Scene {i}" for i in range(1, len(paths) + 1)])
            print(f"\n🔄 Don't like a picture? Set ACTION to 'Regenerate scenes' and REGENERATE to its number.\n"
                  f"📤 Or put your own file named upload.png / upload.mp4 in {ep.dir / 'scenes' / 's03'} (for scene 3).\n"
                  "Then set ACTION to '3. Make video'.")
            return
        if action.startswith("3"):
            res = pipe.make_video()
            _show_videos(res["videos"])
            if res.get("thumbnails"):
                _show_images(res["thumbnails"], [p.split("/")[-1] for p in res["thumbnails"]], width=220)
            meta = ep.export_dir / "metadata.md"
            if meta.exists():
                print("\n" + meta.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        what, todo = explain(exc)
        print(f"\n❌ {what}\n👉 {todo}")
