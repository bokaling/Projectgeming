"""Small GPU helpers. Rule: only one big model on the GPU at a time."""

from __future__ import annotations

import gc


def free_gpu() -> None:
    gc.collect()
    try:
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def best_dtype():
    """fp16 on T4 (no native bf16), bf16 on newer GPUs."""
    import torch  # noqa: PLC0415

    if torch.cuda.is_available():
        major, _ = torch.cuda.get_device_capability(0)
        return torch.bfloat16 if major >= 8 else torch.float16
    return torch.float32


def vram_free_gb() -> float:
    try:
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            free, _total = torch.cuda.mem_get_info()
            return free / 1024**3
    except Exception:
        pass
    return 0.0


def is_oom(exc: BaseException) -> bool:
    return "out of memory" in str(exc).lower() or type(exc).__name__ == "OutOfMemoryError"
