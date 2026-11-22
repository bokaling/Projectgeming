"""What the app shows while something runs: the progress panel, the live step checklist, a short clean log,
status badges, toasts and error boxes. Plain functions of the job's Reporter, so they are easy to test."""

from __future__ import annotations

import html
import re
import time

from .. import config

# (key, label, words in a "▶ step" line that start it)
STEPS = [
    ("script", "📝 Writing script", ("Writing the script", "Reading your script")),
    ("plan", "🧭 Planning scenes", ("Scene plan",)),
    ("voice", "🗣️ Voiceover", ("Voiceover",)),
    ("world", "🏗️ Building world", ("Quality check", "One still frame", "Fixing shot")),
    ("render", "🎬 Rendering shots", ("3D render",)),
    ("sound", "🎵 Sound", ("Music and sound",)),
    ("review", "🧐 Self-review", ("Self-review",)),
    ("export", "📦 Exporting", ("Thumbnail",)),
]
ICONS = {"waiting": "⏳", "running": "🔄", "done": "✅", "failed": "❌", "skipped": "⏭️"}
NOISE = re.compile(r"Traceback|Warning:|warnings\.warn|^\s*File \"|DeprecationWarning|UserWarning|FutureWarning|"
                   r"^\s*\^+\s*$|site-packages", re.I)
TOASTS = [
    (re.compile(r"Script ready"), "📝 Script ready"),
    (re.compile(r"Plan by"), "🧭 Scene plan ready"),
    (re.compile(r"joined without re-encoding"), "🎬 Video saved to Drive"),
    (re.compile(r"Shot (\d+) changed"), "🔧 Shot {0} fixed"),
    (re.compile(r"shots reviewed"), "🧐 Self-review done"),
    (re.compile(r"The plan is ready"), "🧭 Plan ready: check the shots"),
]


def step_lines(rep) -> list[str]:
    return [ln.strip()[2:].strip() for ln in rep.lines if ln.strip().startswith("▶")]


def checklist(rep) -> list[tuple[str, str]]:
    """[(label, state)] in pipeline order. state: waiting, running, done, failed, skipped."""
    seen = []
    for title in step_lines(rep):
        for key, _, words in STEPS:
            if any(w.lower() in title.lower() for w in words) and key not in seen:
                seen.append(key)
    out = []
    last = seen[-1] if seen else None
    for key, label, _ in STEPS:
        if key not in seen:
            state = "skipped" if rep.finished and not rep.failed and seen else "waiting"
        elif key == last and not rep.finished:
            state = "running"
        elif key == last and rep.failed:
            state = "failed"
        else:
            state = "done"
        out.append((label, state))
    return out


def friendly_step(rep) -> str:
    """'3D render 4/13' → 'Rendering shot 4 of 13'; step titles → short plain names."""
    label = rep.label or ""
    m = re.search(r"3D render (\d+)/(\d+)", label)
    if m:
        return f"🎬 Rendering shot {m.group(1)} of {m.group(2)}"
    for key, name, words in STEPS:
        if any(w.lower() in label.lower() for w in words):
            return name
    return label.split("(")[0].strip() or "Working…"


def clean_log(rep, n: int = 10) -> list[str]:
    """The last n lines in plain English (no Python warnings or tracebacks)."""
    lines = [ln.rstrip() for ln in rep.lines if ln.strip() and not NOISE.search(ln)]
    return [ln.strip() for ln in lines[-n:]]


def error_of(rep) -> tuple[str, str]:
    what = todo = ""
    for k, ln in enumerate(rep.lines):
        if "❌" in ln:
            what = ln.strip().lstrip("❌").strip()
            nxt = rep.lines[k + 1].strip() if k + 1 < len(rep.lines) else ""
            todo = nxt.lstrip("👉").strip() if nxt.startswith("👉") else ""
    return what, todo


def eta_text(rep) -> str:
    sec = time.time() - rep.started
    f = rep.fraction
    if rep.finished or f < 0.04:
        return ""
    left = sec * (1 - f) / f
    return f"about {int(left // 60)} min {int(left % 60):02d} s left" if left >= 60 else f"about {int(left)} s left"


