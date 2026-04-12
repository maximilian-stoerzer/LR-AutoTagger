"""Unit tests for app.pipeline.exif_classifier."""

import datetime as dt

import pytest

from app.pipeline.exif_classifier import (
    classify_focal_length,
    classify_season,
    classify_time_of_day,
    derive_keywords,
    get_technik_vetos,
    should_add_kunstlicht,
    should_add_langzeitbelichtung,
    should_veto_bokeh,
    should_veto_langzeitbelichtung,
    should_veto_makro,
)
from app.pipeline.exif_extractor import ExifMetadata
from app.pipeline.pixel_analyzer import PixelAnalysis


# --- Focal length (migrated from test_focal_length_classifier) ---

@pytest.mark.parametrize("focal,expected", [
    (10, "Superweitwinkel"), (24, "Weitwinkel"), (50, "Normalbrennweite"),
    (135, "Teleobjektiv"), (400, "Supertele"), (None, None), (0, None),
])
def test_classify_focal_length(focal, expected):
    assert classify_focal_length(focal) == expected


# --- Season ---

@pytest.mark.parametrize("month,expected", [
    (1, "Winter"), (3, "Fruehling"), (6, "Sommer"),
    (9, "Herbst"), (12, "Winter"),
])
def test_classify_season(month, expected):
    when = dt.datetime(2024, month, 15, 12, 0)
    assert classify_season(when) == expected


def test_classify_season_none():
    assert classify_season(None) is None


# --- Time of day ---

def test_time_of_day_noon():
    noon = dt.datetime(2024, 6, 21, 12, 0, tzinfo=dt.timezone.utc)
    result = classify_time_of_day(noon, 49.0, 12.0, "BAYERN")
    assert result == "Mittag"


def test_time_of_day_none_datetime():
    assert classify_time_of_day(None, 49.0, 12.0) is None


def test_time_of_day_no_gps_no_fallback():
    noon = dt.datetime(2024, 6, 21, 12, 0)
    result = classify_time_of_day(noon, None, None, "NONE")
    assert result == "Mittag"  # hour-based fallback


def test_time_of_day_midnight():
    midnight = dt.datetime(2024, 6, 21, 1, 0, tzinfo=dt.timezone.utc)
    result = classify_time_of_day(midnight, 49.0, 12.0, "BAYERN")
    assert result == "Nacht"


# --- Technik vetos ---

def test_veto_bokeh_high_fnumber():
    exif = ExifMetadata(f_number=13.0, focal_length_35mm=32.0)
    assert should_veto_bokeh(exif) is True


def test_no_veto_bokeh_low_fnumber():
    exif = ExifMetadata(f_number=2.0, focal_length_35mm=85.0)
    assert should_veto_bokeh(exif) is False


def test_no_veto_bokeh_high_fnumber_long_focal():
    exif = ExifMetadata(f_number=8.0, focal_length_35mm=200.0)
    assert should_veto_bokeh(exif) is False


def test_veto_langzeit_fast_shutter():
    exif = ExifMetadata(exposure_time=1 / 1000)
    assert should_veto_langzeitbelichtung(exif) is True


def test_no_veto_langzeit_slow_shutter():
    exif = ExifMetadata(exposure_time=0.5)
    assert should_veto_langzeitbelichtung(exif) is False


def test_add_langzeit_over_1s():
    exif = ExifMetadata(exposure_time=2.0)
    assert should_add_langzeitbelichtung(exif) is True


def test_no_add_langzeit_under_1s():
    exif = ExifMetadata(exposure_time=0.5)
    assert should_add_langzeitbelichtung(exif) is False


def test_veto_makro_wide_angle():
    exif = ExifMetadata(focal_length_35mm=21.0)
    assert should_veto_makro(exif) is True


def test_no_veto_makro_tele():
    exif = ExifMetadata(focal_length_35mm=100.0)
    assert should_veto_makro(exif) is False


def test_add_kunstlicht_flash():
    exif = ExifMetadata(flash_fired=True)
    assert should_add_kunstlicht(exif) is True


def test_no_kunstlicht_no_flash():
    exif = ExifMetadata(flash_fired=False)
    assert should_add_kunstlicht(exif) is False


# --- derive_keywords ---

def test_derive_keywords_full_exif():
    exif = ExifMetadata(
        datetime_original=dt.datetime(2024, 3, 2, 14, 30),
        focal_length_35mm=32.0,
        exposure_time=1 / 250,
        f_number=13.0,
        flash_fired=False,
    )
    pixels = PixelAnalysis(is_bw=False, mean_saturation=80.0)
    kws = derive_keywords(exif, pixels)
    assert "Weitwinkel" in kws
    assert "Fruehling" in kws
    assert "Schwarzweiss" not in kws
    assert "Langzeitbelichtung" not in kws


def test_derive_keywords_bw_image():
    exif = ExifMetadata(datetime_original=dt.datetime(2024, 12, 1, 10, 0))
    pixels = PixelAnalysis(is_bw=True, mean_saturation=3.0)
    kws = derive_keywords(exif, pixels)
    assert "Schwarzweiss" in kws
    assert "Winter" in kws


def test_derive_keywords_long_exposure_flash():
    exif = ExifMetadata(exposure_time=5.0, flash_fired=True)
    pixels = PixelAnalysis(is_bw=False, mean_saturation=60.0)
    kws = derive_keywords(exif, pixels)
    assert "Langzeitbelichtung" in kws
    assert "Kunstlicht" in kws


# --- get_technik_vetos ---

def test_vetos_for_landscape_setup():
    """f/13 at 21mm (APS-C ~32mm equiv) → veto Bokeh + Makro."""
    exif = ExifMetadata(f_number=13.0, focal_length_35mm=32.0, exposure_time=1 / 250)
    pixels = PixelAnalysis(is_bw=False, mean_saturation=80.0)
    vetos = get_technik_vetos(exif, pixels)
    assert "Bokeh" in vetos
    assert "Makro" in vetos
    assert "Langzeitbelichtung" in vetos
    assert "Schwarzweiss" in vetos  # color image → don't ask model about SW


def test_no_vetos_for_portrait_setup():
    """f/2.0 at 85mm, slow shutter → no vetos except SW on color."""
    exif = ExifMetadata(f_number=2.0, focal_length_35mm=85.0, exposure_time=1 / 125)
    pixels = PixelAnalysis(is_bw=False, mean_saturation=60.0)
    vetos = get_technik_vetos(exif, pixels)
    assert "Bokeh" not in vetos
    assert "Makro" not in vetos
    assert "Schwarzweiss" in vetos  # still vetoed because it's a color image
