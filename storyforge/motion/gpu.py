"""The motion engine on the GPU (PyTorch). Same math as effects.frames(), about 5-10x faster.

Used automatically when a CUDA GPU is free. On a T4 the CPU has only 2 cores,
so a 10 minute video (18,000 frames) renders much faster here.
"""

from __future__ import annotations

import math

import numpy as np

from . import effects


def available() -> bool:
    try:
        import torch  # noqa: PLC0415

        return torch.cuda.is_available()
    except Exception:
        return False


def frames(rgb: np.ndarray, depth: np.ndarray | None, size: tuple[int, int], duration: float, fps: int = 30,
           camera: str = "push_in", fx=(), seed: int = 0, shake_times=(), strength: float = 1.0,
           grain: bool = True, vignette: bool = True, device: str = "cuda"):
    """Yield RGB uint8 frames (numpy), computed on `device`."""
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415

    W, H = size
    canvas, dcanvas = effects.prepare_canvas(rgb, depth, size)
    Hw, Ww = canvas.shape[:2]
    move = effects.camera_move(camera, strength)
    if dcanvas is None:
        move.par = ((0, 0), (0, 0))
        move.dolly = (0.0, 0.0)
    overlay = effects.Overlay(size, fx, seed, duration, grain=False, vignette=False, shake_times=shake_times,
                              handheld=move.handheld)
    dev = torch.device(device)
    img = torch.from_numpy(np.ascontiguousarray(canvas)).to(dev).permute(2, 0, 1)[None].float()
    dep = torch.from_numpy(dcanvas).to(dev)[None, None] if dcanvas is not None else None
    h2, w2 = (H + 1) // 2, (W + 1) // 2
    X = (torch.arange(w2, device=dev, dtype=torch.float32) * (W / w2) - W / 2 + 0.5)[None, :].expand(h2, w2)
    Y = (torch.arange(h2, device=dev, dtype=torch.float32) * (H / h2) - H / 2 + 0.5)[:, None].expand(h2, w2)
    cx, cy = Ww / 2, Hw / 2

    def to_grid(mx, my):  # pixel coords (cv2 convention) -> grid_sample coords
        return torch.stack([(mx + 0.5) / Ww * 2 - 1, (my + 0.5) / Hw * 2 - 1], dim=-1)[None]

    # effects prepared once as tensors
    yy, xx = torch.meshgrid(torch.arange(H, device=dev, dtype=torch.float32),
                            torch.arange(W, device=dev, dtype=torch.float32), indexing="ij")
    vig = None
    if vignette:
        r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
        vig = (1 - 0.32 * torch.clamp(r2 / 2, 0, 1) ** 1.3)[None, None]
    gen = torch.Generator(device=dev).manual_seed(int(seed))
    grains = []
    if grain:
        for _ in range(4):
            g = torch.randn((1, 1, H // 2, W // 2), generator=gen, device=dev) * 6
            grains.append(F.interpolate(g, size=(H, W), mode="bilinear", align_corners=False))
    fog = torch.from_numpy(overlay.fog).to(dev) if "fog" in overlay.effects else None
    rays = torch.from_numpy(overlay.rays).to(dev).permute(2, 0, 1)[None] if "god_rays" in overlay.effects else None
    n = max(1, int(round(duration * fps)))
    with torch.no_grad():
        for i in range(n):
            t, z, k, px, py, qx, qy = effects.camera_state(move, overlay, i, n, fps)
            bx = cx + X / z + px * W
            by = cy + Y / z + py * H
            if dep is not None:
                d = F.grid_sample(dep, to_grid(bx, by), mode="bilinear", padding_mode="reflection",
                                  align_corners=False)[0, 0] - 0.5
                zf = z * (1 + k * d)
                mx = cx + X / zf + px * W + qx * W * d
                my = cy + Y / zf + py * H + qy * W * d
            else:
                mx, my = bx, by
            full = F.interpolate(torch.stack([mx, my])[None], size=(H, W), mode="bilinear", align_corners=False)[0]
            f = F.grid_sample(img, to_grid(full[0], full[1]), mode="bilinear", padding_mode="reflection",
                              align_corners=False)
            if fog is not None:
                off = int((t * 0.03 * W) % W)
                f = 255 - (255 - f) * (1 - 0.22 * fog[None, None, :, off:off + W])
            if rays is not None:
                f = f + rays * (0.16 + 0.05 * math.sin(t * 0.8))
            if "light_leak" in overlay.effects:
                small = torch.from_numpy(effects.light_leak_small(t, W, H)).to(dev).permute(2, 0, 1)[None]
                f = f + F.interpolate(small, size=(H, W), mode="bicubic", align_corners=False)
            if overlay.particles:
                light = sum(p.layer(t) for p in overlay.particles)
                lt = torch.from_numpy(np.ascontiguousarray(light)).to(dev).permute(2, 0, 1)[None]
                f = f + F.interpolate(lt, size=(H, W), mode="bilinear", align_corners=False)
            if "flicker" in overlay.effects:
                f = f * effects.flicker_gain(overlay, t)
            if vig is not None:
                f = f * vig
            if grains:
                f = f + grains[i % len(grains)]
            out = f.clamp(0, 255).to(torch.uint8)[0].permute(1, 2, 0).contiguous().cpu().numpy()
            yield out
