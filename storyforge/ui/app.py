"""The StoryForge web app: Idea → Script → Characters → Scenes → Voice & Captions → Export."""

from __future__ import annotations

import html
import shutil
import subprocess
import time
from pathlib import Path

from .. import captions, characters, config, pipeline, planner, publish
from .. import script as script_mod
from ..audio import music, tts
from ..messages import FriendlyError, explain
from ..project import (FORMATS, UPLOAD_VIDEO_EXT, EpisodeOptions, Series, list_series, read_json, slugify,
                       write_json)
from .jobs import ALL, JOBS
from .theme import CSS, HEAD, build_theme

NEW = "__new__"
TAB_IDS = ["idea", "script", "chars", "scenes", "voice", "export"]
LANG_CHOICES = [("English", "en"), ("Farsi · فارسی", "fa")]
MOOD_CHOICES = [("Auto (from the script)", "auto")] + [(m.title(), m) for m in script_mod.MOODS]
CAMERA_CHOICES = [(v, k) for k, v in script_mod.CAMERA_LABELS.items()]
SHOT_CHOICES = [(v, k) for k, v in planner.SHOT_LABELS.items()]


# ---------------------------------------------------------------------------
# Current project (remembered in StoryForge/app.json, so a reload or reconnect reopens it)
# ---------------------------------------------------------------------------


def _app_file() -> Path:
    return config.get().root / "app.json"


def set_current(slug: str, number: int) -> None:
    write_json(_app_file(), {"series": slug, "episode": int(number)})


def current():
    data = read_json(_app_file(), {}) or {}
    slug = data.get("series")
    if not slug:
        return None, None
    series = Series(slug)
    if not series.path.exists():
        return None, None
    return series, series.episode(int(data.get("episode") or 1))


def need_project():
    series, ep = current()
    if series is None:
        raise FriendlyError("No episode is open yet.", "Go to step 1 (Idea), type your idea and press 'Write my script'.")
    return series, ep


def _toast(exc: BaseException) -> None:
    import gradio as gr  # noqa: PLC0415

    what, todo = explain(exc)
    gr.Warning(f"{what} {todo}".strip())


# ---------------------------------------------------------------------------
# HTML pieces
# ---------------------------------------------------------------------------


def header_html() -> str:
    s = config.get()
    n_keys = sum(bool(config.secret(k)) for k in config.SECRET_NAMES)
    gpu = s.gpu
    chips = [
        f'<span class="sf-chip {"ok" if gpu.available else "warn"}">{"⚡ GPU: " + html.escape(gpu.label) if gpu.available else "☁️ No GPU: online mode"}</span>',
        f'<span class="sf-chip {"ok" if s.drive_mounted or s.platform != "colab" else "bad"}">'
        f'{"💾 Saving to Google Drive" if s.drive_mounted else ("💾 Saving to " + s.platform.title() if s.platform != "colab" else "⚠️ Not saving to Drive")}</span>',
        f'<span class="sf-chip">{"🔑 " + str(n_keys) + " free key(s)" if n_keys else "🔓 No keys (works anyway)"}</span>',
    ]
    return (
        '<div class="sf-header"><div class="sf-logo"><div class="sf-logo-mark">✦</div>'
        '<div><h1>StoryForge</h1><p>Free AI story episodes · consistent characters · hooks &amp; cliffhangers</p></div></div>'
        f'<div class="sf-chips">{"".join(chips)}</div></div>'
    )


def session_html() -> str:
    """⏱ Session time + estimated compute units (Colab doesn't show this live)."""
    prof = config.gpu_profile()
    s = config.get()
    cache = "📦 big models on Drive" if s.cache_big_models_on_drive else "📥 big models download each session"
    return (f'<div class="sf-project" style="text-align:right">{html.escape(config.session_label())} · {cache}'
            f'<br><span style="opacity:.7">Estimate from unofficial rates. Check Colab → Runtime → View resources.</span></div>')


def project_html() -> str:
    series, ep = current()
    if series is None:
        return '<div class="sf-project">No episode open yet. Start at step 1.</div>'
    sc = ep.load_script()
    title = html.escape(sc["title"]) if sc else "no script yet"
    return (f'<div class="sf-project">Open: <b>{html.escape(series.name)}</b> · Episode <b>{ep.number}</b> · '
            f'“{title}”</div>')


def progress_html() -> str:
    job = JOBS.job
    if job is None:
        return ('<div class="sf-progress idle"><div class="sf-progress-top"><span>✨ Ready</span>'
                '<span class="sf-progress-pct"></span></div><div class="sf-bar"><div class="sf-fill" style="width:0%"></div></div>'
                '<div class="sf-progress-sub">Nothing is running. Pick a step below.</div></div>')
    rep = job.rep
    pct = int(round(rep.fraction * 100))
    if rep.failed:
        cls, label = "failed", f"❌ {html.escape(job.name)} stopped"
    elif rep.finished:
        cls, label, pct = "done", f"✅ {html.escape(job.name)}: done", 100
    else:
        step = rep.label or "working"
        same = job.name.lower() in step.lower()
        cls, label = "", f"⏳ {html.escape(step if same else job.name + ' · ' + step)}"
    last = ""
    lines = [ln.strip() for ln in rep.lines if ln.strip()]
    if lines:
        last = html.escape(lines[-1][:160])
    return (f'<div class="sf-progress {cls}"><div class="sf-progress-top"><span>{label}</span>'
            f'<span class="sf-progress-pct">{pct}%</span></div><div class="sf-bar"><div class="sf-fill" style="width:{pct}%"></div></div>'
            f'<div class="sf-progress-sub">{last} · {rep.elapsed()}</div></div>')


def usage_html(result: dict | None) -> str:
    """This video's time and units, and this month's totals (to plan your 50 units)."""
    data = read_json(config.get().root / "usage_videos.json", []) or []
    month = time.strftime("%Y-%m")
    this = [d for d in data if str(d.get("date", "")).startswith(month)]
    shorts = [d for d in this if d.get("length") == "short"]
    longs = [d for d in this if d.get("length") == "long"]
    units = sum(float(d.get("units", 0)) for d in this)
    head = ""
    if result and result.get("minutes") is not None:
        head = (f"⏱ This video: <b>{result['minutes']} min</b> on {html.escape(str(result.get('gpu', '?')))} "
                f"≈ <b>{result.get('units', 0)} units</b><br>")
    return (f'<div class="sf-note">{head}📅 This month: {len(shorts)} short, {len(longs)} long · '
            f'≈ <b>{units:.1f}</b> of your 50 units (estimate)</div>')


