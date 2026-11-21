"""Real image-to-video for "hero" scenes with Wan 2.2 TI2V 5B (Apache 2.0).

research.md: Wan 2.2 5B fits a free T4 but takes several minutes per clip, so
we only do it for 0-3 hero scenes (default 2), with a time limit per clip.
If time or memory runs out, the scene falls back to 2.5D parallax.

Memory plan for Colab (12 GB RAM, 15 GB T4): load the text encoder straight to
the GPU, encode the prompts, delete it, then load the video model.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .. import config
from ..gpu import free_gpu, is_oom
from ..messages import StopRequested
from ..project import fingerprint

NEGATIVE = (
    "bright tones, overexposed, static, blurred details, subtitles, text, watermark, worst quality, low quality, "
    "JPEG artifacts, ugly, deformed, disfigured, extra fingers, poorly drawn hands, poorly drawn face, "
    "fused fingers, messy background, three legs, walking backwards, frozen, still picture"
)
CAMERA_WORDS = {
    "push_in": "slow dolly in toward the subject", "pull_out": "slow pull back revealing the scene",
    "pan_left": "smooth pan to the left", "pan_right": "smooth pan to the right", "tilt_up": "camera tilts up",
    "tilt_down": "camera tilts down", "orbit_left": "camera orbits to the left around the subject",
    "orbit_right": "camera orbits to the right around the subject", "dolly_zoom": "dramatic dolly zoom",
    "handheld": "handheld camera, tense", "static": "steady camera, subtle movement",
}
FPS = 16  # 81 frames at 16 fps = ~5 s clip; size/frames/steps come from the GPU profile (config.gpu_profile)


class TimeBudgetExceeded(Exception):
    pass


def hero_prompt(scene: dict) -> str:
    motion = CAMERA_WORDS.get(scene.get("camera", ""), "smooth cinematic camera movement")
    return f"{scene.get('visual', '')}. {motion}. Natural lifelike motion, cinematic lighting, high detail."


class WanEngine:
    _instance: "WanEngine | None" = None
    failed_reason: str = ""

    def __init__(self):
        self.pipe = None

    @classmethod
    def get(cls) -> "WanEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def usable(cls) -> bool:
        s = config.get()
        return s.gpu.available and s.gpu.vram_gb >= 14 and not cls.failed_reason

    def _emb_path(self, text: str) -> Path:
        d = config.get().temp_dir / "wan_embeds"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{fingerprint(text)}.pt"

    def encode(self, prompts: list[str], rep=None) -> None:
        import torch  # noqa: PLC0415
        from transformers import AutoTokenizer, UMT5EncoderModel  # noqa: PLC0415

        todo = [p for p in dict.fromkeys(list(prompts) + [NEGATIVE]) if not self._emb_path(p).exists()]
        if not todo:
            return
        self.unload()
        s = config.get()
        mid, cache = config.MODELS["i2v"], s.model_cache("i2v")
        if rep:
            rep.info("📥 Loading the video prompt reader (first time downloads ~11 GB)…")
        tok = AutoTokenizer.from_pretrained(mid, subfolder="tokenizer", cache_dir=cache)
        from ..gpu import best_dtype  # noqa: PLC0415

        te = UMT5EncoderModel.from_pretrained(mid, subfolder="text_encoder", cache_dir=cache,
                                              torch_dtype=best_dtype(), device_map="cuda")
        try:
            for p in todo:
                clean = re.sub(r"\s+", " ", p).strip()
                inputs = tok([clean], padding="max_length", max_length=512, truncation=True,
                             add_special_tokens=True, return_attention_mask=True, return_tensors="pt")
                ids, mask = inputs.input_ids.to(te.device), inputs.attention_mask.to(te.device)
                with torch.no_grad():
                    emb = te(ids, mask).last_hidden_state.to(best_dtype())
                n = int(mask.gt(0).sum())
                emb = torch.cat([emb[0, :n], emb.new_zeros(512 - n, emb.shape[-1])])[None]
                if not torch.isfinite(emb).all():
                    raise RuntimeError("video prompt reader produced invalid numbers")
                torch.save(emb.cpu(), self._emb_path(p))
        finally:
            del te, tok
            free_gpu()

    def load(self, rep=None):
        if self.pipe is not None:
            return self.pipe
        import torch  # noqa: PLC0415
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanTransformer3DModel  # noqa: PLC0415

        s = config.get()
        mid, cache = config.MODELS["i2v"], s.model_cache("i2v")
        if rep:
            rep.info("📥 Loading Wan 2.2 video model (first time downloads ~10 GB)…")
        from ..gpu import best_dtype  # noqa: PLC0415

        transformer = WanTransformer3DModel.from_pretrained(mid, subfolder="transformer", cache_dir=cache,
                                                            torch_dtype=best_dtype(), device_map="cuda")
        vae = AutoencoderKLWan.from_pretrained(mid, subfolder="vae", cache_dir=cache, torch_dtype=torch.float32).to("cuda")
        pipe = WanImageToVideoPipeline.from_pretrained(mid, cache_dir=cache, transformer=transformer, vae=vae,
                                                       text_encoder=None, tokenizer=None, torch_dtype=best_dtype())
        try:
            pipe.vae.enable_tiling()
        except Exception:
            pass
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe
        return pipe

    def make(self, image: Path, prompt: str, out: Path, fmt: str, minutes: float, seed: int, rep) -> None:
        import torch  # noqa: PLC0415
        from PIL import Image, ImageOps  # noqa: PLC0415

        pipe = self.load(rep)
        prof = config.gpu_profile()
        w, h = prof.wan_sizes.get(fmt, prof.wan_sizes["9x16"])
        STEPS, FRAMES = prof.wan_steps, prof.wan_frames  # noqa: N806
        img = ImageOps.fit(Image.open(image).convert("RGB"), (w, h), method=3)
        emb = torch.load(self._emb_path(prompt)).to("cuda", dtype=pipe.transformer.dtype)
        neg = torch.load(self._emb_path(NEGATIVE)).to("cuda", dtype=pipe.transformer.dtype)
        budget = minutes * 60
        start = time.time()
        status = {"over": False, "stop": False}

        def watch(p, i, t, kwargs):
            elapsed = time.time() - start
            if rep is not None and rep.stop_requested:
                status["stop"] = True
                p._interrupt = True
            elif i >= 1 and elapsed / (i + 1) * STEPS > budget:
                status["over"] = True
                p._interrupt = True
            if rep is not None:
                rep.progress(rep.fraction, f"Hero clip step {i + 1}/{STEPS} ({elapsed / 60:.1f} min)")
            return kwargs

        gen = torch.Generator("cuda").manual_seed(int(seed))
        with torch.no_grad():
            latents = pipe(image=img, prompt_embeds=emb, negative_prompt_embeds=neg, height=h, width=w,
                           num_frames=FRAMES, num_inference_steps=STEPS, guidance_scale=5.0, generator=gen,
                           output_type="latent", callback_on_step_end=watch).frames
            if status["stop"]:
                raise StopRequested()
            if status["over"]:
                raise TimeBudgetExceeded(f"would take more than {minutes:.0f} min")
            vae = pipe.vae
            lat = latents.to(device="cuda", dtype=vae.dtype)
            mean = torch.tensor(vae.config.latents_mean).view(1, vae.config.z_dim, 1, 1, 1).to(lat.device, lat.dtype)
            std = 1.0 / torch.tensor(vae.config.latents_std).view(1, vae.config.z_dim, 1, 1, 1).to(lat.device, lat.dtype)
            video = vae.decode(lat / std + mean, return_dict=False)[0]
            frames = pipe.video_processor.postprocess_video(video, output_type="np")[0]
        _write_frames(frames, out, (w, h))

    def unload(self) -> None:
        if self.pipe is not None:
            self.pipe = None
            free_gpu()


def _write_frames(frames, out: Path, size: tuple[int, int]) -> None:
    import numpy as np  # noqa: PLC0415

    from .effects import write_video  # noqa: PLC0415

    arr = (np.clip(frames, 0, 1) * 255).astype("uint8")
    write_video(iter(arr), out, size, FPS, quality="final")


def make_hero_clip(image: Path, scene: dict, out: Path, fmt: str, minutes: float, seed: int, rep) -> tuple[bool, str]:
    """Try to make a real moving clip. Returns (ok, message). Never raises for normal failures."""
    if not WanEngine.usable():
        return False, WanEngine.failed_reason or "no suitable GPU"
    eng = WanEngine.get()
    prompt = hero_prompt(scene)
    try:
        eng.encode([prompt], rep)
        eng.make(image, prompt, out, fmt, minutes, seed, rep)
        return True, "Wan 2.2"
    except StopRequested:
        raise
    except TimeBudgetExceeded as exc:
        return False, f"too slow on this GPU ({exc})"
    except Exception as exc:  # noqa: BLE001
        reason = "GPU memory full" if is_oom(exc) else f"{type(exc).__name__}: {str(exc)[:120]}"
        WanEngine.failed_reason = reason
        eng.unload()
        return False, reason


def unload() -> None:
    WanEngine.get().unload()
