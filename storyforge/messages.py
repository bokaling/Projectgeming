"""Progress messages and friendly error messages.

Every long task gets a `Reporter`. The web app reads it to draw the progress
bar and log; the forms mode just prints it.
"""

from __future__ import annotations

import contextlib
import errno
import threading
import time
import traceback


class FriendlyError(Exception):
    """An error with a plain-English explanation and a next step for the user."""

    def __init__(self, what: str, todo: str = ""):
        super().__init__(what)
        self.what = what
        self.todo = todo

    def __str__(self) -> str:
        return f"{self.what} {self.todo}".strip()


class StopRequested(Exception):
    """The user pressed Stop."""


def explain(exc: BaseException) -> tuple[str, str]:
    """Turn any exception into (what happened, what to do)."""
    if isinstance(exc, FriendlyError):
        return exc.what, exc.todo
    if isinstance(exc, StopRequested):
        return "Stopped.", "Your finished work is saved. Press the button again to continue."
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()
    if "out of memory" in low or "outofmemory" in low or "cuda oom" in low:
        return (
            "The GPU ran out of memory.",
            "In Colab click Runtime → Restart session, then run the Launch cell again. "
            "Finished scenes are saved, so you only lose the current one.",
        )
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC or "no space left" in low:
        return (
            "The disk is full.",
            "Delete old episodes in Google Drive (MyDrive/StoryForge/series) or empty the Drive trash, then try again.",
        )
    if isinstance(exc, FileNotFoundError) and "ffmpeg" in low:
        return "FFmpeg is not installed.", "Run the Setup cell again."
    if ("401" in low or "403" in low) and ("huggingface" in low or "hf.co" in low) or "gated repo" in low:
        return (
            "A model download was refused (it may need you to accept its license).",
            "Open the model page on huggingface.co, click 'Agree', create a free token, "
            "and save it in Colab Secrets as HF_TOKEN.",
        )
    if "connection" in low or "timed out" in low or "timeout" in low or "name resolution" in low:
        return "Could not reach an online service.", "Check your internet, wait a minute, and press the button again."
    if "cuda" in low and ("driver" in low or "device-side" in low or "illegal memory" in low):
        return (
            "The GPU had a problem.",
            "Click Runtime → Restart session in Colab, then run the Launch cell again.",
        )
    if isinstance(exc, ModuleNotFoundError):
        return f"A Python package is missing ({exc.name}).", "Run the Setup cell again."
    return f"Something went wrong ({type(exc).__name__}: {str(exc)[:160]}).", (
        "Press the button again (finished work is kept). If it keeps happening, restart the session."
    )


class Reporter:
    """Collects progress for one job. Thread safe."""

    MAX_LINES = 400

    def __init__(self, echo: bool = True):
        self.echo = echo
        self.lines: list[str] = []
        self.fraction = 0.0
        self.label = ""
        self.started = time.time()
        self.finished = False
        self.failed = False
        self.result = None
        self.summary: list[tuple[str, str, str]] = []  # (status, part, detail) for Quick test checklist
        self.timings: list[tuple[str, float]] = []  # (step, seconds) for the timing report
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.version = 0

    # -- writing ------------------------------------------------------------
    def _add(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)
            if len(self.lines) > self.MAX_LINES:
                self.lines = self.lines[-self.MAX_LINES:]
            self.version += 1
        if self.echo:
            print(line, flush=True)

    def step(self, title: str) -> None:
        self._add(f"\n▶ {title}")
        with self._lock:
            self.label = title

    def info(self, msg: str) -> None:
        self._add(f"   {msg}")

    def ok(self, msg: str) -> None:
        self._add(f"   ✅ {msg}")

    def warn(self, msg: str) -> None:
        self._add(f"   ⚠️ {msg}")

    def error(self, what: str, todo: str = "") -> None:
        self._add(f"   ❌ {what}")
        if todo:
            self._add(f"   👉 {todo}")

    def progress(self, fraction: float, label: str | None = None) -> None:
        with self._lock:
            self.fraction = max(0.0, min(1.0, float(fraction)))
            if label:
                self.label = label
            self.version += 1

    def record(self, status: str, part: str, detail: str = "") -> None:
        """Add a line to the end-of-job checklist (status: ok / warn / fail)."""
        with self._lock:
            self.summary = [s for s in self.summary if s[1] != part] + [(status, part, detail)]
            self.version += 1

    @contextlib.contextmanager
    def timed(self, name: str):
        """`with rep.timed("🖼️ Pictures"):` adds the step's time to the timing report."""
        t0 = time.time()
        try:
            yield
        finally:
            with self._lock:
                self.timings.append((name, time.time() - t0))

    def timed_lock(self):
        return self._lock

    def timing_report(self, total: float | None = None) -> list[str]:
        """Lines like '🖼️ Pictures ........ 2:10'."""
        with self._lock:
            items = list(self.timings)
        if not items:
            return []
        width = max(len(n) for n, _ in items) + 2
        lines = [f"{n.ljust(width, '.')} {_mmss(sec)}" for n, sec in items]
        if total is not None:
            lines.append(f"{'⏱ Total'.ljust(width, '.')} {_mmss(total)}")
        return lines

    # -- control ------------------------------------------------------------
    def request_stop(self) -> None:
        self._stop.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def check_stop(self) -> None:
        if self._stop.is_set():
            raise StopRequested()

    def fail(self, exc: BaseException) -> None:
        what, todo = explain(exc)
        self.error(what, todo)
        if not isinstance(exc, (FriendlyError, StopRequested)):
            # keep the technical details in the log, below the friendly text
            tb = traceback.format_exception(type(exc), exc, exc.__traceback__)[-3:]
            self._add("   (details: " + " ".join(t.strip().replace("\n", " ") for t in tb)[:600] + ")")
        with self._lock:
            self.failed = True
            self.finished = True
            self.version += 1

    def done(self, result=None, message: str = "") -> None:
        if message:
            self._add(f"\n🎉 {message}")
        with self._lock:
            self.result = result
            self.fraction = 1.0
            self.finished = True
            self.version += 1

    # -- reading ------------------------------------------------------------
    def text(self, last: int = 60) -> str:
        with self._lock:
            return "\n".join(self.lines[-last:]).strip("\n")

    def elapsed(self) -> str:
        sec = int(time.time() - self.started)
        return f"{sec // 60}:{sec % 60:02d}"


def _mmss(sec: float) -> str:
    sec = max(0.0, float(sec))
    return f"{sec:.1f} s" if sec < 10 else (f"{sec:.0f} s" if sec < 60 else f"{int(sec // 60)}:{int(sec % 60):02d}")


class Timer:
    """`with Timer() as t: ...` then `t.label` gives '14 s' or '2 min 3 s'."""

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *exc):
        self.seconds = time.time() - self.start
        return False

    @property
    def label(self) -> str:
        sec = getattr(self, "seconds", time.time() - self.start)
        if sec < 60:
            return f"{sec:.0f} s"
        return f"{int(sec // 60)} min {int(sec % 60)} s"