def panel(job) -> str:
    """The progress panel at the top: step, bar, %, time passed and left, checklist, short log."""
    if job is None:
        return ('<div class="sf-progress idle"><div class="sf-progress-top"><span>✨ Ready</span>'
                '<span class="sf-progress-pct"></span></div><div class="sf-bar"><div class="sf-fill" style="width:0%">'
                '</div></div><div class="sf-progress-sub">Nothing is running. Type a topic or paste a script, then press '
                '🚀.</div></div>')
    rep = job.rep
    pct = 100 if rep.finished and not rep.failed else int(round(rep.fraction * 100))
    if rep.failed:
        cls, title = "failed", f"❌ {html.escape(job.name)} stopped"
    elif rep.finished:
        cls, title = "done", f"✅ {html.escape(job.name)}: done"
    else:
        cls, title = "", f"{html.escape(friendly_step(rep))}"
    times = f"⏱ {rep.elapsed()}" + (f" · {eta_text(rep)}" if eta_text(rep) else "")
    chips = "".join(f'<span class="sf-step {state}">{ICONS[state]} {html.escape(label)}</span>'
                    for label, state in checklist(rep))
    err = ""
    if rep.failed:
        what, todo = error_of(rep)
        err = (f'<div class="sf-error"><b>❌ {html.escape(what or "Something went wrong.")}</b>'
               + (f'<br>👉 {html.escape(todo)}' if todo else "") + "</div>")
    done = ""
    if rep.finished and not rep.failed and isinstance(rep.result, dict) and rep.result.get("videos"):
        done = '<div class="sf-donebox">🎉 Your video is ready: see step 4 · 🎬 Export (it is saved in Google Drive).</div>'
    log = "".join(f"<div>{html.escape(ln[:150])}</div>" for ln in clean_log(rep))
    return (f'<div class="sf-progress {cls}"><div class="sf-progress-top"><span>{title}</span>'
            f'<span class="sf-progress-pct">{pct}%</span></div>'
            f'<div class="sf-bar"><div class="sf-fill" style="width:{pct}%;height:10px;'
            f'background:linear-gradient(90deg,#ff2e97,#a855f7,#7c3aed)"></div></div>'
            f'<div class="sf-progress-sub">{times}</div><div class="sf-steps-live">{chips}</div>{err}{done}'
            f'<div class="sf-minilog">{log}</div></div>')


def badges() -> str:
    """GPU, keys, Drive and compute units used this session."""
    s = config.get()
    prof = config.gpu_profile()
    gem = bool(config.secret("GEMINI_API_KEY"))
    hf = bool(config.secret("HF_TOKEN"))
    drive = s.drive_mounted or s.platform != "colab"
    gpu = s.gpu.name if s.gpu.available else "CPU (no GPU)"
    units = re.search(r"≈\s*([\d.]+)\s*(?:compute )?units", config.session_label() or "")
    chips = [
        ("ok" if s.gpu.available else "warn", f"⚡ {html.escape(gpu)}"),
        ("ok" if gem else "bad", f"Gemini key {'✅' if gem else '❌'}"),
        ("ok" if hf else "warn", f"HF token {'✅' if hf else '❌'}"),
        ("ok" if drive else "bad", f"Drive {'✅' if drive else '❌'}"),
        ("", f"🧮 {units.group(1) if units else '0'} units this session · {prof.name}"),
    ]
    return '<div class="sf-badges">' + "".join(f'<span class="sf-chip {c}">{t}</span>' for c, t in chips) + "</div>"


def new_toasts(rep, seen_lines: int) -> tuple[list[str], int]:
    """Toast messages for important new log lines since the last check."""
    out = []
    lines = rep.lines[seen_lines:] if seen_lines <= len(rep.lines) else rep.lines
    for ln in lines:
        for rx, msg in TOASTS:
            m = rx.search(ln)
            if m:
                out.append(msg.format(*m.groups()))
    return out, len(rep.lines)
