"""Scene and character pictures.

Order: FLUX.2 [klein] 4B on the GPU (Apache 2.0, uses character reference
pictures) → Pollinations (no key, one picture every ~45 s) → AI Horde (no key,
free community queue) → a placeholder card you can replace.

Colab has ~12 GB RAM and a 15 GB T4, so klein is loaded in two halves: the text
encoder turns all prompts into numbers, is deleted, then the image model loads.
Prompt numbers are cached on disk, so "Regenerate" with the same prompt skips
the text encoder.
"""

from __future__ import annotations

import io
import random
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from . import config, net
from .gpu import free_gpu, is_oom
from .messages import FriendlyError, Timer
from .project import fingerprint

POLLINATIONS_GAP = 46.0  # seconds between keyless requests (research.md)
HORDE_URL = "https://aihorde.net/api/v2"
HORDE_MODELS = ["AlbedoBase XL (SDXL)", "Juggernaut XL", "Dreamshaper XL"]


@dataclass
class ImageJob:
    prompt: str
    out: Path
    size: tuple[int, int]  # (width, height) to generate
    seed: int
    refs: list[Path] = field(default_factory=list)
    key: str = ""  # state key, filled by the pipeline
    fp: str = ""
    label: str = ""


def gen_size(size: tuple[int, int], max_side: int | None = None) -> tuple[int, int]:
    """Scale a target size to a GPU friendly size (multiples of 16, long side <= max_side; bigger on L4/A100)."""
    if max_side is None:
        max_side = config.gpu_profile().image_max_side if config.get().gpu.available else 1344
    w, h = size
    scale = min(1.0, max_side / max(w, h))
    return int(w * scale) // 16 * 16, int(h * scale) // 16 * 16


# ---------------------------------------------------------------------------
# GPU: FLUX.2 [klein] 4B
# ---------------------------------------------------------------------------


class KleinEngine:
    _instance: "KleinEngine | None" = None
    failed_reason: str = ""  # set if klein can't run this session

    def __init__(self):
        self.pipe = None
        self.te = None  # prompt reader, kept loaded on L4/A100 (enough GPU memory)
        self.tok = None

    @classmethod
    def get(cls) -> "KleinEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def usable(cls) -> bool:
        return config.get().gpu.available and not cls.failed_reason

    def _emb_dir(self) -> Path:
        d = config.get().temp_dir / "prompt_embeds"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _emb_path(self, prompt: str) -> Path:
        return self._emb_dir() / f"{fingerprint(prompt)}.pt"

    def encode(self, prompts: list[str], rep=None) -> None:
        """Turn prompts into embeddings (cached on local disk)."""
        import torch  # noqa: PLC0415

        todo = [p for p in dict.fromkeys(prompts) if not self._emb_path(p).exists()]
        if not todo:
            return
        keep = config.gpu_profile().keep_text_encoder
        if not keep:
            self.unload()  # T4: the image model and the prompt reader don't fit together
        from diffusers import Flux2KleinPipeline  # noqa: PLC0415
        from transformers import AutoTokenizer, Qwen3ForCausalLM  # noqa: PLC0415

        from .gpu import best_dtype  # noqa: PLC0415

        s = config.get()
        mid, cache = config.MODELS["image"], s.model_cache("image")
        if self.te is None:
            if rep:
                rep.info(f"📥 Loading the prompt reader (first time downloads ~8 GB, then {len(todo)} prompts)…")
            self.tok = AutoTokenizer.from_pretrained(mid, subfolder="tokenizer", cache_dir=cache)
            self.te = Qwen3ForCausalLM.from_pretrained(
                mid, subfolder="text_encoder", cache_dir=cache, torch_dtype=best_dtype(), device_map="cuda"
            )
        try:
            for p in todo:
                with torch.no_grad():
                    emb = Flux2KleinPipeline._get_qwen3_prompt_embeds(self.te, self.tok, p, device=self.te.device)
                if not torch.isfinite(emb).all():
                    raise RuntimeError("prompt reader produced invalid numbers (fp16 overflow)")
                torch.save(emb.to("cpu"), self._emb_path(p))
        finally:
            if not keep:
                self.te = self.tok = None
                free_gpu()

    def load(self, rep=None):
        if self.pipe is not None:
            return self.pipe
        import torch  # noqa: PLC0415
        from diffusers import AutoencoderKLFlux2, Flux2KleinPipeline, Flux2Transformer2DModel  # noqa: PLC0415

        s = config.get()
        mid, cache = config.MODELS["image"], s.model_cache("image")
        if rep:
            rep.info("📥 Loading the image model FLUX.2 klein 4B (first time downloads ~8 GB)…")
        from .gpu import best_dtype  # noqa: PLC0415

        dtype = best_dtype()  # fp16 on T4, bf16 on L4/A100
        transformer = Flux2Transformer2DModel.from_pretrained(
            mid, subfolder="transformer", cache_dir=cache, torch_dtype=dtype, device_map="cuda"
        )
        vae = AutoencoderKLFlux2.from_pretrained(mid, subfolder="vae", cache_dir=cache, torch_dtype=torch.float32).to("cuda")
        self.pipe = Flux2KleinPipeline.from_pretrained(
            mid, cache_dir=cache, transformer=transformer, vae=vae, text_encoder=None, tokenizer=None,
            torch_dtype=dtype,
        )
        self.pipe.set_progress_bar_config(disable=True)
        return self.pipe

    def generate(self, job: ImageJob):
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        pipe = self.load()
        emb = torch.load(self._emb_path(job.prompt)).to("cuda", dtype=pipe.transformer.dtype)
        refs = []
        for r in job.refs:
            im = Image.open(r).convert("RGB")
            im.thumbnail((640, 640))  # small refs = much faster on a T4
            refs.append(im)
        gen = torch.Generator("cuda").manual_seed(int(job.seed))
        w, h = gen_size(job.size)
        with torch.no_grad():
            latents = pipe(
                image=refs or None, prompt_embeds=emb, width=w, height=h, num_inference_steps=4,
                guidance_scale=1.0, generator=gen, output_type="latent",
            ).images
            if not torch.isfinite(latents).all():
                raise RuntimeError("image model produced invalid numbers (fp16 overflow)")
            decoded = pipe.vae.decode(latents.to(torch.float32), return_dict=False)[0]
            img = pipe.image_processor.postprocess(decoded, output_type="pil")[0]
        return img

    def unload(self) -> None:
        if self.pipe is not None or self.te is not None:
            self.pipe = None
            self.te = self.tok = None
            free_gpu()


