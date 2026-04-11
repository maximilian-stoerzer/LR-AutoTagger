"""Unit tests for app.pipeline.sun_calculator."""

import datetime as dt

import pytest

from app.pipeline import sun_calculator

# Munich, roughly.
MUC_LAT = 48.1374
MUC_LON = 11.5754


def test_no_datetime_returns_none():
    assert sun_calculator.classify(None, MUC_LAT, MUC_LON, "BAYERN") is None


def test_no_gps_with_default_bayern_uses_fallback():
    # Noon on the summer solstice — should be clearly Tageslicht whether we
    # fall back to Regensburg or use the passed coordinates.
    noon = dt.datetime(2024, 6, 21, 10, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(noon, None, None, "BAYERN") == "Tageslicht"


def test_no_gps_with_default_none_skips_tagging():
    noon = dt.datetime(2024, 6, 21, 10, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(noon, None, None, "NONE") is None


def test_no_gps_with_default_munich_uses_fallback():
    noon = dt.datetime(2024, 6, 21, 10, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(noon, None, None, "MUNICH") == "Tageslicht"


def test_unknown_default_location_treated_as_no_fallback():
    noon = dt.datetime(2024, 6, 21, 10, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(noon, None, None, "ATLANTIS") is None


def test_summer_solstice_noon_tageslicht():
    # 21 Jun 2024 12:00 CEST = 10:00 UTC, Munich. Sun is ~60° up.
    t = dt.datetime(2024, 6, 21, 10, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(t, MUC_LAT, MUC_LON, "BAYERN") == "Tageslicht"


def test_midnight_is_nacht():
    # 21 Jun 2024 00:00 UTC, Munich. Sun is well below horizon.
    t = dt.datetime(2024, 6, 21, 0, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(t, MUC_LAT, MUC_LON, "BAYERN") == "Nacht"


def test_winter_midday_still_tageslicht():
    # 21 Dec 2024 12:00 CET = 11:00 UTC, Munich. Sun is ~17° up.
    t = dt.datetime(2024, 12, 21, 11, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(t, MUC_LAT, MUC_LON, "BAYERN") == "Tageslicht"


def test_naive_datetime_is_treated_as_europe_berlin():
    # Naive EXIF-style datetimes are assumed to be camera-local time in
    # Europe/Berlin — the Bavarian user's default. 12:00 local in June is
    # mid-day regardless of tz interpretation, so this is clearly Tageslicht.
    naive = dt.datetime(2024, 6, 21, 12, 0)
    assert sun_calculator.classify(naive, MUC_LAT, MUC_LON, "BAYERN") == "Tageslicht"


def test_tz_aware_datetime_is_respected():
    # A datetime from a camera that wrote OffsetTimeOriginal should be used
    # verbatim. 12:00 UTC on summer solstice in Munich = 14:00 CEST, also
    # Tageslicht.
    aware = dt.datetime(2024, 6, 21, 12, 0, tzinfo=dt.timezone.utc)
    assert sun_calculator.classify(aware, MUC_LAT, MUC_LON, "BAYERN") == "Tageslicht"


@pytest.mark.parametrize(
    "elevation_target,expected",
    [
        (+30.0, "Tageslicht"),
        (+6.0, "Tageslicht"),
        (+5.999, "Goldene Stunde"),
        (+2.0, "Goldene Stunde"),
        (-4.0, "Goldene Stunde"),  # -4° is the lower bound of golden hour
        (-4.001, "Blaue Stunde"),
        (-5.0, "Blaue Stunde"),
        (-6.0, "Blaue Stunde"),
        (-6.001, "Nacht"),
        (-8.0, "Nacht"),
    ],
)
def test_elevation_bands_via_monkeypatch(monkeypatch, elevation_target, expected):
    """Stub astral.sun.elevation so we can verify the band boundaries exactly."""
    import app.pipeline.sun_calculator as sc

    monkeypatch.setattr(sc, "elevation", lambda observer, when: elevation_target)
    t = dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
    assert sc.classify(t, MUC_LAT, MUC_LON, "BAYERN") == expected
