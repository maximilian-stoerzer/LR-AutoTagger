"""Unit tests for app.pipeline.pixel_analyzer."""

import io

from PIL import Image

from app.pipeline.pixel_analyzer import analyze


def _make_color_jpeg(r=200, g=100, b=50):
    img = Image.new("RGB", (64, 48), (r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_gray_jpeg():
    img = Image.new("L", (64, 48), 128)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_desaturated_jpeg():
    """Very low saturation but still RGB — simulates a B&W-looking color image."""
    img = Image.new("RGB", (64, 48), (128, 128, 130))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_color_image_is_not_bw():
    result = analyze(_make_color_jpeg())
    assert result.is_bw is False
    assert result.mean_saturation is not None
    assert result.mean_saturation > 15


def test_grayscale_mode_is_bw():
    result = analyze(_make_gray_jpeg())
    assert result.is_bw is True
    assert result.mean_saturation == 0.0


def test_desaturated_rgb_is_bw():
    result = analyze(_make_desaturated_jpeg())
    assert result.is_bw is True
    assert result.mean_saturation is not None
    assert result.mean_saturation < 15


def test_corrupt_image_returns_defaults():
    result = analyze(b"not an image")
    assert result.is_bw is False
    assert result.mean_saturation is None
