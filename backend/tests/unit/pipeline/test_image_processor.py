"""Unit tests for app.pipeline.image_processor — U-IMG-01 to U-IMG-10."""

import io

import pytest
from PIL import Image

from app.pipeline.image_processor import resize_for_analysis


def _dimensions(data: bytes) -> tuple[int, int]:
    img = Image.open(io.BytesIO(data))
    return img.size  # (width, height)


def _mode(data: bytes) -> str:
    return Image.open(io.BytesIO(data)).mode


# U-IMG-01
def test_jpeg_under_max_unchanged_size(sample_jpeg):
    result = resize_for_analysis(sample_jpeg)
    w, h = _dimensions(result)
    assert w == 800
    assert h == 600


# U-IMG-02
def test_large_jpeg_resized(sample_large_jpeg):
    result = resize_for_analysis(sample_large_jpeg)
    w, h = _dimensions(result)
    assert max(w, h) == 1024
    assert w == 1024
    assert h == 768


# U-IMG-03
def test_portrait_resized_correctly(sample_portrait_jpeg):
    result = resize_for_analysis(sample_portrait_jpeg)
    w, h = _dimensions(result)
    assert max(w, h) == 1024
    assert h == 1024
    assert w == 768


# U-IMG-04
def test_rgba_converted_to_rgb(sample_rgba_png):
    result = resize_for_analysis(sample_rgba_png)
    assert _mode(result) == "RGB"


# U-IMG-05
def test_minimal_1x1_image(sample_small_jpeg):
    result = resize_for_analysis(sample_small_jpeg)
    w, h = _dimensions(result)
    assert w == 1
    assert h == 1


# U-IMG-06
def test_exact_1024_unchanged(sample_exact_1024_jpeg):
    result = resize_for_analysis(sample_exact_1024_jpeg)
    w, h = _dimensions(result)
    assert w == 1024
    assert h == 768


# U-IMG-07
def test_very_large_image_resized(sample_very_large_jpeg):
    result = resize_for_analysis(sample_very_large_jpeg)
    w, h = _dimensions(result)
    assert max(w, h) == 1024


# U-IMG-08
def test_corrupt_image_raises(corrupt_image):
    with pytest.raises(Exception):
        resize_for_analysis(corrupt_image)


# U-IMG-09
def test_empty_bytes_raises(empty_bytes):
    with pytest.raises(Exception):
        resize_for_analysis(empty_bytes)


# U-IMG-10
def test_palette_png_converted_to_rgb(sample_palette_png):
    result = resize_for_analysis(sample_palette_png)
    assert _mode(result) in ("RGB", "L")


# Additional: output is always JPEG
def test_output_is_jpeg(sample_jpeg):
    result = resize_for_analysis(sample_jpeg)
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


# U-IMG-11: Grayscale (mode 'L') is preserved/handled
def test_grayscale_jpeg_handled(sample_grayscale_jpeg):
    result = resize_for_analysis(sample_grayscale_jpeg)
    # Should not crash; mode 'L' is allowed without conversion
    img = Image.open(io.BytesIO(result))
    assert img.mode in ("L", "RGB")
    assert img.format == "JPEG"


# U-IMG-12: Resize ratio rounding edge case
def test_non_square_resize_aspect_ratio():
    # 500x2000 → ratio 1024/2000 = 0.512 → (256, 1024)
    img = Image.new("RGB", (500, 2000), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    result = resize_for_analysis(buf.getvalue())

    out = Image.open(io.BytesIO(result))
    assert max(out.size) == 1024
    assert out.size == (256, 1024)
