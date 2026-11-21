"""Depth maps for 2.5D parallax.

Depth Anything V2 *Small* only (Apache 2.0; Base/Large/Giant are non-commercial).
Runs on GPU in under a second, on CPU in a few seconds. Without the model we
make a simple "fake depth" (bottom = near, top = far) so motion still works.
Depth values: 1.0 = near, 0.0 = far.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import config
from ..gpu import free_gpu

_model = {"proc": None, "net": None, "failed": ""}


def _load():
    if _model["net"] is not None:
        return _model["proc"], _model["net"]
    import torch  # noqa: PLC0415
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation  # noqa: PLC0415

    s = config.get()
    mid, cache = config.MODELS["depth"], s.model_cache("depth")
    proc = AutoImageProcessor.from_pretrained(mid, cache_dir=cache)
    net = AutoModelForDepthEstimation.from_pretrained(mid, cache_dir=cache)
    net = net.to("cuda" if s.gpu.available else "cpu").eval()
    if s.gpu.available:
        from ..gpu import best_dtype  # noqa: PLC0415

        net = net.to(best_dtype())
    _model.update(proc=proc, net=net)
    return proc, net


def model_depth(rgb: np.ndarray) -> np.ndarray:
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    proc, net = _load()
    inputs = proc(images=Image.fromarray(rgb), return_tensors="pt")
    inputs = {k: v.to(net.device, dtype=net.dtype if v.is_floating_point() else v.dtype) for k, v in inputs.items()}
    with torch.no_grad():
        pred = net(**inputs).predicted_depth  # relative inverse depth: bigger = nearer
    pred = torch.nn.functional.interpolate(pred[:, None].float(), size=rgb.shape[:2], mode="bicubic", align_corners=False)
    return normalize(pred[0, 0].cpu().numpy())


def normalize(d: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    return np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)


def fake_depth(rgb: np.ndarray) -> np.ndarray:
    """No model? Bottom of the picture is near, top is far, plus a little help from edges."""
    import cv2  # noqa: PLC0415

    h, w = rgb.shape[:2]
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None].repeat(w, axis=1)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    edges = cv2.GaussianBlur(np.abs(cv2.Laplacian(gray, cv2.CV_32F)), (0, 0), max(3, w / 80))
    edges = edges / (edges.max() + 1e-6)
    cx = np.abs(np.linspace(-1, 1, w, dtype=np.float32))[None, :]
    center = 1 - 0.3 * cx
    return normalize(0.7 * y * center + 0.3 * edges)


def smooth(d: np.ndarray) -> np.ndarray:
    """Soften depth edges a bit so parallax doesn't tear."""
    import cv2  # noqa: PLC0415

    d8 = (d * 255).astype(np.uint8)
    d8 = cv2.bilateralFilter(d8, 9, 40, 9)
    return cv2.GaussianBlur(d8, (0, 0), 2).astype(np.float32) / 255.0


def make_depth(image_path: Path, out_path: Path) -> str:
    """Write a depth PNG next to the picture. Returns which method was used."""
    import cv2  # noqa: PLC0415

    rgb = cv2.cvtColor(cv2.imread(str(image_path), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    method = "Depth Anything V2 Small"
    d = None
    if not _model["failed"]:
        try:
            d = model_depth(rgb)
        except Exception as exc:  # no internet / no model / any problem
            _model["failed"] = f"{type(exc).__name__}: {str(exc)[:100]}"
    if d is None:
        d, method = fake_depth(rgb), "simple depth (no model)"
    d = smooth(d)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), (d * 255).astype(np.uint8))
    return method


def load_depth(path: Path | None, shape: tuple[int, int]) -> np.ndarray | None:
    import cv2  # noqa: PLC0415

    if not path or not Path(path).exists():
        return None
    d = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if d is None:
        return None
    if d.shape[:2] != shape:
        d = cv2.resize(d, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    return d.astype(np.float32) / 255.0


def unload() -> None:
    if _model["net"] is not None:
        _model.update(proc=None, net=None)
        free_gpu()
