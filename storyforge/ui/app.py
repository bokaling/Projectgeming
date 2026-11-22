"""The StoryForge web app: 3D explainer videos. Topic & Script → Scene plan → Voice & Sound → Export."""

from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

from .. import config, doctor, pipeline
from .. import script as script_mod
from ..audio import music, tts
from ..messages import FriendlyError, explain
from ..project import EpisodeOptions, Series, list_series, read_json, slugify, write_json
from .jobs import JOBS
from .theme import CSS, HEAD, build_theme

NEW = "__new__"
TAB_IDS = ["script", "plan", "voice", "export"]
LANG_CHOICES = [("English", "en"), ("Farsi · فارسی", "fa")]
MOOD_CHOICES = [("Auto (from the script)", "auto")] + [(m.title(), m) for m in
                                                        ("mysterious", "tense", "hopeful", "epic", "calm", "dark", "action")]


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


def keys_html() -> str:
    """Which free keys the app found and what each one turns on."""
    rows = []
    for name, status, what in config.key_report():
        icon = {"found": "✅", "no_access": "⚠️"}.get(status, "➖")
        note = {"found": "found", "no_access": "in Secrets, but Notebook access is OFF"}.get(status, "not set")
        rows.append(f'<tr><td>{icon} <code>{name}</code></td><td>{note}</td><td>{html.escape(what)}</td></tr>')
    return ('<div class="sf-doctor"><table style="width:100%;font-size:13px">' + "".join(rows) + "</table>"
            '<div class="sf-note">Add keys in Colab: 🔑 Secrets (left bar) → name + value → Notebook access ON. '
            'Then run cell 2️⃣ again (Colab only shares secrets when that cell starts).</div></div>')


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


def opts_from(text, idea, note, langs, length, res, cap_on, mood, vol, sfx, end_card, final, qc,
              source="paste") -> EpisodeOptions:
    return EpisodeOptions.from_dict({
        "script_text": text or "", "idea": idea or "", "creator_note": note or "", "languages": langs or ["en"],
        "length": length, "resolution": res, "captions": bool(cap_on), "music_mood": mood, "music_volume": float(vol),
        "sfx": bool(sfx), "end_card": bool(end_card), "final_episode": bool(final), "quality_check": bool(qc),
        "source": source,
    })


def opts_to_values(o: EpisodeOptions):
    return [o.script_text, o.idea, o.creator_note, o.languages, o.length, o.resolution, o.captions, o.music_mood,
            o.music_volume, o.sfx, o.end_card, o.final_episode, o.quality_check]


def add_style_line(text: str, style: str) -> str:
    """Put a [STYLE] line in the first script, after its [TITLE] line."""
    lines = (text or "").split("\n")
    at = 0
    for i, ln in enumerate(lines):
        if re.match(r"\s*\[(TITLE|CHARACTER)\]", ln, re.I):
            at = i + 1
        elif ln.strip() and not ln.strip().startswith("["):
            break
    return "\n".join(lines[:at] + [f"[STYLE] {style}"] + lines[at:])


def split_scripts(text: str) -> list[str]:
    from .. import paste  # noqa: PLC0415

    return paste.split_scripts(text or "")


SCRIPT_PLACEHOLDER = """[TITLE] How Cow Poop Becomes Electricity
[SCENE] wide shot of a dairy barn full of cows
NARRATOR: This farm runs 150 homes on cow poop.
[SCENE] close on the cows, manure piles up in the alley
NARRATOR: Its 2,000 cows make 130 tons of manure. Every single day.

(Or type a topic above and press ✍️ Write the script.
Several videos at once: separate the scripts with a line of =====)"""


def plan_scene_html(plan: dict, i: int, tl: dict | None) -> str:
    """One scene of the plan in plain words."""
    from ..world import plan as P  # noqa: PLC0415

    sub = {**plan, "scenes": [plan["scenes"][i]]}
    text = P.summary(sub, {"scenes": [tl["scenes"][i]]} if tl and i < len(tl.get("scenes", [])) else None)
    lines = text.split("\n")[2:]  # drop the title + world lines
    out = []
    for ln in lines:
        ln = html.escape(ln).replace("**Scene 1**", f"<b>Scene {i + 1}</b>")
        ln = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", ln)
        out.append(ln[2:] if ln.startswith("- ") else ln)
    return '<div class="sf-doctor">' + "<br>".join(x for x in out if x.strip()) + "</div>"