# ---------------------------------------------------------------------------
# Online fallbacks
# ---------------------------------------------------------------------------

_last_pollinations = [0.0]
_down_until: dict[str, float] = {}  # service name -> time it may be tried again
DOWN_MINUTES = 5


def _service_down(name: str) -> bool:
    return time.time() < _down_until.get(name, 0.0)


def _mark_down(name: str, exc: BaseException) -> None:
    """Unreachable or broken (not just busy)? Skip this service for a few minutes."""
    status = getattr(exc, "status", None)
    if status is None or (isinstance(status, int) and status >= 500):
        _down_until[name] = time.time() + DOWN_MINUTES * 60


def _image_from_bytes(data: bytes):
    from PIL import Image  # noqa: PLC0415

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("RGB")
    except Exception:
        raise net.ServiceError("the reply was not a picture") from None


def pollinations(prompt: str, size: tuple[int, int], seed: int, rep=None):
    wait = POLLINATIONS_GAP - (time.time() - _last_pollinations[0])
    if wait > 0:
        if rep:
            rep.info(f"⏳ Waiting {wait:.0f} s (the free online picture service allows one picture at a time)…")
        while wait > 0:
            if rep:
                rep.check_stop()
            time.sleep(min(wait, 2))
            wait -= 2
    w, h = gen_size(size, 1280)
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:1200], safe="")
    params = {"width": w, "height": h, "seed": seed, "nologo": "true", "private": "true", "model": "flux"}
    try:
        resp = net.request("GET", url, params=params, timeout=180, retries=1, backoff=20, max_wait=60)
    except net.ServiceError as exc:
        if exc.status is not None:  # the service answered (e.g. busy): keep the spacing
            _last_pollinations[0] = time.time()
        raise
    _last_pollinations[0] = time.time()
    return _image_from_bytes(resp.content)


