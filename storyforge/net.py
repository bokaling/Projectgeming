"""One place for every internet call: retries, backoff, provider fallback, usage log.

If a free service is busy (HTTP 429), out of free quota (402) or broken (5xx),
we wait a little and retry, then move on to the next service in the list.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Callable

from . import config
from .project import read_json, write_json

USER_AGENT = "StoryForge/1.0 (free story video maker)"
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 522, 524}


class ServiceError(Exception):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class AllProvidersFailed(Exception):
    def __init__(self, task: str, errors: list[tuple[str, str]]):
        self.task = task
        self.errors = errors
        detail = "; ".join(f"{name}: {err}" for name, err in errors)
        super().__init__(f"All services failed for {task}: {detail}")


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def request(
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff: float = 2.0,
    timeout: float = 60,
    max_wait: float = 30,
    **kwargs,
):
    """requests.request with retries. Raises ServiceError on failure."""
    import requests  # noqa: PLC0415

    headers = {"User-Agent": USER_AGENT, **(kwargs.pop("headers", None) or {})}
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last = ServiceError(f"network problem ({type(exc).__name__})", None, True)
        else:
            if resp.status_code < 400:
                return resp
            body = (resp.text or "")[:200].replace("\n", " ")
            retryable = resp.status_code in RETRY_STATUS
            last = ServiceError(f"HTTP {resp.status_code} {body}", resp.status_code, retryable)
            if not retryable:
                raise last
            wait_hdr = resp.headers.get("Retry-After")
            if wait_hdr and wait_hdr.replace(".", "", 1).isdigit():
                wait = float(wait_hdr)
                if wait > max_wait:  # a long ban: give up on this provider now
                    raise last
                if attempt < retries:
                    _sleep(wait)
                    continue
        if attempt < retries:
            _sleep(min(max_wait, backoff * (2**attempt)))
    assert last is not None
    raise last


def try_in_order(task: str, providers: list[tuple[str, Callable[[], object]]], rep=None):
    """Run providers one after another until one works. Returns (provider_name, result)."""
    errors: list[tuple[str, str]] = []
    for name, fn in providers:
        if rep is not None:
            rep.check_stop()
        try:
            result = fn()
            log_usage(name)
            return name, result
        except Exception as exc:  # noqa: BLE001 - we really want to try the next one
            from .messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            msg = str(exc)[:160] or type(exc).__name__
            errors.append((name, msg))
            if rep is not None:
                rep.info(f"↪ {name} didn't work ({msg[:90]}). Trying the next one…")
    raise AllProvidersFailed(task, errors)


def log_usage(provider: str) -> None:
    """Count calls per provider per day in StoryForge/usage.json (helps you see free limits)."""
    try:
        path = config.get().root / "usage.json"
        data = read_json(path, {}) or {}
        today = data.setdefault(date.today().isoformat(), {})
        today[provider] = today.get(provider, 0) + 1
        for old in sorted(data)[:-14]:  # keep two weeks
            data.pop(old, None)
        write_json(path, data)
    except Exception:
        pass


def download(url: str, dest, *, timeout: float = 120, retries: int = 2, **kwargs) -> None:
    from pathlib import Path  # noqa: PLC0415

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = request("GET", url, timeout=timeout, retries=retries, stream=True, **kwargs)
    tmp = dest.with_name(dest.name + ".part")
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)
    tmp.replace(dest)
