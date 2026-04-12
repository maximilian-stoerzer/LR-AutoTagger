"""Unit tests for app.pipeline.prompt_builder."""

import datetime as dt

from app.pipeline.exif_extractor import ExifMetadata
from app.pipeline.pixel_analyzer import PixelAnalysis
from app.pipeline.prompt_builder import build


def test_full_exif_omits_tageszeit_jahreszeit():
    """When EXIF has datetime, Tageszeit + Jahreszeit should NOT appear in prompt."""
    exif = ExifMetadata(
        datetime_original=dt.datetime(2024, 3, 2, 14, 30),
        focal_length_35mm=32.0,
        f_number=13.0,
        exposure_time=1 / 250,
    )
    pixels = PixelAnalysis(is_bw=False, mean_saturation=80.0)
    prompt = build(exif, pixels)

    assert "Tageszeit" not in prompt
    assert "Jahreszeit" not in prompt
    assert "Objekte" in prompt
    assert "Wetter" in prompt
    assert "Lichtsituation" in prompt
    assert "Perspektive" in prompt


def test_no_exif_includes_tageszeit_jahreszeit():
    """Without EXIF datetime, prompt must ask model for Tageszeit + Jahreszeit."""
    exif = ExifMetadata()
    pixels = PixelAnalysis()
    prompt = build(exif, pixels)

    assert "Tageszeit" in prompt
    assert "Jahreszeit" in prompt


def test_color_image_removes_schwarzweiss_from_technik():
    """Color image → Schwarzweiss should NOT appear in the Technik whitelist."""
    exif = ExifMetadata()
    pixels = PixelAnalysis(is_bw=False, mean_saturation=80.0)
    prompt = build(exif, pixels)

    # Schwarzweiss should be absent from the Technik line.
    # Find the Technik line and check.
    for line in prompt.split("\n"):
        if line.startswith("- Technik"):
            assert "Schwarzweiss" not in line
            assert "Makro" in line  # others should still be there
            break


def test_high_fnumber_removes_bokeh():
    """f/13 at 32mm → Bokeh should be vetoed from Technik whitelist."""
    exif = ExifMetadata(f_number=13.0, focal_length_35mm=32.0)
    pixels = PixelAnalysis(is_bw=False, mean_saturation=80.0)
    prompt = build(exif, pixels)

    for line in prompt.split("\n"):
        if line.startswith("- Technik"):
            assert "Bokeh" not in line
            break


def test_fast_shutter_removes_langzeitbelichtung():
    """1/1000s → Langzeitbelichtung should be vetoed."""
    exif = ExifMetadata(exposure_time=1 / 1000)
    pixels = PixelAnalysis()
    prompt = build(exif, pixels)

    for line in prompt.split("\n"):
        if line.startswith("- Technik"):
            assert "Langzeitbelichtung" not in line
            break


def test_wide_angle_removes_makro():
    """21mm → Makro should be vetoed."""
    exif = ExifMetadata(focal_length_35mm=21.0)
    pixels = PixelAnalysis()
    prompt = build(exif, pixels)

    for line in prompt.split("\n"):
        if line.startswith("- Technik"):
            assert "Makro" not in line
            break


def test_all_technik_vetoed_removes_category():
    """If ALL Technik values are vetoed, the whole category should be absent."""
    exif = ExifMetadata(
        f_number=16.0,
        focal_length_35mm=21.0,
        exposure_time=1 / 1000,
    )
    pixels = PixelAnalysis(is_bw=False, mean_saturation=80.0)
    prompt = build(exif, pixels)

    # With f/16 + 21mm + 1/1000s + color:
    # Bokeh vetoed (f/16 > 5.6 AND 21mm < 85)
    # Makro vetoed (21mm < 35)
    # Langzeitbelichtung vetoed (1/1000 < 1/60)
    # Schwarzweiss vetoed (color)
    # Remaining: Bewegungsunschaerfe, Infrarot — should still be in prompt
    # The "- Technik" category line (not the CoT hint line).
    technik_lines = [l for l in prompt.split("\n") if l.startswith("- Technik")]
    assert len(technik_lines) == 1
    assert "Bewegungsunschaerfe" in technik_lines[0]
    assert "Infrarot" in technik_lines[0]


def test_prompt_always_has_core_categories():
    """Regardless of EXIF, the core categories must always be present."""
    exif = ExifMetadata()
    pixels = PixelAnalysis()
    prompt = build(exif, pixels)

    assert "Objekte" in prompt
    assert "Szene" in prompt
    assert "Umgebung" in prompt
    assert "Wetter" in prompt
    assert "Stimmung" in prompt
    assert "Lichtsituation" in prompt
    assert "Perspektive" in prompt
    assert "wahrscheinlichsten" in prompt