def ai_horde(prompt: str, size: tuple[int, int], seed: int, rep=None, timeout: float = 420):
    key = config.secret("AIHORDE_API_KEY") or "0000000000"
    headers = {"apikey": key, "Client-Agent": "StoryForge:1.0:anonymous"}
    w, h = size
    scale = 1024 / max(w, h)
    w, h = int(w * scale) // 64 * 64, int(h * scale) // 64 * 64
    body = {
        "prompt": prompt[:1000] + " ### text, watermark, logo, blurry, deformed",
        "params": {"width": w, "height": h, "steps": 25, "cfg_scale": 6, "sampler_name": "k_euler_a",
                   "seed": str(seed), "n": 1, "karras": True},
        "nsfw": False, "censor_nsfw": True, "r2": True, "models": HORDE_MODELS,
    }
    job = net.request("POST", f"{HORDE_URL}/generate/async", json=body, headers=headers, timeout=60, retries=1).json()
    jid = job.get("id")
    if not jid:
        raise net.ServiceError(f"no job id ({str(job)[:80]})")
    start = time.time()
    while time.time() - start < timeout:
        if rep:
            rep.check_stop()
        time.sleep(6)
        chk = net.request("GET", f"{HORDE_URL}/generate/check/{jid}", headers=headers, timeout=30, retries=2).json()
        if chk.get("faulted") or chk.get("is_possible") is False:
            raise net.ServiceError("the free queue could not make this picture")
        if chk.get("done"):
            status = net.request("GET", f"{HORDE_URL}/generate/status/{jid}", headers=headers, timeout=30).json()
            gens = status.get("generations") or []
            if not gens:
                raise net.ServiceError("empty result")
            img_url = gens[0].get("img", "")
            data = net.request("GET", img_url, timeout=60).content if img_url.startswith("http") else None
            if data is None:
                import base64  # noqa: PLC0415

                data = base64.b64decode(img_url)
            return _image_from_bytes(data)
        if rep and int(time.time() - start) % 30 < 6:
            rep.info(f"⏳ In the free community queue (position {chk.get('queue_position', '?')})…")
    raise net.ServiceError("the free queue took too long")


# ---------------------------------------------------------------------------
# Placeholder (always works, no internet)
# ---------------------------------------------------------------------------


