"""Classify the photographic 'daylight phase' from time + location.

The category is computed from the sun's elevation above the horizon, not
from image content — LLaVA cannot reliably tell a warm Abendlicht from a
warm Innenraum. With a precise timestamp + GPS we can.

Elevation bands follow the PhotoPills / Wikipedia definitions:
  elevation >= +6°              → Tageslicht      (normal daylight)
  -4° <= elevation < +6°        → Goldene Stunde  (warm, low sun)
  -6° <= elevation < -4°        → Blaue Stunde    (sun below horizon,
                                                   sky still blue)
  elevation < -6°               → Nacht           (civil twilight or later)

If the default-location config is "NONE", images without GPS yield None
instead of falling back. Missing timestamps always yield None because
there is no sensible default for "when was this photo taken".
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import elevation

logger = logging.getLogger(__name__)

# Bavarian fallback locations. Regensburg sits near the geographic centre
# of Bavaria and is the default; Munich is offered as an alternative.
_FALLBACK_LOCATIONS: dict[str, tuple[float, float]] = {
    "BAYERN": (49.0134, 12.1016),   # Regensburg
    "MUNICH": (48.1374, 11.5754),   # München
}

VALID_LOCATIONS: frozenset[str] = frozenset({"BAYERN", "MUNICH", "NONE"})

# Naive EXIF datetimes without OffsetTimeOriginal are assumed to be in this
# timezone — correct for a Bavarian photographer, incorrect for travel
# photos. A ±2h tz error can flip Blaue/Goldene Stunde (narrow 2°-wide
# bands); Europe/Berlin is the least-bad default for the user's use case.
_DEFAULT_NAIVE_TZ = ZoneInfo("Europe/Berlin")


def _resolve_fallback(default_location: str) -> tuple[float, float] | None:
    key = (default_location or "").upper()
    if key == "NONE":
        return None
    return _FALLBACK_LOCATIONS.get(key)


def classify(
    when: dt.datetime | None,
    gps_lat: float | None,
    gps_lon: float | None,
    default_location: str = "BAYERN",
) -> str | None:
    """Return a German daylight-phase keyword, or None if it cannot be determined.

    ``when`` may be naive or tz-aware. Naive datetimes are interpreted as
    Europe/Berlin local time — the typical use case for this tool — because
    camera EXIF usually records the camera's local wall clock with no tz
    info. If OffsetTimeOriginal was present in EXIF, the datetime will be
    tz-aware here and we use that directly.
    """
    if when is None:
        return None

    lat, lon = gps_lat, gps_lon
    if lat is None or lon is None:
        fallback = _resolve_fallback(default_location)
        if fallback is None:
            return None
        lat, lon = fallback

    if when.tzinfo is None:
        when = when.replace(tzinfo=_DEFAULT_NAIVE_TZ)

    location = LocationInfo(
        name="photo", region="", timezone="UTC", latitude=lat, longitude=lon
    )
    try:
        sun_elev = elevation(location.observer, when)
    except Exception as e:
        logger.warning("Sun elevation calculation failed: %s", e, exc_info=True)
        return None

    if sun_elev >= 6.0:
        return "Tageslicht"
    if sun_elev >= -4.0:
        return "Goldene Stunde"
    if sun_elev >= -6.0:
        return "Blaue Stunde"
    return "Nacht"