def checklist_html(summary) -> str:
    if not summary:
        return ""
    icons = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
    items = "".join(f"<li>{icons.get(s, '•')} <b>{html.escape(p)}</b>: {html.escape(d)}</li>" for s, p, d in summary)
    return f'<div class="sf-card-title">Test results</div><ul class="sf-check">{items}</ul>'


# ---------------------------------------------------------------------------
# Settings <-> controls
# ---------------------------------------------------------------------------


def series_choices():
    items = [(s.name, s.slug) for s in list_series() if s.slug != "quick-test"]
    return items + [("➕ New series", NEW)]


def opts_from(text, idea, note, langs, length, scenes, heroes, res, cap_on, cap_style, mood, vol, sfx, fx,
              second, source="paste") -> EpisodeOptions:
    return EpisodeOptions.from_dict({
        "script_text": text or "", "idea": idea or "", "creator_note": note or "", "languages": langs or ["en"],
        "length": length, "scene_count": int(scenes), "hero_count": int(heroes), "resolution": res,
        "captions": bool(cap_on), "caption_style": cap_style, "music_mood": mood, "music_volume": float(vol),
        "sfx": bool(sfx), "effects": bool(fx), "second_format_images": second, "source": source,
    })


def opts_to_values(o: EpisodeOptions):
    return [o.script_text, o.idea, o.creator_note, o.languages, o.length, o.scene_count, o.hero_count, o.resolution,
            o.captions, o.caption_style, o.music_mood, o.music_volume, o.sfx, o.effects, o.second_format_images]


def hero_choices():
    prof = config.gpu_profile()
    auto = f"Auto ({prof.heroes_short} short / {prof.heroes_long} long on {prof.name})"
    return [(auto, -1), ("0 · motion effects only", 0)] + [(str(n), n) for n in (1, 2, 3, 5, 8, 10)]


SCRIPT_PLACEHOLDER = """[TITLE] The Night Radio
[SCENE] a yellow taxi in the rain at 3 a.m., neon signs
NARRATOR: The radio crackled at exactly three in the morning.
MIRA: Who's there?
NARRATOR: A voice answered with her own name.

(No [SCENE] lines? Just paste the story: it is split into scenes for you.
Several videos at once: separate the scripts with a line of =====)"""


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------