def placeholder(prompt: str, size: tuple[int, int], seed: int, label: str = ""):
    """A moody, abstract picture so the video still renders. Replace it later."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: PLC0415

    w, h = size
    rng = random.Random(seed)
    palettes = [((18, 8, 40), (190, 40, 150)), ((5, 20, 40), (40, 160, 200)), ((30, 10, 10), (230, 110, 40)),
                ((10, 25, 20), (90, 200, 140)), ((20, 10, 35), (120, 80, 230))]
    top, glow = palettes[rng.randrange(len(palettes))]
    y = np.linspace(0, 1, h)[:, None, None]
    sky = (np.array(top) * (1 - y) + np.array(glow) * 0.55 * y).repeat(w, axis=1)
    img = sky.astype(np.float32)
    # a glowing moon/sun
    cx, cy, r = rng.uniform(0.25, 0.75) * w, rng.uniform(0.15, 0.4) * h, min(w, h) * rng.uniform(0.08, 0.14)
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    img += (np.clip(1.6 - dist / r, 0, 1) ** 2)[..., None] * np.array(glow) * 1.2
    img += (np.exp(-dist / (r * 4)))[..., None] * np.array(glow) * 0.35
    # layered hills (gives the depth effect something to move)
    for layer in range(4):
        base = h * (0.55 + 0.11 * layer)
        amp = h * (0.06 + 0.02 * layer)
        ph = rng.uniform(0, 6.28)
        freq = rng.uniform(1.5, 3.5) / w * 6.28
        ridge = base + amp * np.sin(xx[0] * freq + ph) + amp * 0.4 * np.sin(xx[0] * freq * 2.7 + ph * 2)
        mask = yy > ridge[None, :]
        shade = 0.55 - 0.13 * layer
        img[mask] = img[mask] * shade + np.array(top) * (1 - shade) * 0.6
    # stars
    for _ in range(int(w * h / 9000)):
        sx, sy = rng.randrange(w), rng.randrange(int(h * 0.5))
        img[sy, sx] = np.minimum(255, img[sy, sx] + rng.uniform(80, 200))
    pil = Image.fromarray(np.clip(img, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.6))
    draw = ImageDraw.Draw(pil)
    try:
        font = ImageFont.truetype(str(config.FONTS_DIR / "Montserrat-ExtraBold.ttf"), max(18, w // 28))
    except Exception:
        font = ImageFont.load_default()
    text = label or "Placeholder picture: replace or regenerate"
    tw = draw.textlength(text, font=font)
    draw.rounded_rectangle([(w - tw) / 2 - 20, h * 0.9 - 14, (w + tw) / 2 + 20, h * 0.9 + font.size + 14],
                           radius=18, fill=(0, 0, 0, 140))
    draw.text(((w - tw) / 2, h * 0.9), text, font=font, fill=(255, 255, 255))
    return pil


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _save(img, path: Path, size: tuple[int, int]) -> None:
    """Save as PNG, center-cropped to the requested aspect ratio."""
    from PIL import ImageOps  # noqa: PLC0415

    w, h = size
    if abs(img.width / img.height - w / h) > 0.01:
        target = gen_size(size, max(img.width, img.height))
        img = ImageOps.fit(img, target, method=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".part.png")
    img.save(tmp)
    tmp.replace(path)


def _check_not_blank(img) -> None:
    import numpy as np  # noqa: PLC0415

    arr = np.asarray(img.convert("L"), dtype=np.float32)
    if arr.std() < 2.0:
        raise RuntimeError("the picture came out blank")


def generate_batch(jobs: list[ImageJob], rep, on_done=None, allow_placeholder: bool = True,
                   span: tuple[float, float] | None = None) -> dict[str, int]:
    """Make all pictures. Calls on_done(job, provider) after each one is saved. Returns provider counts."""
    counts: dict[str, int] = {}
    if not jobs:
        return counts
    if rep is None:
        from .messages import Reporter  # noqa: PLC0415

        rep = Reporter(echo=False)
    remaining = list(jobs)
    engine = KleinEngine.get()
    if KleinEngine.usable():
        try:
            engine.encode([j.prompt for j in remaining], rep)
        except Exception as exc:
            _disable_klein(exc, rep)
    total = len(jobs)
    for i, job in enumerate(remaining, 1):
        rep.check_stop()
        frac = rep.fraction if span is None else span[0] + (span[1] - span[0]) * (i - 1) / total
        rep.progress(frac, f"Picture {i}/{total}")
        with Timer() as t:
            provider = _generate_one(job, rep, allow_placeholder)
        counts[provider] = counts.get(provider, 0) + 1
        if not job.label.startswith("ref:"):  # character refs are logged by characters.py
            rep.ok(f"🖼️ {job.label or job.out.name} {i}/{total} ({provider}, {t.label})")
        if on_done:
            on_done(job, provider)
    return counts


def _disable_klein(exc: BaseException, rep) -> None:
    reason = "GPU memory full" if is_oom(exc) else f"{type(exc).__name__}: {str(exc)[:120]}"
    KleinEngine.failed_reason = reason
    KleinEngine.get().unload()
    if rep:
        rep.warn(f"The GPU image model couldn't run ({reason}). Using free online pictures instead.")


def _breaker(name: str, fn):
    def run():
        try:
            return fn()
        except net.ServiceError as exc:
            _mark_down(name, exc)
            raise

    return run


def _generate_one(job: ImageJob, rep, allow_placeholder: bool) -> str:
    providers = []
    if KleinEngine.usable():
        def klein():
            try:
                return KleinEngine.get().generate(job)
            except Exception as exc:
                if is_oom(exc) or "invalid numbers" in str(exc):
                    _disable_klein(exc, rep)
                raise

        providers.append(("FLUX.2 klein (GPU)", klein))
    for name, fn in (("Pollinations", lambda: pollinations(job.prompt, job.size, job.seed, rep)),
                     ("AI Horde", lambda: ai_horde(job.prompt, job.size, job.seed, rep))):
        if not _service_down(name):
            providers.append((name, _breaker(name, fn)))
    if allow_placeholder:
        providers.append(("Placeholder", lambda: placeholder(job.prompt, gen_size(job.size, 1280), job.seed)))

    def checked(fn):
        def run():
            img = fn()
            _check_not_blank(img)
            return img

        return run

    try:
        name, img = net.try_in_order("picture", [(n, checked(f)) for n, f in providers], rep)
    except net.AllProvidersFailed:
        raise FriendlyError("No picture service is working right now.", "Wait a few minutes and press the button again, or upload your own picture.") from None
    _save(img, job.out, job.size)
    return name


def generate_to_file(prompt: str, out: Path, size: tuple[int, int], seed: int, refs=(), rep=None,
                     allow_placeholder: bool = True, label: str = "") -> str:
    """Make one picture (used for character references)."""
    job = ImageJob(prompt=prompt, out=Path(out), size=size, seed=seed, refs=list(refs), label=label)
    counts = generate_batch([job], rep, allow_placeholder=allow_placeholder)
    return next(iter(counts))


def unload() -> None:
    KleinEngine.get().unload()
