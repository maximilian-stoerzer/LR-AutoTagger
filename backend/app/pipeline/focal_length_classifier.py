"""Classify focal length (35mm equivalent) into a named range.

Taxonomy follows the common photography convention:
  <  24 mm  → Superweitwinkel (fisheye and ultrawide)
  24-35 mm  → Weitwinkel      (classic landscape wide)
  35-70 mm  → Normalbrennweite (~50 mm reference, natural field of view)
  70-200 mm → Teleobjektiv    (portrait + mid-tele)
  > 200 mm  → Supertele       (wildlife, sports)
"""
from __future__ import annotations


def classify(focal_length_35mm: float | None) -> str | None:
    """Return a German focal-length category, or None if unknown."""
    if focal_length_35mm is None or focal_length_35mm <= 0:
        return None
    f = focal_length_35mm
    if f < 24:
        return "Superweitwinkel"
    if f < 35:
        return "Weitwinkel"
    if f < 70:
        return "Normalbrennweite"
    if f <= 200:
        return "Teleobjektiv"
    return "Supertele"