def build_app():
    import gradio as gr  # noqa: PLC0415

    config.get()
    music.ensure_library_readme()
    default_opts = EpisodeOptions()

    with gr.Blocks(title="StoryForge · Free AI Story Videos") as demo:
        gr.HTML(header_html())
        with gr.Row(elem_classes="sf-row-stack"):
            project_box = gr.HTML(project_html())
            session_box = gr.HTML(session_html())
        with gr.Group(elem_classes="sf-card"):
            progress_box = gr.HTML(progress_html())
            with gr.Row(elem_classes="sf-row-stack"):
                stop_btn = gr.Button("⏹ Stop", size="sm", variant="secondary", elem_classes="sf-stop", scale=0, min_width=110)
                with gr.Accordion("Show details (log)", open=False):
                    log_box = gr.Textbox(show_label=False, lines=10, max_lines=14, autoscroll=True, interactive=False,
                                         elem_classes="sf-log")

        # refresh counters: a finished job bumps the ones it affects
        r_script, r_chars, r_scenes, r_export = gr.State(0), gr.State(0), gr.State(0), gr.State(0)
        seen = gr.State({"count": -1, "ver": ""})

        with gr.Tabs(elem_classes="sf-steps", selected="idea") as tabs:
            # ------------------------------------------------------------ 1 Script (paste)
            with gr.Tab("1 · 📝 Script", id="idea"):
                with gr.Row(elem_classes="sf-row-stack", equal_height=False):
                    with gr.Column(scale=3):
                        with gr.Group(elem_classes=["sf-card", "sf-hero-card"]):
                            gr.HTML('<div class="sf-card-title">Paste your script</div>'
                                    '<div class="sf-card-sub"><b>[TITLE]</b> title · <b>[SCENE]</b> what we see '
                                    '(optional) · <b>NARRATOR:</b> line · <b>NAME:</b> a character speaking. '
                                    'Several scripts? Put a line of <b>=====</b> between them (batch).</div>')
                            paste_box = gr.Textbox(show_label=False, lines=16, max_lines=40,
                                                   placeholder=SCRIPT_PLACEHOLDER, elem_classes="sf-script")
                            length = gr.Radio([("⚡ Short · ~60 s · 9:16 · 1080×1920", "short"),
                                               ("🎬 Long · ~10 min · 16:9 · 1920×1080 · chapters", "long")],
                                              value=default_opts.length, show_label=False)
                        with gr.Row(elem_classes="sf-row-stack"):
                            gen_btn = gr.Button("🚀 Generate video", variant="primary", size="lg", scale=2)
                            quick_btn = gr.Button("⚡ Quick test", variant="secondary", size="lg", scale=1)
                        gr.HTML('<div class="sf-note">🚀 <b>Generate</b> does everything by itself: scenes, pictures, '
                                'motion, voice, captions, music, export, thumbnail, title, description and hashtags. '
                                '⚡ <b>Quick test</b> makes only the first 3 scenes (720p, no hero clips) to check '
                                'that everything works.</div>')
                        with gr.Accordion("✨ No script? Let the AI write one (optional)", open=False):
                            idea = gr.Textbox(label="Story idea", lines=3, placeholder="e.g. A lighthouse keeper hears "
                                              "her future self on an old radio…")
                            scenes_n = gr.Slider(3, 80, value=default_opts.scene_count, step=1,
                                                 label="Number of scenes (short ~12, long ~60)")
                            write_btn = gr.Button("✨ Write it with AI", variant="secondary")
                        note = gr.Textbox(label="Creator note (optional): your recap, question or comment for viewers",
                                          lines=2)
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Series &amp; episode</div>'
                                    '<div class="sf-card-sub">Same series = same characters, style and voices.</div>')
                            series_dd = gr.Dropdown(choices=series_choices(), value=NEW, label="Series")
                            new_name = gr.Textbox(label="New series name", placeholder="e.g. The Last Signal")
                            ep_no = gr.Number(value=1, precision=0, minimum=1, label="Episode number")
                            open_btn = gr.Button("📂 Open this episode", variant="secondary")
                        with gr.Group(elem_classes="sf-card"):
                            langs = gr.CheckboxGroup(LANG_CHOICES, value=default_opts.languages,
                                                     label="Languages (your script's language is detected; "
                                                           "tick the other one for a translated version too)")
                            heroes_n = gr.Dropdown(hero_choices(), value=default_opts.hero_count,
                                                   label="🎬 Hero scenes (real image-to-video)",
                                                   info="Auto = what your GPU can do quickly. Every other scene gets "
                                                        "2.5D motion effects.")
                            res = gr.Radio([("1080p (best)", "1080p"), ("720p (faster)", "720p")],
                                           value=default_opts.resolution, label="Quality")

            # ------------------------------------------------------------ 2 Script
            with gr.Tab("2 · ✍️ Edit", id="script"):
                with gr.Group(elem_classes="sf-card"):
                    gr.HTML('<div class="sf-card-title">Edit your script</div>'
                            '<div class="sf-card-sub">Change anything you like: this is where the story becomes yours. '
                            'Keep the <b>## Scene</b> lines and the <b>Narration:</b> lines. Add a scene by copying a '
                            'block; delete a scene by deleting its block. <b>Farsi:</b> lines are the Farsi voiceover.</div>')
                    script_box = gr.Textbox(show_label=False, lines=26, max_lines=60, elem_classes="sf-script")
                with gr.Row(elem_classes="sf-row-stack"):
                    save_script_btn = gr.Button("💾 Save my edits", variant="primary", size="lg")
                    translate_btn = gr.Button("🌍 Translate to Farsi", variant="secondary", size="lg")
                    rewrite_btn = gr.Button("✨ Write a new version", variant="secondary", size="lg")
                    to_chars_btn = gr.Button("Next: Characters →", variant="secondary", size="lg")

            # ------------------------------------------------------------ 3 Characters
            with gr.Tab("3 · 🧑‍🎨 Characters", id="chars"):
                with gr.Group(elem_classes="sf-card"):
                    gr.HTML('<div class="sf-card-title">Series look</div>'
                            '<div class="sf-card-sub">One visual style for every episode of this series.</div>')
                    style_box = gr.Textbox(show_label=False, lines=2)
                    save_style_btn = gr.Button("💾 Save style", variant="secondary", size="sm")
                gr.HTML('<div class="sf-note">Each character keeps the same description, seed and reference picture '
                        'in every scene and every episode. Use your own picture for the best consistency.</div>')

                @gr.render(inputs=[r_chars])
                def char_cards(_):
                    series, _ep = current()  # noqa: F841
                    if series is None or not series.characters:
                        gr.HTML('<div class="sf-empty">No characters yet. Write a script first, or add one below.</div>')
                        return
                    with gr.Row(elem_classes="sf-grid"):
                        for c in list(series.characters):
                            name = c["name"]
                            ref = characters.ref_path(series, c)
                            with gr.Column(elem_classes="sf-scene", min_width=240):
                                gr.Image(value=str(ref) if ref.exists() else None, show_label=False, height=300,
                                         interactive=False, buttons=["fullscreen"],
                                         placeholder="No picture yet")
                                gr.HTML(f'<div class="sf-card-title">{html.escape(name)}</div>')
                                desc = gr.Textbox(value=c.get("description", ""), label="Fixed look (40-60 words)", lines=4)
                                name_fa = gr.Textbox(value=c.get("name_fa", ""), label="Name in Farsi", elem_classes="sf-rtl")
                                vlang = (_ep.load_script() or {}).get("language", "en") if _ep else "en"
                                narr = series.data.get("voices", {}).get(vlang) or ("kokoro:am_fenrir" if vlang == "en"
                                                                                     else "edge:fa-IR-FaridNeural")
                                cur = characters.voice_for(series, name, vlang, narr)
                                cvoice = gr.Dropdown(tts.voice_choices(vlang, own=False),
                                                     value=f"{cur['engine']}:{cur['voice']}",
                                                     label=f"Voice when {name} speaks")
                                cprev = gr.Button("🔊 Preview voice", size="sm")
                                caudio = gr.Audio(show_label=False, interactive=False, visible=False)

                                def _voice(v, name=name, lang=vlang):
                                    s2, _ = need_project()
                                    ch = s2.character(name)
                                    if ch is not None:
                                        ch[f"voice_{lang}"] = v
                                        s2.save()

                                def _preview(v, name=name, lang=vlang):
                                    try:
                                        _, e2 = need_project()
                                        line = next((ln["text"] for sc_ in (e2.load_script() or {}).get("scenes", [])
                                                     for ln in sc_.get("lines", []) if ln["speaker"].lower() == name.lower()),
                                                    f"Hello, my name is {name}." if lang == "en" else f"سلام، من {name} هستم.")
                                        out = config.get().temp_dir / f"preview_{slugify(name)}.wav"
                                        engine, _w = tts.speak(line[:200], lang, tts.parse_voice(v, lang), out)
                                        gr.Info(f"{name}: {engine}")
                                        return gr.update(value=str(out), visible=True)
                                    except Exception as exc:  # noqa: BLE001
                                        _toast(exc)
                                        return gr.skip()

                                cvoice.input(_voice, cvoice, None)
                                cprev.click(_preview, cvoice, caudio)
                                with gr.Row():
                                    save_c = gr.Button("💾 Save", size="sm")
                                    new_pic = gr.Button("🎨 New picture", size="sm", variant="primary")
                                with gr.Row():
                                    up = gr.UploadButton("📤 My picture", file_types=["image"], size="sm")
                                    rm = gr.Button("🗑️ Remove", size="sm")

                                def _save(d, nf, name=name):
                                    try:
                                        s, _ = need_project()
                                        characters.update_character(s, name, description=d, name_fa=nf)
                                        gr.Info(f"Saved {name}. Press 'New picture' to update the reference.")
                                    except Exception as exc:  # noqa: BLE001
                                        _toast(exc)

                                def _new(name=name):
                                    s, _ = need_project()
                                    return start_job(f"Picture of {name}",
                                                     lambda rep: characters.ensure_references(s, [name], rep, force=[name]),
                                                     refresh=("chars",))

                                def _up(f, name=name, n=_):
                                    try:
                                        s, _ = need_project()
                                        characters.set_reference(s, name, f)
                                        gr.Info(f"Your picture is now {name}'s reference.")
                                    except Exception as exc:  # noqa: BLE001
                                        _toast(exc)
                                    return n + 1

                                def _rm(name=name, n=_):
                                    s, _ = need_project()
                                    characters.remove_character(s, name)
                                    return n + 1

                                save_c.click(_save, [desc, name_fa], None)
                                new_pic.click(_new, None, [progress_box])
                                up.upload(_up, [up], [r_chars])
                                rm.click(_rm, None, [r_chars])

                with gr.Group(elem_classes="sf-card"):
                    gr.HTML('<div class="sf-card-title">Add a character</div>')
                    with gr.Row(elem_classes="sf-row-stack"):
                        add_name = gr.Textbox(label="Name", scale=1)
                        add_desc = gr.Textbox(label="Look: age, face, hair, clothes, colors", scale=3)
                    add_btn = gr.Button("➕ Add character", variant="secondary")
                with gr.Row(elem_classes="sf-row-stack"):
                    make_refs_btn = gr.Button("🎨 Make missing character pictures", variant="primary", size="lg")
                    to_scenes_btn = gr.Button("Next: Scenes →", variant="secondary", size="lg")

            # ------------------------------------------------------------ 4 Scenes
            with gr.Tab("4 · 🖼️ Scenes", id="scenes"):
                with gr.Row(elem_classes="sf-row-stack"):
                    make_pics_btn = gr.Button("🖼️ Make all pictures", variant="primary", size="lg", scale=2)
                    view_fmt = gr.Radio([("Show 9:16", "9x16"), ("Show 16:9", "16x9")], value="9x16",
                                        show_label=False, scale=1)
                gr.HTML('<div class="sf-note">Preview every scene. <b>🔄 Regenerate</b> makes a new version, '
                        '<b>📤 Replace</b> uses your own picture or video clip. ⭐ Hero scenes get real image-to-video '
                        'motion on the GPU; all other scenes get 2.5D parallax and effects.</div>')

                @gr.render(inputs=[r_scenes, view_fmt])
                def scene_cards(_, fmt):
                    series, ep = current()
                    sc = ep.load_script() if ep else None
                    if not sc:
                        gr.HTML('<div class="sf-empty">No scenes yet. Write the script first (step 1).</div>')
                        return
                    opts = ep.load_options()
                    hero_ids = [s["id"] for s in sc["scenes"] if s.get("hero")][: opts.hero_count]
                    with gr.Row(elem_classes="sf-grid"):
                        for i, s in enumerate(sc["scenes"], 1):
                            sid = s["id"]
                            up_path = ep.upload_path(sid)
                            with gr.Column(elem_classes="sf-scene", min_width=240):
                                badges = [f'<span class="sf-badge">Scene {i}</span>']
                                if s["kind"] == "hook":
                                    badges.append('<span class="sf-badge hook">🪝 Hook</span>')
                                if s["kind"] == "cliffhanger":
                                    badges.append('<span class="sf-badge cliff">❓ Cliffhanger</span>')
                                if sid in hero_ids:
                                    badges.append('<span class="sf-badge hero">⭐ Hero</span>')
                                if s.get("shot"):
                                    badges.append(f'<span class="sf-badge">{planner.SHOT_LABELS.get(s["shot"], "")}</span>')
                                if up_path:
                                    badges.append('<span class="sf-badge mine">📤 Yours</span>')
                                gr.HTML(f'<div class="sf-badges">{"".join(badges)}</div>')
                                if up_path and up_path.suffix.lower() in UPLOAD_VIDEO_EXT:
                                    gr.Video(value=str(up_path), show_label=False, height=300, interactive=False)
                                else:
                                    img = ep.scene_source_image(sid, fmt, opts.formats)
                                    gr.Image(value=str(img) if img else None, show_label=False, height=300,
                                             interactive=False, buttons=["fullscreen"], placeholder="No picture yet")
                                text = s["narration"]
                                gr.HTML(f'<div class="sf-narr">{html.escape(text)}</div>')
                                if s.get("narration_fa"):
                                    gr.HTML(f'<div class="sf-narr sf-rtl">{html.escape(s["narration_fa"])}</div>')
                                vis = gr.Textbox(value=s["visual"], label="Picture prompt", lines=3)
                                shot = gr.Dropdown(SHOT_CHOICES, value=s.get("shot") or None, label="Shot type")
                                cam = gr.Dropdown(CAMERA_CHOICES, value=s["camera"], label="Camera move")
                                hero = gr.Checkbox(value=bool(s.get("hero")), label="⭐ Hero (real motion)")
                                with gr.Row():
                                    regen = gr.Button("🔄 Regenerate", size="sm", variant="primary")
                                    rep_btn = gr.UploadButton("📤 Replace", file_types=["image", "video"], size="sm")
                                with gr.Row():
                                    save_s = gr.Button("💾 Save", size="sm")
                                    if up_path:
                                        undo = gr.Button("↩️ Use AI picture", size="sm")

                                def _save_scene(v, c, h, sh=None, sid=sid, n=_):
                                    try:
                                        _, e = need_project()
                                        data = e.load_script()
                                        for x in data["scenes"]:
                                            if x["id"] == sid:
                                                x["visual"], x["camera"], x["hero"] = v.strip(), c, bool(h)
                                                if sh in planner.SHOTS:
                                                    x["shot"], x["show_character"] = sh, planner.SHOTS[sh][1]
                                                    if not x["show_character"]:
                                                        x["characters"] = []
                                        script_mod.save_script(e, data)
                                        gr.Info("Saved. Press Regenerate to see the new prompt.")
                                    except Exception as exc:  # noqa: BLE001
                                        _toast(exc)
                                    return n + 1

                                def _regen(v, c, h, sh, sid=sid, n=_):
                                    _save_scene(v, c, h, sh, sid, n)
                                    s2, e = need_project()
                                    o = e.load_options()
                                    return start_job(f"New picture for scene {sid[1:].lstrip('0')}",
                                                     lambda rep: pipeline.Pipeline(s2, e, rep, o).regenerate(sid),
                                                     refresh=("scenes",))

                                def _replace(f, sid=sid, n=_):
                                    try:
                                        _, e = need_project()
                                        e.set_upload(sid, f)
                                        gr.Info("Your file will be used for this scene.")
                                    except Exception as exc:  # noqa: BLE001
                                        _toast(exc)
                                    return n + 1

                                save_s.click(_save_scene, [vis, cam, hero, shot], [r_scenes])
                                regen.click(_regen, [vis, cam, hero, shot], [progress_box])
                                rep_btn.upload(_replace, [rep_btn], [r_scenes])
                                if up_path:
                                    def _undo(sid=sid, n=_):
                                        _, e = need_project()
                                        e.clear_upload(sid)
                                        e.state.forget(f"clip:{sid}")
                                        return n + 1

                                    undo.click(_undo, None, [r_scenes])

                with gr.Row(elem_classes="sf-row-stack"):
                    to_voice_btn = gr.Button("Next: Voice & Captions →", variant="secondary", size="lg")

            # ------------------------------------------------------------ 5 Voice & captions
            with gr.Tab("5 · 🎙️ Voice & Captions", id="voice"):
                with gr.Row(elem_classes="sf-row-stack", equal_height=False):
                    with gr.Column():
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Voices</div>'
                                    '<div class="sf-card-sub">Saved for the whole series, so every episode sounds the same.</div>')
                            voice_en = gr.Dropdown(tts.voice_choices("en"), value="kokoro:am_fenrir",
                                                   label="Narrator voice · English (one male narrator by default)")
                            voice_fa = gr.Dropdown(tts.voice_choices("fa"), value="edge:fa-IR-FaridNeural",
                                                   label="Narrator voice · Farsi")
                            gr.HTML('<div class="sf-note">Characters who speak in your script (lines like '
                                    '<b>MIRA:</b>) get their own voice: pick and preview it on step 3.</div>')
                            gr.HTML(f'<div class="sf-warn">⚠️ {html.escape(tts.EDGE_WARNING)}</div>')
                            preview_lang = gr.Radio(LANG_CHOICES, value="en", label="Preview language")
                            preview_btn = gr.Button("🔊 Preview voice", variant="secondary")
                            preview_audio = gr.Audio(show_label=False, interactive=False)
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">🎙️ Your own voice (best for monetization)</div>'
                                    '<div class="sf-card-sub">Record the whole episode on your phone, reading the '
                                    'narration in order, and upload one file. StoryForge cuts it into scenes and '
                                    'times the captions. The voice choice switches to “My own recording”.</div>')
                            own_en = gr.File(label="My English recording", file_types=["audio"], type="filepath", height=130)
                            own_fa = gr.File(label="My Farsi recording", file_types=["audio"], type="filepath", height=130)
                    with gr.Column():
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Captions</div>')
                            cap_on = gr.Checkbox(value=True, label="Burn word-by-word captions into the video")
                            cap_style = gr.Radio([(v, k) for k, v in captions.STYLES.items()], value="highlight", label="Style")
                            accent = gr.Radio([(k.title(), k) for k in captions.ACCENTS], value="yellow", label="Highlight color")
                            cap_prev_btn = gr.Button("👀 Preview captions", variant="secondary")
                            cap_prev = gr.Image(show_label=False, interactive=False, height=360, buttons=["fullscreen"])
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Music &amp; effects</div>'
                                    '<div class="sf-card-sub">Built-in music and sounds are made by the app: no copyright '
                                    'claims. Add your own tracks in Drive: StoryForge/library/music/&lt;mood&gt;/.</div>')
                            mood = gr.Dropdown(MOOD_CHOICES, value="auto", label="Music mood")
                            vol = gr.Slider(0, 0.4, value=default_opts.music_volume, step=0.01,
                                            label="Music volume (it also ducks under the voice automatically)")
                            sfx = gr.Checkbox(value=False, label="Sound effects (soft whoosh, impact, rain…) · off = calmer")
                            fx = gr.Checkbox(value=True, label="Visual effects (particles, light, grain)")
                            second = gr.Radio([("Auto", "auto"), ("Separate 16:9 pictures (better)", "generate"),
                                               ("Reuse 9:16 pictures (faster)", "reuse")], value="auto",
                                              label="Pictures for the second format")
                with gr.Row(elem_classes="sf-row-stack"):
                    to_export_btn = gr.Button("Next: Export →", variant="secondary", size="lg")

            # ------------------------------------------------------------ 6 Export
            with gr.Tab("6 · 🎬 Export", id="export"):
                with gr.Group(elem_classes=["sf-card", "sf-hero-card"]):
                    gr.HTML('<div class="sf-card-title">Make the video</div>'
                            '<div class="sf-card-sub">Pictures, hero clips, voice, captions, music and both formats. '
                            'If Colab disconnects, open the app again and press this button: finished parts are kept.</div>')
                    make_btn = gr.Button("🎬 Make my video", variant="primary", size="lg", elem_classes="sf-big")

                @gr.render(inputs=[r_export])
                def export_view(_):
                    series, ep = current()
                    res_ = pipeline.load_result(ep) if ep else None
                    if not res_:
                        gr.HTML('<div class="sf-empty">Your finished videos will appear here.</div>')
                        return
                    vids = [v for v in res_.get("videos", []) if Path(v).exists()]
                    with gr.Row(elem_classes="sf-grid"):
                        for v in vids:
                            with gr.Column(elem_classes="sf-scene", min_width=240):
                                gr.Video(value=v, label=Path(v).stem.split("_", 2)[-1].replace("_", " · "),
                                         height=420, interactive=False)
                    thumbs = [t for t in res_.get("thumbnails", []) if Path(t).exists()]
                    if thumbs:
                        gr.Gallery(value=thumbs, label="Thumbnails", columns=4, height=300, object_fit="contain")
                    meta = Path(res_.get("metadata", ""))
                    files = vids + thumbs + ([str(meta)] if meta.exists() else [])
                    gr.File(value=files, label="Download files", file_count="multiple", interactive=False)
                    if meta.exists():
                        with gr.Group(elem_classes="sf-card"):
                            gr.Markdown(meta.read_text(encoding="utf-8"))
                    gr.HTML(f'<div class="sf-note">📁 Saved in Google Drive: {html.escape(str(ep.export_dir))}</div>')
                    gr.HTML(usage_html(res_))

                test_box = gr.HTML()
                with gr.Row(elem_classes="sf-row-stack"):
                    clean_btn = gr.Button("🧹 Free up Drive space (delete re-makeable scene clips)", variant="secondary")

        timer = gr.Timer(1.0)
        gr.Timer(20.0).tick(lambda: session_html(), None, session_box, show_progress="hidden")

        # ------------------------------------------------------------ wiring
        settings = [paste_box, idea, note, langs, length, scenes_n, heroes_n, res, cap_on, cap_style, mood, vol, sfx,
                    fx, second]
        refreshers = [r_script, r_chars, r_scenes, r_export]

        def start_job(name, fn, goto=None, refresh=ALL):
            ok, msg = JOBS.start(name, fn, goto, refresh)
            (gr.Info if ok else gr.Warning)(msg)
            return progress_html()

        def tick(seen_info, rs, rc, rsc, re_):
            job = JOBS.job
            if job is None:
                return [gr.skip()] * 8
            seen_info = seen_info if isinstance(seen_info, dict) else {"count": -1, "ver": ""}
            ver = f"{id(job)}:{job.rep.version}"
            done_now = JOBS.finished_count != seen_info["count"] and job.rep.finished
            if not done_now and ver == seen_info["ver"]:
                return [gr.skip()] * 8  # nothing new: don't redraw
            out = [progress_html(), job.rep.text(120)]
            if done_now:
                bump = lambda key, v: v + 1 if key in job.refresh else gr.skip()  # noqa: E731
                out += [bump("script", rs), bump("chars", rc), bump("scenes", rsc), bump("export", re_)]
                out.append(gr.Tabs(selected=job.goto) if job.goto and not job.rep.failed else gr.skip())
                out.append({"count": JOBS.finished_count, "ver": ver})
                if job.rep.failed:
                    what = [ln for ln in job.rep.lines if "❌" in ln]
                    gr.Warning((what[-1].strip() if what else "Something went wrong.") + " See the log for what to do.")
            else:
                out += [gr.skip()] * 5 + [{"count": seen_info["count"], "ver": ver}]
            return out

        timer.tick(tick, [seen] + refreshers, [progress_box, log_box] + refreshers + [tabs, seen], show_progress="hidden")
        stop_btn.click(lambda: gr.Info(JOBS.stop()), None, None)

        # load script text / style when their counters change
        def load_script_text(_):
            _, ep = current()
            sc = ep.load_script() if ep else None
            return script_mod.to_markdown(sc) if sc else ""

        def load_style(_):
            series, _ep = current()
            return series.data.get("style", "") if series else ""

        r_script.change(load_script_text, r_script, script_box)
        r_script.change(lambda _: project_html(), r_script, project_box)
        r_chars.change(load_style, r_chars, style_box)

        def load_test_box(_):
            job = JOBS.job
            return checklist_html(job.rep.summary) if job and job.name == "Quick test" else ""

        r_export.change(load_test_box, r_export, test_box)

        # ---- Idea step
        def on_series(choice):
            if choice == NEW:
                return gr.update(visible=True), 1
            s = Series(choice)
            return gr.update(visible=False), s.next_episode_number()

        series_dd.input(on_series, series_dd, [new_name, ep_no])

        def resolve_series(choice, name):
            if choice == NEW or not choice:
                if not (name or "").strip():
                    raise FriendlyError("Give your new series a name first.", "Type it in 'New series name'.")
                s = Series.create(name.strip())
            else:
                s = Series(choice)
            return s

        def on_generate(choice, name, number, *vals):
            """🚀 One click: your pasted script(s) → finished videos."""
            from .. import paste  # noqa: PLC0415

            try:
                o = opts_from(*vals, source="paste")
                texts = paste.split_scripts(o.script_text)
                if not texts:
                    raise FriendlyError("The script box is empty.", "Paste your script, then press Generate.")
                s = resolve_series(choice, name)
                for k, t in enumerate(texts, 1):  # too short for a Short / a long video? say so (it still runs)
                    warn = paste.length_warning(t, o.length)
                    if warn:
                        gr.Warning(("" if len(texts) == 1 else f"Script {k}: ") + warn)
                if len(texts) > 1:  # batch: new episode numbers after the last one
                    first = s.next_episode_number()
                    set_current(s.slug, first)
                    html_ = start_job(f"Batch: {len(texts)} videos",
                                      lambda rep: pipeline.generate(s, o, o.script_text, rep), goto="export")
                else:
                    number = int(number or s.next_episode_number())
                    e = s.episode(number)
                    if e.load_script():
                        shutil.copyfile(e.script_path, e.dir / f"script_backup_{int(time.time())}.json")
                    set_current(s.slug, number)
                    html_ = start_job("Making your video",
                                      lambda rep: pipeline.generate(s, o, o.script_text, rep, number), goto="export")
                return html_, project_html(), gr.update(choices=series_choices(), value=s.slug), gr.update(visible=False)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip(), gr.skip(), gr.skip(), gr.skip()

        gen_btn.click(on_generate, [series_dd, new_name, ep_no] + settings,
                      [progress_box, project_box, series_dd, new_name])

        def on_write(choice, name, number, *vals):
            try:
                o = opts_from(*vals, source="ai")
                s = resolve_series(choice, name)
                number = int(number or 1)
                if not o.idea.strip() and number <= 1:
                    raise FriendlyError("Type your story idea first.", "One or two sentences are enough.")
                e = s.episode(number)
                if e.load_script():
                    shutil.copyfile(e.script_path, e.dir / f"script_backup_{int(time.time())}.json")
                e.save_options(o)
                set_current(s.slug, number)
                html_ = start_job("Writing the script", lambda rep: pipeline.Pipeline(s, e, rep, o).write_script(),
                                  goto="script")
                return html_, project_html(), gr.update(choices=series_choices(), value=s.slug), gr.update(visible=False)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip(), gr.skip(), gr.skip(), gr.skip()

        write_btn.click(on_write, [series_dd, new_name, ep_no] + settings,
                        [progress_box, project_box, series_dd, new_name])

        def on_quick(*vals):
            o = opts_from(*vals)
            set_current("quick-test", 1)
            return start_job("Quick test", lambda rep: pipeline.quick_test(rep, o.script_text, o.languages, o.length),
                             goto="export")

        quick_btn.click(on_quick, settings, [progress_box])

        def on_open(choice, name, number):
            try:
                s = resolve_series(choice, name)
                number = int(number or 1)
                e = s.episode(number)
                set_current(s.slug, number)
                o = e.load_options()
                voices = s.data.get("voices", {})
                gr.Info(f"Opened {s.name}, episode {number}.")
                return ([project_html(), gr.update(choices=series_choices(), value=s.slug)] + opts_to_values(o)
                        + [voices.get("en", "kokoro:am_fenrir"), voices.get("fa", "edge:fa-IR-FaridNeural"),
                           s.data.get("caption_accent", "yellow")]
                        + [int(time.time())] * 4)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return [gr.skip()] * (2 + len(settings) + 3 + 4)

        open_btn.click(on_open, [series_dd, new_name, ep_no],
                       [project_box, series_dd] + settings + [voice_en, voice_fa, accent] + refreshers)

        # ---- settings are saved whenever they change
        def save_settings(*vals):
            series, ep = current()
            if ep is None:
                return
            o = opts_from(*vals)
            old = ep.load_options()
            ep.save_options(o)
            if o.hero_count != old.hero_count and ep.load_script():
                sc = ep.load_script()
                script_mod.apply_hero_count(sc["scenes"], o.hero_count)
                script_mod.save_script(ep, sc)

        for comp in settings:  # .input = only when YOU change it (not when the app fills it in)
            comp.input(save_settings, settings, None, show_progress="hidden")

        def save_voice(lang, value):
            series, _ep = current()
            if series is None:
                return
            series.data.setdefault("voices", {})[lang] = value
            series.save()

        voice_en.input(lambda v: save_voice("en", v), voice_en, None)
        voice_fa.input(lambda v: save_voice("fa", v), voice_fa, None)

        def save_accent(a):
            series, _ep = current()
            if series is not None:
                series.data["caption_accent"] = a
                series.save()

        accent.input(save_accent, accent, None)

        # ---- Script step
        def on_save_script(text, *vals):
            try:
                _, ep = need_project()
                o = ep.load_options()
                new = script_mod.from_markdown(text, ep.load_script(), o)
                script_mod.save_script(ep, new)
                missing = "fa" in o.languages and any(not s["narration_fa"] for s in new["scenes"])
                gr.Info("Saved! " + ("Some Farsi lines are empty: press 'Translate to Farsi' or type them." if missing else ""))
                return script_mod.to_markdown(new), project_html()
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip(), gr.skip()

        save_script_btn.click(on_save_script, [script_box], [script_box, project_box])

        def on_translate(text):
            try:
                series, ep = need_project()
                o = ep.load_options()
                new = script_mod.from_markdown(text, ep.load_script(), o)
                script_mod.save_script(ep, new)
                return start_job("Translating to Farsi",
                                 lambda rep: script_mod.translate_script(series, ep, ep.load_script(), rep),
                                 refresh=("script",))
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        translate_btn.click(on_translate, [script_box], [progress_box])

        def on_rewrite():
            try:
                series, ep = need_project()
                o = ep.load_options()
                if ep.load_script():
                    shutil.copyfile(ep.script_path, ep.dir / f"script_backup_{int(time.time())}.json")
                return start_job("Writing the script", lambda rep: pipeline.Pipeline(series, ep, rep, o).write_script(),
                                 goto="script")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        rewrite_btn.click(on_rewrite, None, [progress_box])

        # ---- Characters step
        def on_save_style(text):
            try:
                series, _ = need_project()
                series.data["style"] = text.strip()
                series.data["style_custom"] = True
                series.save()
                gr.Info("Style saved for the whole series.")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)

        save_style_btn.click(on_save_style, style_box, None)

        def on_add_char(name, desc, n):
            try:
                series, _ = need_project()
                if not name.strip():
                    raise FriendlyError("Type a name first.")
                characters.add_character(series, name.strip(), desc)
                series.save()
                return "", "", n + 1
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip(), gr.skip(), gr.skip()

        add_btn.click(on_add_char, [add_name, add_desc, r_chars], [add_name, add_desc, r_chars])

        def on_make_refs():
            try:
                series, ep = need_project()
                o = ep.load_options()
                return start_job("Character pictures",
                                 lambda rep: pipeline.Pipeline(series, ep, rep, o).character_pictures(),
                                 refresh=("chars",))
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        make_refs_btn.click(on_make_refs, None, [progress_box])

        # ---- Scenes step
        def on_make_pics():
            try:
                series, ep = need_project()
                o = ep.load_options()

                def run(rep):
                    p = pipeline.Pipeline(series, ep, rep, o)
                    p.character_pictures()
                    p.scene_pictures(keep_loaded=True)

                return start_job("Scene pictures", run, goto="scenes", refresh=("chars", "scenes"))
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        make_pics_btn.click(on_make_pics, None, [progress_box])

        # ---- Voice step
        def on_preview(lang, ven, vfa):
            try:
                series, ep = current()
                sc = ep.load_script() if ep else None
                text = ""
                if sc:
                    text = sc["scenes"][0]["narration_fa" if lang == "fa" else "narration"]
                text = text or ("این یک نمونه صدا برای داستان شماست." if lang == "fa" else "This is how your story will sound.")
                out = config.get().temp_dir / f"preview_{lang}.wav"
                engine, _w = tts.speak(text, lang, tts.parse_voice(vfa if lang == "fa" else ven, lang), out)
                gr.Info(f"Voice: {engine}")
                return str(out)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return None

        preview_btn.click(on_preview, [preview_lang, voice_en, voice_fa], preview_audio)

        def on_own(f, lang):
            try:
                series, ep = need_project()
                if not f:
                    return gr.skip()
                for old in ep.audio_dir(lang).glob("own_voice.*"):
                    old.unlink()
                dst = ep.audio_dir(lang) / f"own_voice{Path(f).suffix.lower() or '.wav'}"
                shutil.copyfile(f, dst)
                series.data.setdefault("voices", {})[lang] = "own:own"
                series.save()
                gr.Info("Recording saved. Voice set to 'My own recording'.")
                return "own:own"
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        own_en.upload(lambda f: on_own(f, "en"), own_en, voice_en)
        own_fa.upload(lambda f: on_own(f, "fa"), own_fa, voice_fa)

        def on_cap_preview(style, acc, lang_choice):
            try:
                series, ep = current()
                sc = ep.load_script() if ep else None
                lang = lang_choice or "en"
                text = (sc["scenes"][0].get("narration_fa" if lang == "fa" else "narration") if sc else "") or (
                    "نیمه‌شب رادیو با صدای خودم حرف زد" if lang == "fa" else "At midnight the radio spoke my name")
                fmt = (ep.load_options().primary_format if ep else "9x16")
                W, H = (540, 960) if fmt == "9x16" else (960, 540)
                from ..audio import align  # noqa: PLC0415

                words = align.proportional(align.split_words(text), 0.0, 3.0)
                tmp = config.get().temp_dir
                ass = captions.write_ass(tmp / "preview.ass", words, (W, H), fmt, lang, style, acc, total=3.0)
                bg = ep.scene_source_image(sc["scenes"][0]["id"], fmt, ep.load_options().formats) if sc else None
                out = tmp / "caption_preview.png"
                t = (words[min(1, len(words) - 1)]["s"] + words[min(1, len(words) - 1)]["e"]) / 2
                src = ["-loop", "1", "-i", str(bg)] if bg else ["-f", "lavfi", "-i", f"color=c=0x1a1030:s={W}x{H}"]
                vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{captions.ass_filter(ass)}"
                subprocess.run([config.ffmpeg_path(), "-y", "-loglevel", "error", *src, "-t", "3", "-vf", vf,
                                "-ss", f"{t:.2f}", "-frames:v", "1", str(out)], check=True, timeout=60)
                return str(out)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return None

        cap_prev_btn.click(on_cap_preview, [cap_style, accent, preview_lang], cap_prev)

        # ---- Export step
        def on_make():
            try:
                series, ep = need_project()
                o = ep.load_options()
                if not ep.load_script():
                    raise FriendlyError("This episode has no script yet.", "Write the script on step 1 first.")
                return start_job("Making the video", lambda rep: pipeline.Pipeline(series, ep, rep, o).make_video(),
                                 goto="export", refresh=("chars", "scenes", "export"))
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        make_btn.click(on_make, None, [progress_box])

        def on_clean():
            try:
                _, ep = need_project()
                mb = ep.cleanup_work_files()
                gr.Info(f"Freed {mb} MB. (They are re-made automatically if needed.)")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)

        clean_btn.click(on_clean, None, None)

        # ---- navigation
        for btn, target in ((to_chars_btn, "chars"), (to_scenes_btn, "scenes"), (to_voice_btn, "voice"),
                            (to_export_btn, "export")):
            btn.click(lambda t=target: gr.Tabs(selected=t), None, tabs)

        # ---- first load: reopen the last project
        def on_load():
            series, ep = current()
            base = [project_html(), progress_html()]
            job = JOBS.job
            seen_now = {"count": JOBS.finished_count if job and job.rep.finished else -1, "ver": ""}
            if series is None:
                return base + [gr.skip()] * (len(settings) + 6) + [1, 1, 1, 1, seen_now]
            o = ep.load_options()
            voices = series.data.get("voices", {})
            return (base + opts_to_values(o)
                    + [voices.get("en", "kokoro:am_fenrir"), voices.get("fa", "edge:fa-IR-FaridNeural"),
                       series.data.get("caption_accent", "yellow"),
                       gr.update(choices=series_choices(), value=series.slug if series.slug != "quick-test" else NEW),
                       ep.number, gr.update(visible=series.slug == "quick-test")]
                    + [1, 1, 1, 1, seen_now])

        demo.load(on_load, None, [project_box, progress_box] + settings
                  + [voice_en, voice_fa, accent, series_dd, ep_no, new_name] + refreshers + [seen])
    return demo


