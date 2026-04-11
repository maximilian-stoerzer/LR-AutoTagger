"""Unit tests for app.pipeline.focal_length_classifier."""

import pytest

from app.pipeline.focal_length_classifier import classify


@pytest.mark.parametrize(
    "focal_mm,expected",
    [
        (10, "Superweitwinkel"),
        (16, "Superweitwinkel"),
        (23.9, "Superweitwinkel"),
        (24, "Weitwinkel"),
        (28, "Weitwinkel"),
        (34.9, "Weitwinkel"),
        (35, "Normalbrennweite"),
        (50, "Normalbrennweite"),
        (69.9, "Normalbrennweite"),
        (70, "Teleobjektiv"),
        (135, "Teleobjektiv"),
        (200, "Teleobjektiv"),
        (201, "Supertele"),
        (400, "Supertele"),
        (800, "Supertele"),
    ],
)
def test_classify_ranges(focal_mm, expected):
    assert classify(focal_mm) == expected


@pytest.mark.parametrize("bad_value", [None, 0, -50, -1.0])
def test_classify_invalid_returns_none(bad_value):
    assert classify(bad_value) is None
