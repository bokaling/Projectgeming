"""Free AI text providers with automatic fallback.

Order: Gemini's main Flash model (3 retries when it is busy: wait 5 s, 15 s, 30 s) → Gemini Flash-Lite
models → Groq → OpenRouter :free (only with your own free keys). Providers without a key are skipped.
The small local model is never used for scripts or scene plans (its plans were garbage). If every
provider fails, the planner uses the built-in planner and the script writer says "Gemini is busy".
"""

from __future__ import annotations

import json
import re
import threading

from . import config, net

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
GROQ_BASE = "https://api.groq.com/openai/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
GEMINI_WAITS = (5, 15, 30)  # seconds between retries when the main Gemini model says "busy" (HTTP 503/429/500)
LITE_WAITS = (5,)
BUSY = {"main": 0.0}  # time.time() when the main Gemini model last stayed busy after every retry

# Preferred model name patterns, best first. We read each provider's model list
# at run time, so new model versions are picked up automatically.
PREFER = {
    "gemini": [r"flash-lite", r"flash", r"gemma"],
    "groq": [r"gpt-oss-120b", r"qwen", r"llama-3\.3-70b", r"kimi", r"llama-4", r"gpt-oss-20b", r"llama-3\.1-8b"],
    "openrouter": [r"deepseek", r"qwen", r"llama-3\.3-70b", r"gpt-oss", r"gemma", r"mistral"],
}
AVOID = re.compile(
    r"pro|image|tts|embed|live|audio|vision|aqa|learnlm|robot|computer|native|whisper|guard|"
    r"playai|distil|compound|transcribe|search|nano|veo|imagen|lyria|coder",
    re.I,
)
DEFAULT_MODELS = {
    "gemini": ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash-lite"],
    "groq": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "openrouter": ["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-chat-v3-0324:free"],
}

