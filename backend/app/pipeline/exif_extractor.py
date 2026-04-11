"""Extract metadata from raw image bytes before resizing.

Reads EXIF fields that later pipeline stages (focal length classifier,
sun calculator) need. Extraction happens on the original bytes because
the resize step re-encodes the image and drops EXIF.
"""
from __future__ import annotations

import datetime as dt
import io
import logging
from dataclasses import dataclass

from PIL import ExifTags, Image

logger = logging.getLogger(__name__)


@dataclass
class ExifMetadata:
    """Subset of EXIF fields the pipeline uses.

    All fields are optional — absent values should disable the downstream
    step that needs them, not fail the whole request.
    """

    datetime_original: dt.datetime | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    focal_length_35mm: float | None = None  # 35mm equivalent in mm


# Pre-compute reverse lookups so we don't rebuild them on every call.
_EXIF_NAME_TO_TAG = {v: k for k, v in ExifTags.TAGS.items()}
_GPS_NAME_TO_TAG = {v: k for k, v in ExifTags.GPSTAGS.items()}


def _to_float(value) -> float | None:
    """Normalise Pillow rationals/tuples/floats to a plain float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rational_to_degrees(dms) -> float | None:
    """Convert an EXIF (deg, min, sec) rational tuple to decimal degrees."""
    if not dms or len(dms) != 3:
        return None
    try:
        deg = float(dms[0])
        minute = float(dms[1])
        sec = float(dms[2])
    except (TypeError, ValueError):
        return None
    return deg + minute / 60.0 + sec / 3600.0


def _parse_datetime(value: str | None) -> dt.datetime | None:
    """EXIF datetime format is 'YYYY:MM:DD HH:MM:SS' (camera-local, no tz)."""
    if not value or not isinstance(value, str):
        return None
    try:
        return dt.datetime.strptime(value.strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _parse_offset_time(value: str | None) -> dt.timezone | None:
    """Parse EXIF ``OffsetTimeOriginal`` ('+HH:MM' / '-HH:MM') to a fixed
    timezone. Modern cameras (post-2017-ish) write this; older cameras don't."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip("\x00 ")
    if len(s) != 6 or s[0] not in "+-" or s[3] != ":":
        return None
    try:
        hours = int(s[1:3])
        minutes = int(s[4:6])
    except ValueError:
        return None
    delta = dt.timedelta(hours=hours, minutes=minutes)
    if s[0] == "-":
        delta = -delta
    return dt.timezone(delta)


def _extract_gps(exif: Image.Exif) -> tuple[float | None, float | None]:
    gps_ifd_tag = _EXIF_NAME_TO_TAG.get("GPSInfo")
    if gps_ifd_tag is None:
        return None, None
    try:
        gps = exif.get_ifd(gps_ifd_tag)
    except (KeyError, AttributeError):
        return None, None
    if not gps:
        return None, None

    lat_tag = _GPS_NAME_TO_TAG.get("GPSLatitude")
    lat_ref_tag = _GPS_NAME_TO_TAG.get("GPSLatitudeRef")
    lon_tag = _GPS_NAME_TO_TAG.get("GPSLongitude")
    lon_ref_tag = _GPS_NAME_TO_TAG.get("GPSLongitudeRef")

    lat = _rational_to_degrees(gps.get(lat_tag))
    lon = _rational_to_degrees(gps.get(lon_tag))
    if lat is None or lon is None:
        return None, None

    if str(gps.get(lat_ref_tag, "N")).upper().startswith("S"):
        lat = -lat
    if str(gps.get(lon_ref_tag, "E")).upper().startswith("W"):
        lon = -lon
    return lat, lon


