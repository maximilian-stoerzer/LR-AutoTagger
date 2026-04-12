"""Build the Ollama vision prompt dynamically based on EXIF and pixel analysis.

Categories that are already answered by EXIF or pixel data are omitted
from the prompt entirely — the model has fewer things to juggle and
less room to hallucinate. Technik whitelist values that EXIF rules out
(e.g. Bokeh at f/13) are removed so the model can't pick them.
"""
from __future__ import annotations

from app.config import settings
from app.pipeline.exif_classifier import get_technik_vetos
from app.pipeline.exif_extractor import ExifMetadata
from app.pipeline.pixel_analyzer import PixelAnalysis

# ---------------------------------------------------------------------------
# Whitelists (canonical, reused in normalizer/validator)
# ---------------------------------------------------------------------------

TAGESZEIT_VALUES = [
    "Morgengrauen", "Morgen", "Vormittag", "Mittag",
    "Nachmittag", "Abend", "Daemmerung", "Nacht",
]
JAHRESZEIT_VALUES = ["Fruehling", "Sommer", "Herbst", "Winter"]
WETTER_VALUES = [
    "Sonnig", "Bewoelkt", "Bedeckt", "Regen", "Schnee",
    "Nebel", "Gewitter", "Wind", "Sturm", "Dunst",
]
STIMMUNG_VALUES = [
    "Dramatisch", "Melancholisch", "Mystisch", "Bedrohlich", "Einsam",
    "Vertraeumt", "Nostalgisch", "Majestaetisch", "Romantisch",
    "Lebhaft", "Froehlich", "Friedlich",
]
LICHTSITUATION_VALUES = [
    "Gegenlicht", "Seitenlicht", "Hartes Licht", "Weiches Licht",
    "Diffuses Licht", "Hell-Dunkel", "Silhouette", "Lichtstrahlen",
    "High-Key", "Low-Key", "Kantenlicht", "Oberlicht", "Mischlicht",
    "Kunstlicht", "Natuerliches Licht", "Frontlicht",
]
PERSPEKTIVE_VALUES = [
    "Froschperspektive", "Vogelperspektive", "Draufsicht", "Aufsicht",
    "Untersicht", "Schraegsicht", "Normalperspektive",
]
TECHNIK_VALUES = [
    "Schwarzweiss", "Makro", "Bokeh",
    "Langzeitbelichtung", "Bewegungsunschaerfe", "Infrarot",
]


def build(exif: ExifMetadata, pixels: PixelAnalysis) -> str:
    """Return the complete prompt string, tailored to what EXIF/pixels
    already tell us about this particular image."""

    has_datetime = exif.datetime_original is not None
    technik_vetos = get_technik_vetos(exif, pixels)
    available_technik = [v for v in TECHNIK_VALUES if v not in technik_vetos]

    lines = [
        "Analysiere dieses Foto und gib deutsche Schlagworte zurueck.",
        "",
        "Bevor du antwortest, ueberlege kurz:",
        "- Woher kommt das Hauptlicht? (von vorne, von der Seite, von hinten, von oben?)",
        "- Aus welchem Winkel wurde fotografiert? (von unten, von oben, Augenhoehe?)",
    ]
    if available_technik:
        lines.append(
            "- Gibt es sichtbare fotografische Techniken? ("
            + ", ".join(available_technik) + "?)"
        )
    lines.append(
        "- Welche Stimmung vermittelt das Bild? Ist es friedlich, dramatisch, melancholisch?"
    )
    lines.append("")
    lines.append("Kategorien:")

    # --- Always from the model ---
    lines.append("- Objekte: frei waehlbar, MAXIMAL 5")
    lines.append("- Szene: frei waehlbar, max 2")
    lines.append("- Umgebung: frei waehlbar, max 2")

    # --- Conditional: only if EXIF can't answer ---
    if not has_datetime:
        lines.append(
            "- Tageszeit: waehle den wahrscheinlichsten Wert aus: "
            + ", ".join(TAGESZEIT_VALUES)
        )
        lines.append(
            "- Jahreszeit: waehle den wahrscheinlichsten Wert aus: "
            + ", ".join(JAHRESZEIT_VALUES)
        )

    # --- Always from the model (can't derive from EXIF) ---
    lines.append(
        "- Wetter: waehle den EINEN wahrscheinlichsten Wert aus: "
        + ", ".join(WETTER_VALUES)
        + ". Nur einen zweiten wenn eindeutig erkennbar."
    )
    lines.append(
        "- Stimmung (1-2 Werte, den dominantesten zuerst): "
        + ", ".join(STIMMUNG_VALUES)
    )
    lines.append(
        "- Lichtsituation (0-3 Werte, NUR wenn im Bild OFFENSICHTLICH erkennbar "
        "— im Zweifel LEER lassen): "
        + ", ".join(LICHTSITUATION_VALUES)
    )
    lines.append(
        "- Perspektive (genau 1 Wert — Normalperspektive NUR wenn Kamera klar "
        "auf Augenhoehe und horizontal steht, sonst den spezifischen Winkel): "
        + ", ".join(PERSPEKTIVE_VALUES)
    )

    # --- Technik: only values that EXIF hasn't ruled out ---
    if available_technik:
        lines.append(
            "- Technik (0-2 Werte, NUR bei offensichtlichem Merkmal — leer lassen wenn nichts): "
            + ", ".join(available_technik)
        )

    lines.append("")
    lines.append("Regeln:")
    lines.append("- Fuer alle Whitelist-Kategorien NUR Werte aus der jeweiligen Liste verwenden.")
    lines.append(f"- Format: JSON-Array mit maximal {settings.max_keywords} Keywords.")
    lines.append("- Antworte NUR mit dem JSON-Array, kein weiterer Text.")

    return "\n".join(lines)
