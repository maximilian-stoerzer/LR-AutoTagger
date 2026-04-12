"""Pixel-level image analysis that doesn't need a vision model.

Currently: black-and-white detection via HSV saturation. Runs on the
original image bytes before resize — cheap (one Pillow convert + numpy
mean) and deterministic.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger(__name__)

# Mean saturation below this threshold (0-255 scale) → black & white.
# 15 is conservative: most true B&W images have saturation < 5, while
# desaturated colour images are typically 30+.
BW_SATURATION_THRESHOLD = 15


@dataclass
class PixelAnalysis:
    is_bw: bool = False
    mean_saturation: float | None = None


def analyze(image_data: bytes) -> PixelAnalysis:
    """Analyze pixel data for properties that are cheaper and more
    reliable than asking a vision model."""
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            # Grayscale mode images are trivially B&W.
            if img.mode in ("L", "LA", "1"):
                return PixelAnalysis(is_bw=True, mean_saturation=0.0)

            hsv = img.convert("HSV")
            # S channel is index 1 in HSV. Split and compute mean.
            s_channel = hsv.split()[1]
            # Use Pillow's built-in stat to avoid a numpy dependency.
            from PIL import ImageStat
            stat = ImageStat.Stat(s_channel)
            mean_s = stat.mean[0]  # 0-255 scale

            return PixelAnalysis(
                is_bw=mean_s < BW_SATURATION_THRESHOLD,
                mean_saturation=round(mean_s, 1),
            )
    except Exception as e:
        logger.warning("Pixel analysis failed: %s", e)
        return PixelAnalysis()
