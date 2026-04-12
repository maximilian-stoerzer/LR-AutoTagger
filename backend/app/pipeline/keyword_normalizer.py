"""Post-processing normalizer: map English keywords to German whitelist values.

Some vision models (llava-llama3, llama3.2-vision) answer in English
despite a German prompt. This module provides a deterministic,
zero-cost dictionary lookup that maps common English photo keywords to
their German equivalents — either to the exact whitelist value (for
controlled categories) or to a standard German term (for free
categories like Objekte/Szene/Umgebung).

Unknown words pass through unchanged (conservative — better an English
keyword than a wrong translation).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Whitelist reverse mappings: English → exact German whitelist value
# ---------------------------------------------------------------------------

_WHITELIST_MAP: dict[str, str] = {
    # Tageszeit
    "dawn": "Morgengrauen",
    "sunrise": "Morgengrauen",
    "morning": "Morgen",
    "forenoon": "Vormittag",
    "noon": "Mittag",
    "midday": "Mittag",
    "afternoon": "Nachmittag",
    "evening": "Abend",
    "sunset": "Abend",
    "dusk": "Daemmerung",
    "twilight": "Daemmerung",
    "night": "Nacht",
    "nighttime": "Nacht",
    # Jahreszeit
    "spring": "Fruehling",
    "summer": "Sommer",
    "autumn": "Herbst",
    "fall": "Herbst",
    "winter": "Winter",
    # Wetter
    "sunny": "Sonnig",
    "clear": "Sonnig",
    "cloudy": "Bewoelkt",
    "overcast": "Bedeckt",
    "rain": "Regen",
    "rainy": "Regen",
    "snow": "Schnee",
    "snowy": "Schnee",
    "fog": "Nebel",
    "foggy": "Nebel",
    "mist": "Nebel",
    "misty": "Nebel",
    "thunderstorm": "Gewitter",
    "storm": "Sturm",
    "wind": "Wind",
    "windy": "Wind",
    "haze": "Dunst",
    "hazy": "Dunst",
    # Stimmung
    "peaceful": "Friedlich",
    "calm": "Friedlich",
    "serene": "Friedlich",
    "dramatic": "Dramatisch",
    "melancholic": "Melancholisch",
    "melancholy": "Melancholisch",
    "cheerful": "Froehlich",
    "joyful": "Froehlich",
    "happy": "Froehlich",
    "mystical": "Mystisch",
    "mysterious": "Mystisch",
    "romantic": "Romantisch",
    "threatening": "Bedrohlich",
    "ominous": "Bedrohlich",
    "lonely": "Einsam",
    "solitary": "Einsam",
    "lively": "Lebhaft",
    "vibrant": "Lebhaft",
    "dreamy": "Vertraeumt",
    "nostalgic": "Nostalgisch",
    "majestic": "Majestaetisch",
    "grand": "Majestaetisch",
    # Lichtsituation
    "backlight": "Gegenlicht",
    "backlit": "Gegenlicht",
    "sidelight": "Seitenlicht",
    "side light": "Seitenlicht",
    "side-light": "Seitenlicht",
    "frontlight": "Frontlicht",
    "front light": "Frontlicht",
    "rim light": "Kantenlicht",
    "overhead light": "Oberlicht",
    "natural light": "Natuerliches Licht",
    "available light": "Natuerliches Licht",
    "artificial light": "Kunstlicht",
    "mixed light": "Mischlicht",
    "hard light": "Hartes Licht",
    "harsh light": "Hartes Licht",
    "soft light": "Weiches Licht",
    "diffused light": "Diffuses Licht",
    "diffuse light": "Diffuses Licht",
    "high-key": "High-Key",
    "high key": "High-Key",
    "low-key": "Low-Key",
    "low key": "Low-Key",
    "chiaroscuro": "Hell-Dunkel",
    "silhouette": "Silhouette",
    "light rays": "Lichtstrahlen",
    "sun rays": "Lichtstrahlen",
    "god rays": "Lichtstrahlen",
    # Perspektive
    "eye level": "Normalperspektive",
    "normal perspective": "Normalperspektive",
    "high angle": "Aufsicht",
    "bird's eye": "Vogelperspektive",
    "birds eye": "Vogelperspektive",
    "bird's-eye": "Vogelperspektive",
    "aerial view": "Vogelperspektive",
    "top-down": "Draufsicht",
    "top down": "Draufsicht",
    "overhead": "Draufsicht",
    "flat lay": "Draufsicht",
    "low angle": "Untersicht",
    "worm's eye": "Froschperspektive",
    "worms eye": "Froschperspektive",
    "dutch angle": "Schraegsicht",
    "tilted": "Schraegsicht",
    # Technik
    "macro": "Makro",
    "close-up": "Makro",
    "closeup": "Makro",
    "bokeh": "Bokeh",
    "long exposure": "Langzeitbelichtung",
    "motion blur": "Bewegungsunschaerfe",
    "black and white": "Schwarzweiss",
    "black & white": "Schwarzweiss",
    "b&w": "Schwarzweiss",
    "b/w": "Schwarzweiss",
    "monochrome": "Schwarzweiss",
    "infrared": "Infrarot",
}

# ---------------------------------------------------------------------------
# Common photography objects: English → German
# ---------------------------------------------------------------------------

_OBJECT_MAP: dict[str, str] = {
    # Nature
    "tree": "Baum", "trees": "Baeume",
    "flower": "Blume", "flowers": "Blumen",
    "leaf": "Blatt", "leaves": "Blaetter",
    "forest": "Wald", "woods": "Wald",
    "mountain": "Berg", "mountains": "Berge",
    "hill": "Huegel", "hills": "Huegel",
    "river": "Fluss", "stream": "Bach",
    "lake": "See", "pond": "Teich",
    "sea": "Meer", "ocean": "Ozean",
    "beach": "Strand", "coast": "Kueste",
    "sky": "Himmel", "cloud": "Wolke", "clouds": "Wolken",
    "sun": "Sonne", "moon": "Mond", "star": "Stern", "stars": "Sterne",
    "water": "Wasser", "ice": "Eis",
    "rock": "Fels", "rocks": "Felsen", "stone": "Stein",
    "grass": "Gras", "meadow": "Wiese", "field": "Feld",
    "garden": "Garten", "park": "Park",
    # Animals
    "bird": "Vogel", "birds": "Voegel",
    "dog": "Hund", "cat": "Katze",
    "horse": "Pferd", "cow": "Kuh",
    "bee": "Biene", "butterfly": "Schmetterling",
    "fish": "Fisch", "insect": "Insekt",
    "deer": "Hirsch", "fox": "Fuchs",
    # People
    "person": "Person", "people": "Menschen",
    "man": "Mann", "woman": "Frau",
    "child": "Kind", "children": "Kinder",
    "face": "Gesicht", "portrait": "Portrait",
    # Built environment
    "building": "Gebaeude", "buildings": "Gebaeude",
    "house": "Haus", "church": "Kirche", "castle": "Burg",
    "bridge": "Bruecke", "tower": "Turm",
    "city": "Stadt", "town": "Stadt", "village": "Dorf",
    "street": "Strasse", "road": "Strasse", "path": "Weg",
    "car": "Auto", "boat": "Boot", "ship": "Schiff",
    "window": "Fenster", "door": "Tuer", "wall": "Mauer",
    "roof": "Dach", "stairs": "Treppe", "fence": "Zaun",
    # Scenes / concepts
    "landscape": "Landschaft", "cityscape": "Stadtlandschaft",
    "skyline": "Skyline", "panorama": "Panorama",
    "nature": "Natur", "urban": "Staedtisch",
    "indoor": "Innenraum", "indoors": "Innenraum",
    "outdoor": "Draussen", "outdoors": "Draussen",
    "food": "Essen", "light": "Licht", "shadow": "Schatten",
    "reflection": "Spiegelung", "sunrise": "Sonnenaufgang",
    "sunset": "Sonnenuntergang",
    "rain": "Regen", "snow": "Schnee",
    "daytime": "Tag", "nighttime": "Nacht",
    "green": "Gruen", "blue": "Blau", "red": "Rot",
}

# Build a single combined lookup (whitelist takes precedence).
_FULL_MAP: dict[str, str] = {**_OBJECT_MAP, **_WHITELIST_MAP}


def normalize(keywords: list[str]) -> list[str]:
    """Normalize a keyword list: map English terms to German equivalents.

    Case-insensitive lookup. Unknown words pass through unchanged.
    Lookup is O(1) per keyword — no network, no ML.
    """
    result: list[str] = []
    for kw in keywords:
        mapped = _FULL_MAP.get(kw.lower().strip())
        if mapped:
            result.append(mapped)
        else:
            result.append(kw)
    return result