# ---------------------------------------------------------------------------
# Launch (Colab: built-in link by default, optional public link for your phone)
# ---------------------------------------------------------------------------


def launch(public_link: bool = False, root: str | None = None, port: int = 7860, block: bool = True,
           cache_big_models_on_drive: bool = False):
    s = config.init(root=root, cache_big_models_on_drive=cache_big_models_on_drive)
    found = config.load_secrets()
    print(f"✅ StoryForge {s.platform} · {s.gpu.label} · saving to {s.root}")
    print("🔑 Free keys found: " + (", ".join(k for k, v in found.items() if v) or "none (that's OK)"))
    if s.platform == "colab" and not s.drive_mounted:
        print("⚠️ Google Drive is not mounted: projects will be lost when Colab closes. Run the Setup cell again.")
    demo = build_app()
    demo.queue(default_concurrency_limit=4)
    kwargs = dict(theme=build_theme(), css=CSS, head=HEAD, allowed_paths=[str(s.root), str(config.ASSETS_DIR),
                  str(config.local_cache_dir(s.platform))], show_error=True, quiet=True, footer_links=[])
    use_share = public_link or s.platform == "kaggle"
    try:
        demo.launch(server_name="0.0.0.0" if s.platform != "local" else "127.0.0.1", server_port=port,
                    share=use_share, inline=False, prevent_thread_lock=True, **kwargs)
    except TypeError:  # older Gradio without some options
        kwargs.pop("footer_links", None)
        demo.launch(server_port=port, share=use_share, inline=False, prevent_thread_lock=True, **kwargs)
    _show_links(demo, s.platform, port, use_share)
    if block:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("👋 StoryForge stopped. Run the Launch cell again to restart.")
            demo.close()
    return demo


def _show_links(demo, platform: str, port: int, shared: bool) -> None:
    print("")
    if platform == "colab":
        try:
            from google.colab import output  # type: ignore  # noqa: PLC0415

            output.serve_kernel_port_as_window(port, anchor_text="👉 OPEN STORYFORGE (click here)")
            print("☝️ Click the link above to open the app in a new tab (keep this Colab tab open).")
        except Exception as exc:  # noqa: BLE001
            print(f"Couldn't make the Colab link ({exc}).")
    else:
        print(f"👉 Open http://localhost:{port}")
    if shared and getattr(demo, "share_url", None):
        print(f"📱 Public link (works on your phone, valid for about a week): {demo.share_url}")
        print("   Anyone with this link can use your app while it runs. Don't share it.")
    elif shared:
        print("📱 The public link couldn't be created right now. Use the link above instead.")