_model_cache: dict[str, list[str]] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def extract_json(text: str):
    """Find and parse the first JSON object/array in an AI reply (fixes common mistakes)."""
    if not text:
        raise ValueError("empty reply")
    t = text.strip()
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip(), flags=re.I | re.M)
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found in reply")
    open_ch = t[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth, in_str, esc, end = 0, False, False, -1
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                end = i
                break
    chunk = t[start: end + 1] if end > 0 else t[start:] + close_ch * max(depth, 1)
    for attempt in range(3):
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            if attempt == 0:
                chunk = chunk.replace("“", '"').replace("”", '"').replace("’", "'")
                chunk = re.sub(r",\s*([}\]])", r"\1", chunk)
            elif attempt == 1:
                chunk = re.sub(r"(?m)^\s*//.*$", "", chunk)
    raise ValueError("the AI reply was not valid JSON")


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


def _version_key(model_id: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", model_id)
    return float(m.group(1)) if m else 0.0


def rank_models(provider: str, ids: list[str]) -> list[str]:
    """Order available model ids by our preference list (newest version first)."""
    ids = [i.removeprefix("models/") for i in ids]
    if provider == "openrouter":
        ids = [i for i in ids if i.endswith(":free")]
    ranked: list[str] = []
    for pattern in PREFER.get(provider, []):
        group = [i for i in ids if re.search(pattern, i, re.I) and not AVOID.search(i) and i not in ranked]
        group.sort(key=_version_key, reverse=True)
        ranked.extend(group)
    return ranked


def _list_models(provider: str, base: str, key: str) -> list[str]:
    with _lock:
        if provider in _model_cache:
            return _model_cache[provider]
    models: list[str] = []
    try:
        resp = net.request("GET", f"{base}/models", headers={"Authorization": f"Bearer {key}"}, retries=1, timeout=20)
        data = resp.json().get("data", [])
        models = rank_models(provider, [m.get("id", "") for m in data if m.get("id")])
    except Exception:
        models = []
    models = (models + [m for m in DEFAULT_MODELS[provider] if m not in models])[:12]
    with _lock:
        _model_cache[provider] = models
    return models


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _openai_chat(base: str, key: str | None, model: str, messages, json_mode: bool, temperature: float, max_tokens: int,
                 waits=None, on_wait=None):
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        resp = net.request("POST", f"{base}/chat/completions", json=body, headers=headers, timeout=150,
                           retries=len(waits) if waits is not None else 2, waits=waits, on_wait=on_wait)
    except net.ServiceError as exc:
        if exc.status == 400 and json_mode:  # some models don't support JSON mode
            body.pop("response_format", None)
            resp = net.request("POST", f"{base}/chat/completions", json=body, headers=headers, timeout=150, retries=1)
        else:
            raise
    data = resp.json()
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        raise net.ServiceError(f"unexpected reply: {str(data)[:120]}") from None
    if not content.strip():
        raise net.ServiceError("empty reply")
    return content


def gemini_models(key: str) -> tuple[list[str], list[str]]:
    """(main models, lite models): the newest Flash first, then the Flash-Lite models (they answer when Flash is busy)."""
    ranked = _list_models("gemini", GEMINI_BASE, key)
    main = [m for m in ranked if re.search(r"flash(?!-lite)", m)][:1]
    lite = [m for m in ranked if "flash-lite" in m][:2]
    return main, lite


def gemini_busy(within: float = 900) -> bool:
    """True when the main Gemini model stayed busy after all retries in the last 15 minutes (skip extras)."""
    import time  # noqa: PLC0415

    return BUSY["main"] > 0 and time.time() - BUSY["main"] < within


def _waiter(rep):
    def on_wait(sec, status):
        if rep is not None:
            rep.info(f"⏳ Gemini busy (HTTP {status}), retrying in {sec:g} s…")
    return on_wait


def _gemini_provider(model: str, waits, rep, main: bool):
    key = config.secret("GEMINI_API_KEY")

    def call(messages, json_mode, temperature, max_tokens):
        import time  # noqa: PLC0415

        try:
            return _openai_chat(GEMINI_BASE, key, model, messages, json_mode, temperature, max_tokens,
                                waits=waits, on_wait=_waiter(rep))
        except net.ServiceError as exc:
            if exc.status in (401, 403):
                raise net.ServiceError("key was refused (check GEMINI_API_KEY in Colab Secrets)", exc.status) from None
            if main and exc.status in net.RETRY_STATUS:
                BUSY["main"] = time.time()
            raise

    return call


def _keyed_provider(provider: str, base: str, env: str, strong: bool = False):
    key = config.secret(env)
    if not key:
        return None

    def call(messages, json_mode, temperature, max_tokens):
        last: Exception | None = None
        models = _list_models(provider, base, key)
        if strong:  # writing: the bigger free model first
            models = sorted(models, key=lambda m: 0 if re.search(r"flash(?!-lite)|70b|120b", m) else 1)
        for model in models[:2]:
            try:
                return _openai_chat(base, key, model, messages, json_mode, temperature, max_tokens)
            except net.ServiceError as exc:
                last = exc
                if exc.status in (401, 403):  # bad key: no point trying other models
                    raise net.ServiceError(f"key was refused (check {env} in Colab Secrets)", exc.status) from None
                if exc.status == 429:
                    raise
        raise last or net.ServiceError("no model available")

    return call


# ---- local model on the GPU (last AI fallback) -----------------------------

_local = {"model": None, "tok": None}


def _local_chat(messages, json_mode, temperature, max_tokens):
    s = config.get()
    if not s.gpu.available:
        raise net.ServiceError("no GPU for a local model")
    import torch  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

    from .gpu import best_dtype  # noqa: PLC0415

    if _local["model"] is None:
        from .models import ensure_model  # noqa: PLC0415

        mid = ensure_model("local_llm")  # real, checked files
        _local["tok"] = AutoTokenizer.from_pretrained(mid)
        _local["model"] = AutoModelForCausalLM.from_pretrained(mid, torch_dtype=best_dtype(), device_map="cuda")
    tok, model = _local["tok"], _local["model"]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_tokens, do_sample=True, temperature=max(0.3, temperature), top_p=0.9
        )
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def unload_local() -> None:
    """Free the GPU (the local AI writer is done)."""
    if _local["model"] is None:
        return
    _local["model"] = None
    _local["tok"] = None
    from .gpu import free_gpu  # noqa: PLC0415

    free_gpu()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def providers(allow_local: bool = False, strong: bool = False, rep=None) -> list[tuple[str, object]]:
    """The AI chain, best first. Gemini: the main Flash model (3 patient retries), then Flash-Lite.
    The local GPU model only when a caller asks for it (never for scripts or scene plans)."""
    out = []
    key = config.secret("GEMINI_API_KEY")
    if key:
        main, lite = gemini_models(key)
        if not strong:  # quick jobs (titles): the light model first, it is rarely busy
            main, lite = lite[:1], main + lite[1:]
        for k, m in enumerate(main):
            out.append((f"Gemini ({m})", _gemini_provider(m, GEMINI_WAITS if strong else LITE_WAITS, rep, strong)))
        for m in lite:
            if m not in main:
                out.append((f"Gemini ({m})", _gemini_provider(m, LITE_WAITS, rep, False)))
    for name, base, env in (("Groq", GROQ_BASE, "GROQ_API_KEY"), ("OpenRouter", OPENROUTER_BASE, "OPENROUTER_API_KEY")):
        fn = _keyed_provider(name.lower(), base, env, strong)
        if fn:
            out.append((name, fn))
    if allow_local and config.get().gpu.available:
        out.append(("Local AI on GPU", _local_chat))
    return out


def chat(messages, *, json_mode=False, temperature=0.8, max_tokens=4000, rep=None, task="text", allow_local=False):
    """Ask the first free AI that answers. Returns (provider_name, text)."""
    calls = [
        (name, (lambda f=fn: f(messages, json_mode, temperature, max_tokens)))
        for name, fn in _found(allow_local, False, rep)
    ]
    return net.try_in_order(task, calls, rep)


VISION_DEFAULTS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest"]


def vision_models(key: str) -> list[str]:
    """Gemini models that can look at pictures: Flash before Flash-Lite, never Gemma (text only on this API)."""
    found = [m for m in _list_models("gemini", GEMINI_BASE, key) if "gemma" not in m.lower()]
    found.sort(key=lambda m: 0 if re.search(r"flash(?!-lite)", m) else 1)
    return list(dict.fromkeys(found + VISION_DEFAULTS))[:3]


def vision_json(system: str, text: str, images: list, *, rep=None, max_tokens: int = 3000):
    """Ask Gemini (free key) about pictures. Returns the parsed JSON, or None when there is no key or no answer.

    images: JPEG bytes. Only Gemini is used (free vision). The pictures are the same on a CPU or GPU runtime
    (still frames as JPEG), so this works the same on both. If it fails, the real reason is shown in the log."""
    import base64  # noqa: PLC0415

    from .messages import StopRequested  # noqa: PLC0415

    key = config.secret("GEMINI_API_KEY")
    if not key or not images:
        return None
    content = [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
        for b in images]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    errors = []
    for model in vision_models(key):
        try:
            reply = _openai_chat(GEMINI_BASE, key, model, messages, True, 0.2, max_tokens)
            obj = extract_json(reply)
            if rep is not None:
                rep.info(f"👁️ Gemini vision ({model}) looked at {len(images)} picture(s)")
            return obj
        except StopRequested:
            raise
        except net.ServiceError as exc:
            errors.append(f"{model}: {exc}")
            if exc.status in (401, 403):
                break  # a bad key: other models won't work either
        except Exception as exc:  # noqa: BLE001  (a reply that isn't JSON: try the next model)
            errors.append(f"{model}: {type(exc).__name__}: {exc}")
    if rep is not None and errors:
        rep.warn(f"Gemini vision didn't answer ({errors[-1][:140]}). The local checks still ran.")
    return None


def generate_json(system: str, user: str, *, validate=None, rep=None, task="script", temperature=0.85,
                  max_tokens=4000, allow_local=False, strong=False):
    """Ask for JSON, check it with `validate(obj)` (raise ValueError if bad). Returns (provider, obj)."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def make(fn):
        def run():
            text = fn(messages, True, temperature, max_tokens)
            try:
                obj = extract_json(text)
                if validate:
                    validate(obj)
                return obj
            except ValueError as exc:  # one repair attempt with the same provider
                fix = messages + [
                    {"role": "assistant", "content": text[:6000]},
                    {"role": "user", "content": f"That was not usable ({exc}). Reply again with ONLY the corrected JSON."},
                ]
                obj = extract_json(fn(fix, True, 0.4, max_tokens))
                if validate:
                    validate(obj)
                return obj

        return run

    calls = [(name, make(fn)) for name, fn in _found(allow_local, strong, rep)]
    if not calls:
        raise net.AllProvidersFailed(task, [("AI", "no free AI key (add GEMINI_API_KEY in Colab Secrets)")])
    return net.try_in_order(task, calls, rep)


def _found(allow_local: bool, strong: bool, rep):
    try:
        return providers(allow_local, strong=strong, rep=rep)
    except TypeError:  # a simpler providers() (tests)
        return providers(allow_local)


def all_busy(exc: Exception) -> bool:
    """Every AI in the chain was busy or unreachable (HTTP 429/5xx, network): asking again now only waits."""
    errs = getattr(exc, "errors", None)
    return bool(errs) and all(re.search(r"HTTP (429|5\d\d)|network problem|timed? ?out", e, re.I) for _, e in errs)


BUSY_TEXT = ("Gemini is busy, try again in a few minutes.",
             "Free Gemini gets crowded at peak times. Your project is saved: press the button again later.")
