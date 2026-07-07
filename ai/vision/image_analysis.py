"""

Real, on-device image feature extraction for ClariMed AI.

HONEST SCOPE (read this before extending):
This is NOT a trained CNN. There is no model file, no dataset, no transfer
learning happening here. What it DOES do is compute genuine, deterministic
features from the actual uploaded image's pixel data:

    - redness        : how red-dominant the image is (proxy for inflammation)
    - yellowness      : how yellow-tinted the image is (proxy for discharge/pus/fungal tint)
    - whiteness       : how bright/pale the image is (proxy for scaling/pallor)
    - variance        : local brightness variance (proxy for texture irregularity / swelling)
    - brightness      : overall exposure
    - sharpness       : simple edge-based blur estimate, for image-quality gating
    - heatmap_blocks  : a per-block redness/anomaly grid, used to render a
                         visual "attention map" overlay in place of Grad-CAM

This is an MVP substitute for a trained CNN + Grad-CAM. When a real model is
trained (see /models and /datasets), swap `extract_features()` for a model
forward pass and `heatmap_blocks` for real Grad-CAM activations — everything
downstream (condition_engine.py) consumes the same feature dict shape, so the
swap is contained to this file.
"""

from __future__ import annotations
from io import BytesIO
from typing import Dict, Any
from PIL import Image
import numpy as np


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def extract_features(image_bytes: bytes, max_dim: int = 384) -> Dict[str, Any]:
    """
    Load image bytes, downscale for speed, and compute real pixel-derived
    features. Returns a dict consumed by ai/rules/condition_engine.py.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    arr = np.asarray(img).astype(np.float32)  # H x W x 3

    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    brightness_map = (r + g + b) / 3.0
    brightness = float(brightness_map.mean())

    r_avg, g_avg, b_avg = float(r.mean()), float(g.mean()), float(b.mean())
    redness = _clamp01((r_avg - (g_avg + b_avg) / 2.0) / 60.0 + 0.15)
    yellowness = _clamp01(((r_avg + g_avg) / 2.0 - b_avg) / 60.0)
    whiteness = _clamp01((brightness - 140.0) / 100.0)

    variance = _clamp01(float(brightness_map.std()) / 60.0)
    sharpness = _estimate_sharpness(brightness_map)

    heatmap_blocks, bw, bh, block_size = _redness_heatmap(r, g, b)

    return {
        "redness": redness,
        "yellowness": yellowness,
        "whiteness": whiteness,
        "variance": variance,
        "brightness": brightness,
        "sharpness": sharpness,
        "heatmap_blocks": heatmap_blocks,
        "heatmap_grid": (bw, bh),
        "block_size": block_size,
        "image_size": img.size,
    }


def _estimate_sharpness(gray: np.ndarray) -> float:
    """Cheap blur estimate: variance of the horizontal second derivative."""
    if gray.shape[1] < 3:
        return 0.0
    lap = gray[:, :-2] - 2 * gray[:, 1:-1] + gray[:, 2:]
    return float(np.mean(np.abs(lap)))


def _redness_heatmap(r: np.ndarray, g: np.ndarray, b: np.ndarray, block_size: int = 16):
    """Grid-average redness per block -> used to render an attention overlay."""
    h, w = r.shape
    bw = max(1, w // block_size)
    bh = max(1, h // block_size)
    heat = np.zeros((bh, bw), dtype=np.float32)
    redness_map = r - (g + b) / 2.0
    for by in range(bh):
        for bx in range(bw):
            y0, y1 = by * block_size, min(h, (by + 1) * block_size)
            x0, x1 = bx * block_size, min(w, (bx + 1) * block_size)
            block = redness_map[y0:y1, x0:x1]
            heat[by, bx] = float(block.mean()) if block.size else 0.0
    return heat.tolist(), bw, bh, block_size


def quality_check(features: Dict[str, Any]) -> Dict[str, Any]:
    """Simple, honest image-quality gate (replaces the old file-size-only check)."""
    issues = []
    if features["brightness"] < 45:
        issues.append("Image appears too dark")
    if features["brightness"] > 235:
        issues.append("Image appears overexposed")
    if features["sharpness"] < 4.0:
        issues.append("Image may be blurry — try holding the camera steadier")
    return {"passed": len(issues) == 0, "issues": issues}


def render_heatmap_png_base64(image_bytes: bytes, features: Dict[str, Any]) -> str:
    """
    Overlay the heuristic attention map on the original image and return a
    base64 PNG data URL, for the frontend to display directly in an <img>.
    Labeled honestly as a heuristic map, not Grad-CAM, in the API response.
    """
    import base64

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    scale = min(1.0, 384 / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    w, h = img.size

    heat = np.array(features["heatmap_blocks"])
    block_size = features["block_size"]
    max_val = float(heat.max()) if heat.size and heat.max() > 0 else 1.0

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = overlay.load()
    bh, bw = heat.shape
    for by in range(bh):
        for bx in range(bw):
            val = _clamp01(heat[by, bx] / max_val)
            if val < 0.3:
                continue
            color = _heat_color(val)
            y0, y1 = by * block_size, min(h, (by + 1) * block_size)
            x0, x1 = bx * block_size, min(w, (bx + 1) * block_size)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    px[x, y] = color

    composed = Image.alpha_composite(img.convert("RGBA"), overlay)
    buf = BytesIO()
    composed.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _heat_color(v: float):
    r = int(60 + v * 180)
    g = int(140 - v * 100)
    b = int(200 - v * 180)
    alpha = int(120 * v + 60)
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), alpha)