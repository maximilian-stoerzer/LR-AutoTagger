"""Unit tests for app.pipeline.exif_extractor."""

import datetime as dt

import pytest

from app.pipeline import exif_extractor


def test_empty_bytes_returns_empty_metadata():
    meta = exif_extractor.extract(b"")
    assert meta.datetime_original is None
    assert meta.gps_lat is None
    assert meta.gps_lon is None
    assert meta.focal_length_35mm is None


def test_corrupt_bytes_returns_empty_metadata():
    import os

    meta = exif_extractor.extract(os.urandom(2048))
    assert meta.datetime_original is None


def test_jpeg_without_exif(sample_jpeg):
    meta = exif_extractor.extract(sample_jpeg)
    assert meta.datetime_original is None
    assert meta.gps_lat is None
    assert meta.focal_length_35mm is None


def test_extracts_focal_length_35mm(jpeg_factory):
    data = jpeg_factory(focal_35mm=50)
    meta = exif_extractor.extract(data)
    assert meta.focal_length_35mm == 50.0


def test_extracts_datetime_original(jpeg_factory):
    data = jpeg_factory(datetime_original="2024:06:21 14:30:00")
    meta = exif_extractor.extract(data)
    # No OffsetTimeOriginal → naive datetime.
    assert meta.datetime_original == dt.datetime(2024, 6, 21, 14, 30, 0)
    assert meta.datetime_original.tzinfo is None


def test_extracts_datetime_with_offset(jpeg_factory):
    data = jpeg_factory(
        datetime_original="2024:06:21 14:30:00",
        offset_time_original="+02:00",
    )
    meta = exif_extractor.extract(data)
    assert meta.datetime_original is not None
    assert meta.datetime_original.tzinfo is not None
    assert meta.datetime_original.utcoffset() == dt.timedelta(hours=2)


def test_extracts_datetime_with_negative_offset(jpeg_factory):
    data = jpeg_factory(
        datetime_original="2024:06:21 14:30:00",
        offset_time_original="-05:00",
    )
    meta = exif_extractor.extract(data)
    assert meta.datetime_original is not None
    assert meta.datetime_original.utcoffset() == dt.timedelta(hours=-5)


def test_malformed_datetime_returns_none(jpeg_factory):
    data = jpeg_factory(datetime_original="not-a-date")
    meta = exif_extractor.extract(data)
    assert meta.datetime_original is None


def test_extracts_gps_north_east(jpeg_factory):
    data = jpeg_factory(gps_lat=49.0134, gps_lon=12.1016)
    meta = exif_extractor.extract(data)
    assert meta.gps_lat is not None
    assert meta.gps_lon is not None
    assert abs(meta.gps_lat - 49.0134) < 0.01
    assert abs(meta.gps_lon - 12.1016) < 0.01


def test_extracts_gps_south_west(jpeg_factory):
    data = jpeg_factory(gps_lat=-33.8688, gps_lon=-151.2093)
    meta = exif_extractor.extract(data)
    assert meta.gps_lat is not None
    assert meta.gps_lat < 0
    assert meta.gps_lon is not None
    assert meta.gps_lon < 0


def test_extracts_all_fields_together(jpeg_factory):
    data = jpeg_factory(
        focal_35mm=85,
        datetime_original="2023:12:24 18:00:00",
        gps_lat=48.1374,
        gps_lon=11.5754,
    )
    meta = exif_extractor.extract(data)
    assert meta.focal_length_35mm == 85.0
    assert meta.datetime_original == dt.datetime(2023, 12, 24, 18, 0, 0)
    assert meta.gps_lat is not None and abs(meta.gps_lat - 48.1374) < 0.01
    assert meta.gps_lon is not None and abs(meta.gps_lon - 11.5754) < 0.01


@pytest.mark.parametrize(
    "raw,expected",
    [
        ((1.0, 30.0, 0.0), 1.5),
        ((48.0, 8.0, 12.44), 48.0 + 8 / 60 + 12.44 / 3600),
    ],
)
def test_rational_to_degrees(raw, expected):
    # Pillow returns GPS triples as floats (or IFDRational, which float()'s
    # cleanly). The helper takes that shape, not nested numerator/denom tuples.
    result = exif_extractor._rational_to_degrees(raw)
    assert result is not None
    assert abs(result - expected) < 1e-4


def test_rational_to_degrees_rejects_wrong_shape():
    assert exif_extractor._rational_to_degrees(None) is None
    assert exif_extractor._rational_to_degrees((1.0, 2.0)) is None
    assert exif_extractor._rational_to_degrees(("a", "b", "c")) is None
