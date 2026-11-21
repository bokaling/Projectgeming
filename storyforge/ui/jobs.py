"""Runs one long task at a time in the background.

The web page asks for progress every second, so closing or reloading the page
never stops the work, and the log is also printed in the Colab cell.
"""

from __future__ import annotations

import threading
from typing import Callable

from ..messages import Reporter

ALL = ("script", "chars", "scenes", "export")


class Job:
    def __init__(self, name: str, fn: Callable[[Reporter], object], goto: str | None, refresh=ALL):
        self.name = name
        self.fn = fn
        self.goto = goto
        self.refresh = tuple(refresh)
        self.rep = Reporter(echo=True)
        self.thread: threading.Thread | None = None


class JobManager:
    def __init__(self):
        self.job: Job | None = None
        self.finished_count = 0
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self.job is not None and not self.job.rep.finished

    def start(self, name: str, fn, goto: str | None = None, refresh=ALL) -> tuple[bool, str]:
        with self._lock:
            if self.busy:
                return False, f"Please wait: “{self.job.name}” is still running (or press Stop)."
            job = Job(name, fn, goto, refresh)
            self.job = job
            job.thread = threading.Thread(target=self._run, args=(job,), daemon=True, name=f"sf-{name}")
            job.thread.start()
        return True, f"Started: {name}"

    def _run(self, job: Job) -> None:
        try:
            result = job.fn(job.rep)
            if not job.rep.finished:
                job.rep.done(result, f"{job.name}: done!")
        except BaseException as exc:  # noqa: BLE001 - always report, never crash the app
            job.rep.fail(exc)
        finally:
            with self._lock:
                self.finished_count += 1

    def stop(self) -> str:
        if not self.busy:
            return "Nothing is running."
        self.job.rep.request_stop()
        return "Stopping after the current step… (finished work is kept)"


JOBS = JobManager()
