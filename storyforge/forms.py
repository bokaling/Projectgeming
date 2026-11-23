"""Backup mode: plain Colab forms, no web app.

Use it if Colab blocks the web app link. Paste your script into the SCRIPT box (or type a TOPIC),
pick an ACTION and run the cell. Everything after that is automatic: scene plan, voice, 3D render,
sound, export. Several scripts separated by a line of ===== are made one after another.
"""

from __future__ import annotations


from . import config, pipeline
from .messages import Reporter, explain
from .project import EpisodeOptions, Series

ACTIONS = ["🚀 Generate from my SCRIPT", "✍️ AI writes from my TOPIC", "🔧 Fix one shot", "⚡ Quick test"]


def _langs(choice: str) -> list[str]:
    c = (choice or "").lower()
    if "+" in c or "both" in c:
        return ["en", "fa"]
    return ["fa"] if "farsi" in c else ["en"]


def _show_images(paths, labels, width=180) -> None:
    try:
        import base64  # noqa: PLC0415
        import io  # noqa: PLC0415

        from IPython.display import HTML, display  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        cells = []
        for p, label in zip(paths, labels):
            if p is None:
                cells.append(f"<div style='width:{width}px;color:#aaa'>{label}: no thumbnail</div>")
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


def run(action: str, script_text: str = "", series_name: str = "My Series", episode: int = 0, length: str = "Short",
        languages: str = "English", quality: str = "1080p", narrator_en: str = "kokoro:am_fenrir",
        narrator_fa: str = "edge:fa-IR-FaridNeural", sound_effects: bool = True, topic: str = "",
        end_card: bool = False, final_episode: bool = False, shot: int = 0, fix: str = "",
        video_format: str = "auto") -> None:
    s = config.init(root=None) if config._SETTINGS is None else config.get()
    found = config.load_secrets()
    prof = config.gpu_profile()
    print(f"✅ StoryForge forms mode · {s.gpu.label} → {prof.label} · saving to {s.root}")
    print(f"🔑 Free keys found: {sum(found.values())}")
    for line in config.key_lines():
        print(line)
    print()
    rep = Reporter(echo=True)
    try:
        ai = action.startswith("✍️")
        opts = EpisodeOptions.from_dict({
            "script_text": script_text, "idea": topic, "languages": _langs(languages),
            "length": "long" if str(length).lower().startswith("long") else "short", "resolution": quality,
            "sfx": bool(sound_effects), "source": "ai" if ai else "paste", "end_card": bool(end_card),
            "final_episode": bool(final_episode), "video_format": video_format or "auto",
        })
        if action.startswith("⚡"):
            res = pipeline.quick_test(rep, script_text, opts.languages, opts.length)
            _show_videos(res["videos"])
            return
        auto = (series_name or "").strip().lower() in ("", "auto")
        series = pipeline.auto_series(opts, script_text) if auto else Series.create(series_name.strip())
        series.data.setdefault("voices", {}).update({"en": narrator_en, "fa": narrator_fa})
        series.save()
        number = None if auto else pipeline.episode_number(series, int(episode) if episode and int(episode) > 0
                                                            else None, opts)
        if action.startswith("🔧"):  # change one shot of an episode you already made, render only what changed
            nums = series.episode_numbers()
            if not nums:
                print("❌ This series has no episodes yet. Make the video first.")
                return
            ep = series.episode(number or nums[-1])
            if not int(shot or 0) or not (fix or "").strip():
                print("❌ Fill in SHOT (the shot number) and FIX (what to change, e.g. make the tank bigger).")
                return
            res = pipeline.Pipeline(series, ep, rep, ep.load_options()).fix_scene(int(shot) - 1, fix)
            _show_videos(res.get("videos", []))
            return
        if ai and not topic.strip():
            print("❌ Type your TOPIC in the form first (e.g. how cow poop becomes electricity).")
            return
        if not ai and not script_text.strip():
            print("❌ Paste your script between the triple quotes in SCRIPT first.")
            return
        res = pipeline.generate(series, opts, "" if ai else script_text, rep, number)
        _show_videos(res.get("videos", []))
        if res.get("thumbnails"):
            _show_images(res["thumbnails"], [p.split("/")[-1] for p in res["thumbnails"]], width=220)
        for ep_no in res.get("episodes", []) or []:
            print(f"📁 Episode {ep_no}: {series.episode(ep_no).export_dir}")
        if res.get("metadata"):
            from pathlib import Path  # noqa: PLC0415

            meta = Path(res["metadata"])
            if meta.exists():
                print("\n" + meta.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        what, todo = explain(exc)
        print(f"\n❌ {what}\n👉 {todo}")
    finally:
        print("\n" + config.session_label())
