"""Unit tests for app.pipeline.keyword_normalizer."""

import pytest

from app.pipeline.keyword_normalizer import normalize


def test_english_whitelist_mapped_to_german():
    result = normalize(["sunset", "fog", "dramatic", "backlight", "macro"])
    assert result == ["Abend", "Nebel", "Dramatisch", "Gegenlicht", "Makro"]


def test_german_keywords_pass_through():
    result = normalize(["Bruecke", "Fluss", "Herbst"])
    assert result == ["Bruecke", "Fluss", "Herbst"]


def test_case_insensitive():
    result = normalize(["SUNSET", "Fog", "bACKLIGHT"])
    assert result == ["Abend", "Nebel", "Gegenlicht"]


def test_unknown_english_passes_through():
    result = normalize(["something_unusual", "xyzzy"])
    assert result == ["something_unusual", "xyzzy"]


def test_mixed_english_german():
    result = normalize(["Haus", "bee", "Wald", "silhouette", "Sommer"])
    assert result == ["Haus", "Biene", "Wald", "Silhouette", "Sommer"]


def test_common_objects():
    result = normalize(["tree", "mountain", "bridge", "church"])
    assert result == ["Baum", "Berg", "Bruecke", "Kirche"]


def test_whitelist_takes_precedence_over_object():
    # "night" appears in both Tageszeit whitelist and objects — whitelist wins.
    result = normalize(["night"])
    assert result == ["Nacht"]


def test_empty_list():
    assert normalize([]) == []


def test_whitespace_handling():
    result = normalize(["  sunset  ", " fog"])
    assert result == ["Abend", "Nebel"]


@pytest.mark.parametrize(
    "english,german",
    [
        ("black and white", "Schwarzweiss"),
        ("b&w", "Schwarzweiss"),
        ("bird's eye", "Vogelperspektive"),
        ("worm's eye", "Froschperspektive"),
        ("long exposure", "Langzeitbelichtung"),
        ("motion blur", "Bewegungsunschaerfe"),
        ("natural light", "Natuerliches Licht"),
        ("hard light", "Hartes Licht"),
        ("top-down", "Draufsicht"),
        ("high-key", "High-Key"),
    ],
)
def test_multi_word_mappings(english, german):
    assert normalize([english]) == [german]


def test_real_llava_llama3_output():
    """Actual keywords from llava-llama3 benchmark run on 03_night_city.jpg."""
    raw = ["Skyline", "Buildings", "Cityscape", "Nighttime", "Urban", "Dusk"]
    result = normalize(raw)
    assert "Skyline" in result  # pass-through (accepted German loan word)
    assert "Nacht" in result    # Nighttime → Nacht
    assert "Daemmerung" in result  # Dusk → Daemmerung
    assert "Staedtisch" in result  # Urban → Staedtisch


def test_real_llama32_vision_output():
    """Actual keywords from llama3.2-vision benchmark on 02_macro.jpg."""
    raw = ["Bee", "Flower", "Nature", "Daytime", "Green"]
    result = normalize(raw)
    assert "Biene" in result
    assert "Blume" in result
    assert "Natur" in result
    assert "Tag" in result
    assert "Gruen" in result
