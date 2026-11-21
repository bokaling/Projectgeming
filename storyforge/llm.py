"""Free AI text providers with automatic fallback.

Order (research.md section 2): Gemini Flash-Lite → Groq → OpenRouter :free →
Pollinations (no key) → small local model on the GPU. Providers without a key
are skipped. If all fail, script.py makes a template script you can edit.
"""

from __future__ import annotations

import json
import re
import threading

from . import config, net

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
GROQ_BASE = "https://api.groq.com/openai/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
POLLINATIONS_URLS = ["https://text.pollinations.ai/openai", "https://text.pollinations.ai/"]

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
    models = (models + [m for m in DEFAULT_MODELS[provider] if m not in models])[:4]
    with _lock:
        _model_cache[provider] = models
    return models


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _openai_chat(base: str, key: str | None, model: str, messages, json_mode: bool, temperature: float, max_tokens: int):
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        resp = net.request("POST", f"{base}/chat/completions", json=body, headers=headers, timeout=150, retries=2)
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


def _keyed_provider(provider: str, base: str, env: str):
    key = config.secret(env)
    if not key:
        return None

    def call(messages, json_mode, temperature, max_tokens):
        last: Exception | None = None
        for model in _list_models(provider, base, key)[:2]:
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


def _pollinations(messages, json_mode, temperature, max_tokens):
    last: Exception | None = None
    for url in POLLINATIONS_URLS:
        body = {"model": "openai", "messages": messages, "temperature": temperature}
        if json_mode:
            body["jsonMode"] = True
            body["response_format"] = {"type": "json_object"}
        try:
            resp = net.request("POST", url, json=body, timeout=150, retries=1, backoff=8)
        except net.ServiceError as exc:
            last = exc
            continue
        try:
            data = resp.json()
            if isinstance(data, dict) and "choices" in data:
                return data["choices"][0]["message"]["content"]
            if isinstance(data, (dict, list)):
                return json.dumps(data)
        except ValueError:
            pass
        if resp.text.strip():
            return resp.text
    raise last or net.ServiceError("no reply")


# ---- local model on the GPU (last AI fallback) -----------------------------

_local = {"model": None, "tok": None}


def _local_chat(messages, json_mode, temperature, max_tokens):
    s = config.get()
    if not s.gpu.available:
        raise net.ServiceError("no GPU for a local model")
    import torch  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

    if _local["model"] is None:
        mid = config.MODELS["local_llm"]
        cache = s.model_cache("local_llm")
        _local["tok"] = AutoTokenizer.from_pretrained(mid, cache_dir=cache)
        _local["model"] = AutoModelForCausalLM.from_pretrained(
            mid, cache_dir=cache, torch_dtype=torch.float16, device_map="cuda"
        )
    tok, model = _local["tok"], _local["model"]
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_tokens, do_sample=True, temperature=max(0.3, temperature), top_p=0.9
        )
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def unload_local() -> None:
    """Free the GPU for image generation."""
    if _local["model"] is None:
        return
    _local["model"] = None
    _local["tok"] = None
    from .gpu import free_gpu  # noqa: PLC0415

    free_gpu()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def providers(allow_local: bool = True) -> list[tuple[str, object]]:
    out = []
    for name, base, env in (
        ("Gemini", GEMINI_BASE, "GEMINI_API_KEY"),
        ("Groq", GROQ_BASE, "GROQ_API_KEY"),
        ("OpenRouter", OPENROUTER_BASE, "OPENROUTER_API_KEY"),
    ):
        fn = _keyed_provider(name.lower(), base, env)
        if fn:
            out.append((name, fn))
    out.append(("Pollinations", _pollinations))
    if allow_local and config.get().gpu.available:
        out.append(("Local AI on GPU", _local_chat))
    return out


def chat(messages, *, json_mode=False, temperature=0.8, max_tokens=4000, rep=None, task="text", allow_local=True):
    """Ask the first free AI that answers. Returns (provider_name, text)."""
    calls = [
        (name, (lambda f=fn: f(messages, json_mode, temperature, max_tokens)))
        for name, fn in providers(allow_local)
    ]
    return net.try_in_order(task, calls, rep)


def generate_json(system: str, user: str, *, validate=None, rep=None, task="script", temperature=0.85,
                  max_tokens=4000, allow_local=True):
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

    calls = [(name, make(fn)) for name, fn in providers(allow_local)]
    return net.try_in_order(task, calls, rep)