def build_app():
    import gradio as gr  # noqa: PLC0415

    config.get()
    music.ensure_library_readme()
    default_opts = EpisodeOptions()

    with gr.Blocks(title="StoryForge · 3D explainer videos") as demo:
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

        r_script, r_plan, r_export = gr.State(0), gr.State(0), gr.State(0)
        seen = gr.State({"count": -1, "ver": ""})

        with gr.Tabs(elem_classes="sf-steps", selected="script") as tabs:
            # ------------------------------------------------------------ 1 Topic & Script
            with gr.Tab("1 · 💡 Topic & Script", id="script"):
                with gr.Row(elem_classes="sf-row-stack", equal_height=False):
                    with gr.Column(scale=3):
                        with gr.Group(elem_classes=["sf-card", "sf-hero-card"]):
                            gr.HTML('<div class="sf-card-title">What should the video explain?</div>'
                                    '<div class="sf-card-sub">How things work, what happens if, how things are made, '
                                    'inside machines, science, engineering, history of inventions.</div>')
                            idea = gr.Textbox(show_label=False, lines=2, placeholder="e.g. how cow poop becomes "
                                              "electricity   (several topics? put ===== between them)")
                            write_btn = gr.Button("✍️ Write the script (free AI, retention rules)", variant="secondary")
                        with gr.Group(elem_classes=["sf-card", "sf-hero-card"]):
                            gr.HTML('<div class="sf-card-title">Your script</div>'
                                    '<div class="sf-card-sub"><b>[TITLE]</b> title · <b>[STYLE]</b> look (optional) · '
                                    '<b>[SCENE]</b> what we see · <b>NARRATOR:</b> what is said. Paste your own or let '
                                    'the AI write it above. Several scripts? A line of <b>=====</b> between them.</div>')
                            paste_box = gr.Textbox(show_label=False, lines=16, max_lines=40,
                                                   placeholder=SCRIPT_PLACEHOLDER, elem_classes="sf-script")
                            length = gr.Radio([("⚡ Short · ~60 s · 9:16 · 1080×1920", "short"),
                                               ("🎬 Long · ~10 min · 16:9 · 1920×1080 · chapters", "long")],
                                              value=default_opts.length, show_label=False)
                        with gr.Group(elem_classes="sf-card"):
                            doctor_box = gr.HTML(doctor.report_html(doctor.Report()))
                            with gr.Row(elem_classes="sf-row-stack"):
                                improve_btn = gr.Button("✨ Improve script (for retention)", variant="secondary")
                                style_btn = gr.Button("🎨 Add this style as a [STYLE] line", variant="secondary",
                                                      visible=False)
                        with gr.Group(visible=False, elem_classes=["sf-card", "sf-hero-card"]) as cmp_box:
                            gr.HTML('<div class="sf-card-title">Your script or the improved one?</div>'
                                    '<div class="sf-card-sub">Nothing changes until you choose. The one you pick is '
                                    'what the scene plan and the video use. You can edit the improved one.</div>')
                            cmp_scores = gr.HTML()
                            with gr.Row(elem_classes="sf-row-stack", equal_height=False):
                                old_txt = gr.Textbox(label="Your script", lines=14, max_lines=40, interactive=False,
                                                     elem_classes="sf-script")
                                new_txt = gr.Textbox(label="✨ Improved (you can edit it)", lines=14, max_lines=40,
                                                     elem_classes="sf-script")
                            cmp_notes = gr.HTML()
                            with gr.Row(elem_classes="sf-row-stack"):
                                use_new = gr.Button("✅ Use the improved script", variant="primary")
                                keep_old = gr.Button("↩️ Keep my original", variant="secondary")
                        with gr.Row(elem_classes="sf-row-stack"):
                            gen_btn = gr.Button("🚀 Make the video", variant="primary", size="lg", scale=2)
                            plan_btn = gr.Button("🧭 Plan first (see every shot)", variant="secondary", size="lg",
                                                 scale=1)
                        quick_btn = gr.Button("⚡ Quick test (3 scenes, 720p)", variant="secondary")
                        gr.HTML('<div class="sf-note">🚀 does everything: scene plan, voice, 3D render, captions, '
                                'music, export, thumbnail, title, description. 🧭 makes the plan and one still frame per '
                                'shot first, so you can fix shots before the render.</div>')
                        note = gr.Textbox(label="Creator note (optional): your recap, question or comment for viewers",
                                          lines=2)
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Series &amp; episode</div>'
                                    '<div class="sf-card-sub">Same series = same voice, numbering and end card.</div>')
                            series_dd = gr.Dropdown(choices=series_choices(), value=NEW, label="Series")
                            new_name = gr.Textbox(label="New series name", placeholder="e.g. How Things Work")
                            ep_no = gr.Number(value=1, precision=0, minimum=1, label="Episode number")
                            open_btn = gr.Button("📂 Open this episode", variant="secondary")
                        with gr.Group(elem_classes="sf-card"):
                            langs = gr.CheckboxGroup(LANG_CHOICES, value=default_opts.languages,
                                                     label="Language (detected from your script)")
                            res = gr.Radio([("1080p (best)", "1080p"), ("720p (faster)", "720p")],
                                           value=default_opts.resolution, label="Quality")
                            qc_cb = gr.Checkbox(value=True, label="🔍 Quality check: look at one still frame per shot and "
                                                                  "fix broken ones (Gemini vision with a free key; switched on "
                                                                  "in the next update)")
                        with gr.Accordion("🔑 Free keys: what the app found", open=False):
                            gr.HTML(keys_html())
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">End</div>')
                            end_cb = gr.Checkbox(value=True, label="👀 End card: “Part X 👀” (X = the next episode)")
                            final_cb = gr.Checkbox(value=False, label="🏁 Final episode: the end card says “The End”")

            # ------------------------------------------------------------ 2 Scene plan
            with gr.Tab("2 · 🧭 Scene plan", id="plan"):
                with gr.Group(elem_classes="sf-card"):
                    gr.HTML('<div class="sf-card-title">The 3D world, shot by shot</div>'
                            '<div class="sf-card-sub">One still frame per shot (from the middle of the shot). Type what to '
                            'change under a shot and press 🔧: only that shot is planned and rendered again.</div>')
                    plan_info = gr.HTML()

                @gr.render(inputs=[r_plan])
                def plan_cards(_):
                    series, ep = current()
                    plan = ep.load_plan() if ep else None
                    sc = ep.load_script() if ep else None
                    if not plan or not sc:
                        gr.HTML('<div class="sf-empty">Press <b>🧭 Plan first</b> on step 1 to see every shot here.</div>')
                        return
                    o = ep.load_options()
                    fmt = o.formats[0]
                    tl = read_json(ep.audio_dir(o.languages[0]) / "timeline.json", None)
                    with gr.Row(elem_classes="sf-grid"):
                        for i, s in enumerate(sc["scenes"]):
                            if i >= len(plan["scenes"]):
                                break
                            still = ep.still_path(s["id"], fmt)
                            with gr.Column(elem_classes="sf-scene", min_width=240):
                                gr.Image(value=str(still) if still.exists() else None, show_label=False, height=300,
                                         interactive=False, buttons=["fullscreen"], placeholder="No still frame yet")
                                gr.HTML(plan_scene_html(plan, i, tl))
                                fix_box = gr.Textbox(show_label=False, lines=1,
                                                     placeholder="e.g. make the tank bigger / show the gas flowing")
                                fix_btn = gr.Button("🔧 Fix this shot", size="sm", variant="secondary")

                                def _fix(instr, k=i):
                                    return on_fix(k, instr)

                                fix_btn.click(_fix, fix_box, [progress_box])

                with gr.Accordion("⚙️ Advanced: the plan as JSON (edit and save)", open=False):
                    plan_json = gr.Code(language="json", lines=20, show_label=False)
                    save_plan_btn = gr.Button("💾 Check and save the plan", variant="secondary")
                with gr.Row(elem_classes="sf-row-stack"):
                    make_btn = gr.Button("🚀 Make the video with this plan", variant="primary", size="lg")

            # ------------------------------------------------------------ 3 Voice & Sound
            with gr.Tab("3 · 🎙️ Voice & Sound", id="voice"):
                with gr.Row(elem_classes="sf-row-stack", equal_height=False):
                    with gr.Column():
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Narrator</div>'
                                    '<div class="sf-card-sub">Saved for the whole series. Speaks at 1.1× with a short '
                                    'pause before reveals; every shot lasts exactly as long as its line.</div>')
                            voice_en = gr.Dropdown(tts.voice_choices("en"), value="kokoro:am_fenrir",
                                                   label="Narrator voice · English")
                            voice_fa = gr.Dropdown(tts.voice_choices("fa"), value="edge:fa-IR-FaridNeural",
                                                   label="Narrator voice · Farsi")
                            gr.HTML(f'<div class="sf-warn">⚠️ {html.escape(tts.EDGE_WARNING)}</div>')
                            preview_lang = gr.Radio(LANG_CHOICES, value="en", label="Preview language")
                            preview_btn = gr.Button("🔊 Preview voice", variant="secondary")
                            preview_audio = gr.Audio(show_label=False, interactive=False)
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">🎙️ Your own voice</div>'
                                    '<div class="sf-card-sub">Record the whole episode in order and upload one file. '
                                    'It is cut into shots and the timing follows your words.</div>')
                            own_en = gr.File(label="My English recording", file_types=["audio"], type="filepath", height=130)
                            own_fa = gr.File(label="My Farsi recording", file_types=["audio"], type="filepath", height=130)
                    with gr.Column():
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Captions</div>'
                                    '<div class="sf-card-sub">Small keywords at the top, only the important words: '
                                    '<span style="color:#ff5c5c">red</span> problems, '
                                    '<span style="color:#ffaa3c">orange</span> parts, white numbers.</div>')
                            cap_on = gr.Checkbox(value=True, label="Show keyword captions")
                        with gr.Group(elem_classes="sf-card"):
                            gr.HTML('<div class="sf-card-title">Music &amp; sound</div>'
                                    '<div class="sf-card-sub">Made by the app (no copyright claims). Soft only: nothing '
                                    'above 8 kHz, -14 LUFS. Your own tracks: Drive → StoryForge/library/music/&lt;mood&gt;/.</div>')
                            mood = gr.Dropdown(MOOD_CHOICES, value="auto", label="Music mood")
                            vol = gr.Slider(0, 0.4, value=default_opts.music_volume, step=0.01,
                                            label="Music volume (it also ducks under the voice)")
                            sfx = gr.Checkbox(value=True, label="Sounds: whoosh on camera moves, machine hums, bubbling, "
                                                                "sparks, low booms on reveals")

            # ------------------------------------------------------------ 4 Export
            with gr.Tab("4 · 🎬 Export", id="export"):
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
                    if res_.get("timings"):
                        rows = "".join(f"<tr><td>{html.escape(n)}</td><td style='text-align:right'>{s:.1f} s</td></tr>"
                                       for n, s in res_["timings"])
                        gr.HTML(f'<div class="sf-doctor"><b>⏱ Timing report</b><table style="width:100%">{rows}'
                                f'</table></div>')
                    if meta.exists():
                        with gr.Group(elem_classes="sf-card"):
                            gr.Markdown(meta.read_text(encoding="utf-8"))
                    gr.HTML(f'<div class="sf-note">📁 Saved in Google Drive: {html.escape(str(ep.export_dir))}</div>')
                    gr.HTML(usage_html(res_))

                with gr.Row(elem_classes="sf-row-stack"):
                    clean_btn = gr.Button("🧹 Free up Drive space (delete re-makeable shot clips)", variant="secondary")

        timer = gr.Timer(1.0)
        gr.Timer(20.0).tick(lambda: session_html(), None, session_box, show_progress="hidden")

        # ------------------------------------------------------------ wiring
        settings = [paste_box, idea, note, langs, length, res, cap_on, mood, vol, sfx, end_cb, final_cb, qc_cb]
        refreshers = [r_script, r_plan, r_export]

        def start_job(name, fn, goto=None, refresh=("script", "plan", "export")):
            ok, msg = JOBS.start(name, fn, goto, refresh)
            (gr.Info if ok else gr.Warning)(msg)
            return progress_html()

        def tick(seen_info, rs, rp, re_):
            job = JOBS.job
            if job is None:
                return [gr.skip()] * 7
            seen_info = seen_info if isinstance(seen_info, dict) else {"count": -1, "ver": ""}
            ver = f"{id(job)}:{job.rep.version}"
            done_now = JOBS.finished_count != seen_info["count"] and job.rep.finished
            if not done_now and ver == seen_info["ver"]:
                return [gr.skip()] * 7
            out = [progress_html(), job.rep.text(120)]
            if done_now:
                bump = lambda key, v: v + 1 if key in job.refresh else gr.skip()  # noqa: E731
                out += [bump("script", rs), bump("plan", rp), bump("export", re_)]
                out.append(gr.Tabs(selected=job.goto) if job.goto and not job.rep.failed else gr.skip())
                out.append({"count": JOBS.finished_count, "ver": ver})
                if job.rep.failed:
                    what = [ln for ln in job.rep.lines if "❌" in ln]
                    gr.Warning((what[-1].strip() if what else "Something went wrong.") + " See the log for what to do.")
            else:
                out += [gr.skip()] * 4 + [{"count": seen_info["count"], "ver": ver}]
            return out

        timer.tick(tick, [seen] + refreshers, [progress_box, log_box] + refreshers + [tabs, seen], show_progress="hidden")
        stop_btn.click(lambda: gr.Info(JOBS.stop()), None, None)
        r_script.change(lambda _: project_html(), r_script, project_box)

        def load_plan_json(_):
            _, ep = current()
            plan = ep.load_plan() if ep else None
            info = ""
            if plan and ep:
                st = ep.state.info("plan")
                fixes = st.get("fixes") or []
                info = (f'<div class="sf-note">🧭 Plan by <b>{html.escape(str(st.get("provider", "?")))}</b> · '
                        f'{len(plan["areas"])} areas · {sum(o["count"] for o in plan["objects"])} objects · '
                        f'{len(plan["scenes"])} shots' + (f' · 🔧 {len(fixes)} auto-fix(es)' if fixes else "") + "</div>")
            return (json.dumps(plan, indent=1, ensure_ascii=False) if plan else ""), info

        r_plan.change(load_plan_json, r_plan, [plan_json, plan_info])

        def resolve_series(choice, name) -> Series:
            if choice and choice != NEW:
                return Series(choice)
            name = (name or "").strip()
            if not name:
                raise FriendlyError("Give your series a name first.", "Type it in 'New series name' (right side).")
            return Series.create(name)

        def topic_or_script(o):
            if not (o.script_text or "").strip():
                if not (o.idea or "").strip():
                    raise FriendlyError("Paste a script or type a topic first.",
                                        "Type a topic and press ✍️ Write the script, or paste your own script.")
                o.source = "ai"
            return o

        def on_generate(choice, name, number, *vals):
            try:
                o = topic_or_script(opts_from(*vals))
                s = resolve_series(choice, name)
                n = int(number) if number else None
                set_current(s.slug, n or s.next_episode_number())
                return start_job("Making the video", lambda rep: pipeline.generate(s, o, o.script_text, rep, n),
                                 goto="export")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        gen_btn.click(on_generate, [series_dd, new_name, ep_no] + settings, [progress_box])

        def on_plan(choice, name, number, *vals):
            try:
                o = topic_or_script(opts_from(*vals))
                s = resolve_series(choice, name)
                n = int(number) if number else None
                set_current(s.slug, n or s.next_episode_number())
                return start_job("Planning the shots", lambda rep: pipeline.prepare(s, o, o.script_text, rep, n),
                                 goto="plan")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        plan_btn.click(on_plan, [series_dd, new_name, ep_no] + settings, [progress_box])

        def on_make():
            try:
                series, ep = need_project()
                return start_job("Making the video",
                                 lambda rep: pipeline.Pipeline(series, ep, rep, ep.load_options()).make_video(),
                                 goto="export")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        make_btn.click(on_make, None, [progress_box])

        def on_fix(k, instruction):
            try:
                series, ep = need_project()
                if not (instruction or "").strip():
                    raise FriendlyError("Type what to change first.", "For example: make the tank bigger.")
                return start_job(f"Fixing shot {k + 1}",
                                 lambda rep: pipeline.Pipeline(series, ep, rep, ep.load_options()).fix_scene(k, instruction),
                                 goto="plan", refresh=("plan", "export"))
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        def on_save_plan(text):
            try:
                series, ep = need_project()
                plan = json.loads(text or "{}")
                pipeline.Pipeline(series, ep, None, ep.load_options()).save_plan(plan)
                gr.Info("Saved. Press 🚀 Make the video with this plan (only changed shots are rendered again).")
                return int(time.time())
            except json.JSONDecodeError as exc:
                gr.Warning(f"That isn't valid JSON (line {exc.lineno}). Fix it or reload the page to start over.")
                return gr.skip()
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        save_plan_btn.click(on_save_plan, plan_json, r_plan)

        def on_quick(text, langs_, length_):
            return start_job("Quick test", lambda rep: pipeline.quick_test(rep, text or "", langs_ or ["en"], length_),
                             goto="export")

        quick_btn.click(on_quick, [paste_box, langs, length], [progress_box])

        def on_write(topic, length_, langs_, note_):
            try:
                if not (topic or "").strip():
                    raise FriendlyError("Type a topic first.", "For example: how cow poop becomes electricity.")
                gr.Info("✍️ Writing the script (10-40 s)…")
                text, provider = script_mod.write_from_topic(topic.split("=====")[0], length_, (langs_ or ["en"])[0],
                                                             note_ or "")
                gr.Info(f"Script written by {provider}. Check the doctor's score below, then press 🚀 or 🧭.")
                return text
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return gr.skip()

        write_btn.click(on_write, [idea, length, langs, note], paste_box)

        # ---- 🩺 Script doctor
        def on_score(text, length_):
            r = doctor.score(text or "", length_)
            return doctor.report_html(r), gr.update(visible=bool(r.words) and not r.has_style)

        paste_box.change(on_score, [paste_box, length], [doctor_box, style_btn], trigger_mode="always_last",
                         show_progress="hidden")
        length.change(on_score, [paste_box, length], [doctor_box, style_btn], show_progress="hidden")

        def on_style(text, length_):
            r = doctor.score(text or "", length_)
            gr.Info("🎨 Added the [STYLE] line.")
            return add_style_line(text, r.style_line)

        style_btn.click(on_style, [paste_box, length], paste_box)

        def on_improve(text, length_):
            if not (text or "").strip():
                gr.Warning("Paste your script first.")
                return [gr.skip()] * 5
            gr.Info("✨ Improving your script for retention (10-60 s)…")
            try:
                res_ = doctor.improve(text, length_)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return [gr.skip()] * 5
            first = (split_scripts(text) or [text])[0]
            old_r, new_r = doctor.score(first, length_), doctor.score(res_["script"], length_)
            notes = "".join(f"<li>{html.escape(c)}</li>" for c in res_["changes"])
            note_html = (f'<div class="sf-note">Rewritten by <b>{html.escape(res_["provider"])}</b>'
                         + (f'<ul style="margin:4px 0 0 18px">{notes}</ul>' if notes else "") + "</div>")
            return gr.update(visible=True), first, res_["script"], doctor.compare_html(old_r, new_r), note_html

        improve_btn.click(on_improve, [paste_box, length], [cmp_box, old_txt, new_txt, cmp_scores, cmp_notes])

        def on_use_new(new_text, text):
            parts = split_scripts(text)
            rest = ("\n=====\n" + "\n=====\n".join(parts[1:])) if len(parts) > 1 else ""
            gr.Info("✅ Using the improved script.")
            return new_text.strip() + "\n" + rest, gr.update(visible=False)

        use_new.click(on_use_new, [new_txt, paste_box], [paste_box, cmp_box])
        keep_old.click(lambda: gr.update(visible=False), None, cmp_box)

        # ---- open an episode / settings
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
                        + [voices.get("en", "kokoro:am_fenrir"), voices.get("fa", "edge:fa-IR-FaridNeural")]
                        + [int(time.time())] * 3)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return [gr.skip()] * (2 + len(settings) + 2 + 3)

        open_btn.click(on_open, [series_dd, new_name, ep_no],
                       [project_box, series_dd] + settings + [voice_en, voice_fa] + refreshers)

        def save_settings(*vals):
            series, ep = current()
            if ep is not None:
                ep.save_options(opts_from(*vals))

        for comp in settings:  # .input = only when YOU change it (not when the app fills it in)
            comp.input(save_settings, settings, None, show_progress="hidden")

        def save_voice(lang, value):
            series, _ep = current()
            if series is not None:
                series.data.setdefault("voices", {})[lang] = value
                series.save()

        voice_en.input(lambda v: save_voice("en", v), voice_en, None)
        voice_fa.input(lambda v: save_voice("fa", v), voice_fa, None)

        def on_preview(lang, ven, vfa):
            try:
                choice = tts.parse_voice(ven if lang == "en" else vfa, lang)
                choice["speed"] = 1.1
                out = config.get().temp_dir / f"preview_{lang}.wav"
                text = ("Inside this tank, trillions of bacteria are making electricity." if lang == "en"
                        else "درون این مخزن، میلیاردها باکتری برق می‌سازند.")
                if choice["engine"] == "own":
                    raise FriendlyError("Your own voice has no preview.", "Upload your recording below.")
                tts.speak(text, lang, choice, out)
                return str(out)
            except Exception as exc:  # noqa: BLE001
                _toast(exc)
                return None

        preview_btn.click(on_preview, [preview_lang, voice_en, voice_fa], preview_audio)

        def on_own(lang, file):
            try:
                series, ep = need_project()
                if not file:
                    return
                src = Path(file)
                dst = ep.audio_dir(lang) / f"own_voice{src.suffix.lower()}"
                for p in ep.audio_dir(lang).glob("own_voice.*"):
                    p.unlink(missing_ok=True)
                import shutil  # noqa: PLC0415

                shutil.copyfile(src, dst)
                series.data.setdefault("voices", {})[lang] = "own:own"
                series.save()
                gr.Info("Your recording is saved. The video will use it (the voice choice says 'My own recording').")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)

        own_en.upload(lambda f: on_own("en", f), own_en, None)
        own_fa.upload(lambda f: on_own("fa", f), own_fa, None)

        def on_clean():
            try:
                _, ep = need_project()
                mb = ep.cleanup_work_files()
                gr.Info(f"Freed {mb} MB. (They are re-made automatically if needed.)")
            except Exception as exc:  # noqa: BLE001
                _toast(exc)

        clean_btn.click(on_clean, None, None)

        # ---- first load: reopen the last project
        def on_load():
            series, ep = current()
            base = [project_html(), progress_html()]
            job = JOBS.job
            seen_now = {"count": JOBS.finished_count if job and job.rep.finished else -1, "ver": ""}
            if series is None:
                return base + [gr.skip()] * (len(settings) + 2 + 3) + [1, 1, 1, seen_now]
            o = ep.load_options()
            voices = series.data.get("voices", {})
            return (base + opts_to_values(o)
                    + [voices.get("en", "kokoro:am_fenrir"), voices.get("fa", "edge:fa-IR-FaridNeural"),
                       gr.update(choices=series_choices(), value=series.slug if series.slug != "quick-test" else NEW),
                       ep.number, gr.update(visible=series.slug == "quick-test")]
                    + [1, 1, 1, seen_now])

        demo.load(on_load, None, [project_box, progress_box] + settings
                  + [voice_en, voice_fa, series_dd, ep_no, new_name] + refreshers + [seen])
    return demo


def launch(public_link: bool = False, root: str | None = None, port: int = 7860, block: bool = True,
           cache_big_models_on_drive: bool = False):
    s = config.init(root=root, cache_big_models_on_drive=cache_big_models_on_drive)
    found = config.load_secrets()
    print(f"✅ StoryForge {s.platform} · {s.gpu.label} · saving to {s.root}")
    n = sum(found.values())
    print(f"🔑 Free keys found: {n}" + ("" if n else " (that's OK, everything still works)"))
    for line in config.key_lines():
        print(line)
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

            import contextlib  # noqa: PLC0415
            import io  # noqa: PLC0415

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):  # hide Colab's iframe notice
                output.serve_kernel_port_as_window(port, anchor_text="👉 OPEN STORYFORGE (click here)")
            for line in buf.getvalue().splitlines():
                if line.strip() and not config.NOISE.search(line) and "browser security" not in line:
                    print(line)
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