def _focal_length_35mm(exif: Image.Exif) -> float | None:
    """Return the 35mm-equivalent focal length in mm.

    Prefer the explicit ``FocalLengthIn35mmFilm`` tag if present. Otherwise
    compute it from the actual focal length and the sensor width derived
    from ``FocalPlaneXResolution`` + ``PixelXDimension`` +
    ``FocalPlaneResolutionUnit``. Focal-length fields live in the Exif
    sub-IFD (0x8769), not the main block.
    """
    # The EXIF sub-IFD holds FocalLength*, FocalPlane* and PixelXDimension.
    exif_ifd_tag = _EXIF_NAME_TO_TAG.get("ExifOffset")
    try:
        sub = exif.get_ifd(exif_ifd_tag) if exif_ifd_tag else {}
    except (KeyError, AttributeError):
        sub = {}

    f35 = _to_float(sub.get(_EXIF_NAME_TO_TAG.get("FocalLengthIn35mmFilm")))
    if f35 and f35 > 0:
        return f35

    focal = _to_float(sub.get(_EXIF_NAME_TO_TAG.get("FocalLength")))
    if not focal or focal <= 0:
        return None

    fp_x_res = _to_float(sub.get(_EXIF_NAME_TO_TAG.get("FocalPlaneXResolution")))
    # PixelXDimension is exposed as 'ExifImageWidth' in Pillow's ExifTags.TAGS.
    px_x = _to_float(sub.get(_EXIF_NAME_TO_TAG.get("ExifImageWidth")))
    unit = sub.get(_EXIF_NAME_TO_TAG.get("FocalPlaneResolutionUnit"))
    if not fp_x_res or not px_x or not unit:
        return None

    # Unit: 2 = inches, 3 = cm, 4 = mm, 5 = µm (EXIF spec).
    unit_to_mm = {2: 25.4, 3: 10.0, 4: 1.0, 5: 0.001}
    unit_mm = unit_to_mm.get(int(unit))
    if not unit_mm:
        return None

    sensor_width_mm = (px_x / fp_x_res) * unit_mm
    if sensor_width_mm <= 0:
        return None
    crop_factor = 36.0 / sensor_width_mm
    return focal * crop_factor


def extract(image_data: bytes) -> ExifMetadata:
    """Parse the EXIF block of a JPEG/TIFF byte stream.

    Always returns an ExifMetadata — fields are None when the respective
    tag is missing or unreadable. Parsing errors are logged and swallowed.
    """
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            exif = img.getexif()
    except Exception as e:
        logger.debug("EXIF extraction failed: %s", e)
        return ExifMetadata()

    if not exif:
        return ExifMetadata()

    # DateTimeOriginal lives in the Exif sub-IFD; DateTime is in the main
    # block. Read the sub-IFD once for the datetime + offset lookup and for
    # the focal-length classifier downstream.
    exif_ifd_tag = _EXIF_NAME_TO_TAG.get("ExifOffset")
    sub: dict = {}
    if exif_ifd_tag:
        try:
            sub = exif.get_ifd(exif_ifd_tag)
        except (KeyError, AttributeError):
            sub = {}

    datetime_original = _parse_datetime(
        sub.get(_EXIF_NAME_TO_TAG.get("DateTimeOriginal"))
        or exif.get(_EXIF_NAME_TO_TAG.get("DateTimeOriginal"))
        or exif.get(_EXIF_NAME_TO_TAG.get("DateTime"))
    )
    if datetime_original is not None:
        offset = _parse_offset_time(
            sub.get(_EXIF_NAME_TO_TAG.get("OffsetTimeOriginal"))
            or sub.get(_EXIF_NAME_TO_TAG.get("OffsetTime"))
        )
        if offset is not None:
            datetime_original = datetime_original.replace(tzinfo=offset)

    try:
        gps_lat, gps_lon = _extract_gps(exif)
    except Exception as e:
        logger.warning("EXIF GPS parsing failed: %s", e, exc_info=True)
        gps_lat, gps_lon = None, None

    try:
        focal_length_35mm = _focal_length_35mm(exif)
    except Exception as e:
        logger.warning("EXIF focal length parsing failed: %s", e, exc_info=True)
        focal_length_35mm = None

    return ExifMetadata(
        datetime_original=datetime_original,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        focal_length_35mm=focal_length_35mm,
    )
