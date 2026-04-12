"""Derive keywords deterministically from EXIF metadata and pixel analysis.

These classifications are more reliable than asking the vision model
because they use measured camera data, not visual interpretation. The
pipeline calls these BEFORE sending to Ollama and uses the results to
(a) add deterministic keywords and (b) shorten the prompt by removing
categories the model doesn't need to guess.

Replaces the earlier single-purpose focal_length_classifier.py.
"""
from __future__ import annotations

import datetime as dt
import logging

from app.pipeline.exif_extractor import ExifMetadata
from app.pipeline.pixel_analyzer import PixelAnalysis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Focal length → Brennweite (unchanged logic from focal_length_classifier)
# ---------------------------------------------------------------------------

def classify_focal_length(focal_35mm: float | None) -> str | None:
    if focal_35mm is None or focal_35mm <= 0:
        return None
    if focal_35mm < 24:
        return "Superweitwinkel"
    if focal_35mm < 35:
        return "Weitwinkel"
    if focal_35mm < 70:
        return "Normalbrennweite"
    if focal_35mm <= 200:
        return "Teleobjektiv"
    return "Supertele"


# ---------------------------------------------------------------------------
# Jahreszeit from month (meteorological seasons, Central Europe)
# ---------------------------------------------------------------------------

_MONTH_TO_SEASON = {
    1: "Winter", 2: "Winter", 3: "Fruehling",
    4: "Fruehling", 5: "Fruehling", 6: "Sommer",
    7: "Sommer", 8: "Sommer", 9: "Herbst",
    10: "Herbst", 11: "Herbst", 12: "Winter",
}


def classify_season(when: dt.datetime | None) -> str | None:
    if when is None:
        return None
    return _MONTH_TO_SEASON.get(when.month)


# ---------------------------------------------------------------------------
# Tageszeit from sun elevation (via astral) — latitude-aware, not just hour
# ---------------------------------------------------------------------------

def classify_time_of_day(
    when: dt.datetime | None,
    gps_lat: float | None,
    gps_lon: float | None,
    default_location: str = "BAYERN",
) -> str | None:
    """Classify time of day based on sun elevation — more accurate than
    fixed hour boundaries because it adapts to latitude and season.

    Falls back to hour-based classification if GPS is unavailable and
    default_location is NONE.
    """
    if when is None:
        return None

    # Try sun-elevation-based classification first.
    from app.pipeline.sun_calculator import _resolve_fallback, _DEFAULT_NAIVE_TZ
    from astral import LocationInfo
    from astral.sun import elevation

    lat, lon = gps_lat, gps_lon
    if lat is None or lon is None:
        fallback = _resolve_fallback(default_location)
        if fallback is None:
            return _classify_time_by_hour(when)
        lat, lon = fallback

    aware = when if when.tzinfo else when.replace(tzinfo=_DEFAULT_NAIVE_TZ)
    loc = LocationInfo(name="photo", region="", timezone="UTC", latitude=lat, longitude=lon)

    try:
        elev = elevation(loc.observer, aware)
    except Exception:
        return _classify_time_by_hour(when)

    # Sun elevation → time of day.
    # Below horizon:
    if elev < -6:
        return "Nacht"
    if elev < 0:
        return "Daemmerung"
    # Low sun (within ~1h of sunrise/sunset):
    if elev < 15:
        # Distinguish morning from evening by checking if sun is rising or
        # setting. Simple heuristic: compare to solar noon.
        try:
            from astral.sun import noon as solar_noon
            sn = solar_noon(loc.observer, aware)
            if aware < sn:
                return "Morgen" if elev < 10 else "Vormittag"
            else:
                return "Abend"
        except Exception:
            return "Morgen"
    # High sun:
    if elev > 50:
        return "Mittag"
    # Mid elevation — use hour as tiebreaker.
    return _classify_time_by_hour(when)


def _classify_time_by_hour(when: dt.datetime) -> str:
    """Fallback: simple hour-based classification."""
    h = when.hour
    if h < 5:
        return "Nacht"
    if h < 8:
        return "Morgengrauen" if h < 6 else "Morgen"
    if h < 11:
        return "Vormittag"
    if h < 14:
        return "Mittag"
    if h < 17:
        return "Nachmittag"
    if h < 20:
        return "Abend"
    if h < 22:
        return "Daemmerung"
    return "Nacht"


# ---------------------------------------------------------------------------
# Technik vetos + adds from exposure triangle
# ---------------------------------------------------------------------------

def should_veto_bokeh(exif: ExifMetadata) -> bool:
    """Reject Bokeh if the aperture is too narrow for shallow DOF."""
    if exif.f_number is None:
        return False
    if exif.f_number > 5.6 and (exif.focal_length_35mm is None or exif.focal_length_35mm < 85):
        return True
    return False


def should_veto_langzeitbelichtung(exif: ExifMetadata) -> bool:
    """Reject Langzeitbelichtung if shutter speed is too fast."""
    if exif.exposure_time is None:
        return False
    return exif.exposure_time < (1 / 60)


def should_add_langzeitbelichtung(exif: ExifMetadata) -> bool:
    """Add Langzeitbelichtung deterministically if shutter > 1s."""
    if exif.exposure_time is None:
        return False
    return exif.exposure_time >= 1.0


def should_veto_makro(exif: ExifMetadata) -> bool:
    """Reject Makro if the focal length is wide-angle."""
    if exif.focal_length_35mm is None:
        return False
    return exif.focal_length_35mm < 35


def should_add_kunstlicht(exif: ExifMetadata) -> bool:
    """Add Kunstlicht if flash was fired."""
    return exif.flash_fired is True


# ---------------------------------------------------------------------------
# Convenience: collect all EXIF-derived keywords in one call
# ---------------------------------------------------------------------------

def derive_keywords(exif: ExifMetadata, pixels: PixelAnalysis) -> list[str]:
    """Return all deterministically derivable keywords."""
    keywords: list[str] = []

    focal = classify_focal_length(exif.focal_length_35mm)
    if focal:
        keywords.append(focal)

    season = classify_season(exif.datetime_original)
    if season:
        keywords.append(season)

    if pixels.is_bw:
        keywords.append("Schwarzweiss")

    if should_add_langzeitbelichtung(exif):
        keywords.append("Langzeitbelichtung")

    if should_add_kunstlicht(exif):
        keywords.append("Kunstlicht")

    return keywords


def get_technik_vetos(exif: ExifMetadata, pixels: PixelAnalysis) -> set[str]:
    """Return Technik whitelist values that EXIF data rules out."""
    vetos: set[str] = set()
    if should_veto_bokeh(exif):
        vetos.add("Bokeh")
    if should_veto_langzeitbelichtung(exif):
        vetos.add("Langzeitbelichtung")
    if should_veto_makro(exif):
        vetos.add("Makro")
    if pixels.is_bw:
        # Already added deterministically — don't ask the model too.
        vetos.add("Schwarzweiss")
    elif not pixels.is_bw and pixels.mean_saturation is not None:
        # Colour image — model shouldn't tag it as B&W.
        vetos.add("Schwarzweiss")
    return vetos
