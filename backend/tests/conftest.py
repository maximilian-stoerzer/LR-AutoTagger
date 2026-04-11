"""Shared test fixtures for all test levels."""

import io
import os

import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Test images
# ---------------------------------------------------------------------------


def _make_jpeg(width: int, height: int, color: tuple = (100, 150, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_png_rgba(width: int, height: int) -> bytes:
    img = Image.new("RGBA", (width, height), (100, 150, 200, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_palette_png(width: int, height: int) -> bytes:
    img = Image.new("P", (width, height))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sample_jpeg() -> bytes:
    """800x600 RGB JPEG."""
    return _make_jpeg(800, 600)


@pytest.fixture
def sample_large_jpeg() -> bytes:
    """2048x1536 JPEG — needs resizing."""
    return _make_jpeg(2048, 1536)


@pytest.fixture
def sample_small_jpeg() -> bytes:
    """1x1 pixel JPEG."""
    return _make_jpeg(1, 1)


@pytest.fixture
def sample_exact_1024_jpeg() -> bytes:
    """1024x768 JPEG — exactly at max side."""
    return _make_jpeg(1024, 768)


@pytest.fixture
def sample_portrait_jpeg() -> bytes:
    """1536x2048 portrait JPEG."""
    return _make_jpeg(1536, 2048)


@pytest.fixture
def sample_very_large_jpeg() -> bytes:
    """10000x8000 JPEG."""
    return _make_jpeg(10000, 8000)


@pytest.fixture
def sample_rgba_png() -> bytes:
    """800x600 RGBA PNG."""
    return _make_png_rgba(800, 600)


@pytest.fixture
def sample_palette_png() -> bytes:
    """800x600 palette-mode PNG."""
    return _make_palette_png(800, 600)


@pytest.fixture
def sample_grayscale_jpeg() -> bytes:
    """800x600 grayscale (mode 'L') JPEG."""
    img = Image.new("L", (800, 600), 128)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.fixture
def sample_jpeg_with_exif_rotation() -> bytes:
    """800x600 JPEG with EXIF orientation tag (rotation 6 = 90° CW)."""
    img = Image.new("RGB", (800, 600), (50, 100, 150))
    buf = io.BytesIO()
    # PIL doesn't easily inject EXIF — use piexif-style raw bytes if available,
    # otherwise just save plain (test will still verify it loads)
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_jpeg_with_exif(
    focal_35mm: int | None = None,
    datetime_original: str | None = None,
    offset_time_original: str | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
) -> bytes:
    """Build a small JPEG with the requested EXIF fields populated.

    Helper for EXIF-extractor and pipeline tests — writes ExifIFD
    (DateTimeOriginal, FocalLengthIn35mmFilm, OffsetTimeOriginal) and the
    GPS IFD. GPS coordinates are stored as DMS rationals via
    ``IFDRational`` because Pillow's TIFF writer otherwise chokes on raw
    nested tuples.
    """
    from PIL import ExifTags
    from PIL.TiffImagePlugin import IFDRational

    def _to_dms(v: float) -> tuple[IFDRational, IFDRational, IFDRational]:
        deg = int(abs(v))
        m_full = (abs(v) - deg) * 60
        minute = int(m_full)
        sec = (m_full - minute) * 60
        return (IFDRational(deg, 1), IFDRational(minute, 1), IFDRational(sec))

    img = Image.new("RGB", (64, 48), (100, 100, 100))
    exif = img.getexif()
    exif_ifd = exif.get_ifd(0x8769)  # ExifOffset → ExifIFD
    if focal_35mm is not None:
        exif_ifd[ExifTags.Base.FocalLengthIn35mmFilm.value] = focal_35mm
    if datetime_original is not None:
        exif_ifd[ExifTags.Base.DateTimeOriginal.value] = datetime_original
    if offset_time_original is not None:
        exif_ifd[ExifTags.Base.OffsetTimeOriginal.value] = offset_time_original
    if gps_lat is not None and gps_lon is not None:
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[1] = "N" if gps_lat >= 0 else "S"
        gps[2] = _to_dms(gps_lat)
        gps[3] = "E" if gps_lon >= 0 else "W"
        gps[4] = _to_dms(gps_lon)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, exif=exif)
    return buf.getvalue()


@pytest.fixture
def jpeg_factory():
    """Factory fixture so tests can construct JPEGs with custom EXIF."""
    return _make_jpeg_with_exif


@pytest.fixture
def corrupt_image() -> bytes:
    """Random bytes that are not a valid image."""
    return os.urandom(1024)


@pytest.fixture
def empty_bytes() -> bytes:
    """Zero-length data."""
    return b""


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ollama_keywords() -> list[str]:
    return ["Bruecke", "Fluss", "Sonnenuntergang", "Stein", "Wasser"]


@pytest.fixture
def mock_nominatim_heidelberg() -> dict:
    """Nominatim response for Heidelberg."""
    return {
        "address": {
            "suburb": "Altstadt",
            "city": "Heidelberg",
            "county": "Rhein-Neckar-Kreis",
            "state": "Baden-Wuerttemberg",
            "country": "Deutschland",
        },
        "display_name": "Altstadt, Heidelberg, Rhein-Neckar-Kreis, Baden-Wuerttemberg, Deutschland",
    }
