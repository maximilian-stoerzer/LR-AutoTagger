import asyncio
import base64
import json
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VISION_PROMPT = (
    "Analysiere dieses Foto und gib deutsche Schlagworte zurueck.\n"
    "\n"
    "Bevor du antwortest, ueberlege kurz:\n"
    "- Woher kommt das Hauptlicht? (von vorne, von der Seite, von hinten, von oben?)\n"
    "- Aus welchem Winkel wurde fotografiert? (von unten, von oben, Augenhoehe, Makro?)\n"
    "- Ist das Bild schwarzweiss? Gibt es Bokeh, Langzeitbelichtung oder andere Techniken?\n"
    "- Welche Stimmung vermittelt das Bild? Ist es friedlich, dramatisch, melancholisch?\n"
    "\n"
    "Kategorien:\n"
    "- Objekte: frei waehlbar, MAXIMAL 5\n"
    "- Szene: frei waehlbar, max 2\n"
    "- Umgebung: frei waehlbar, max 2\n"
    "- Tageszeit: Morgengrauen, Morgen, Vormittag, Mittag, Nachmittag, Abend, Daemmerung, Nacht\n"
    "- Jahreszeit: Fruehling, Sommer, Herbst, Winter\n"
    "- Wetter: Sonnig, Bewoelkt, Bedeckt, Regen, Schnee, Nebel, Gewitter, Wind, Sturm, Dunst\n"
    "- Stimmung (1-2 Werte): Dramatisch, Melancholisch, Mystisch, Bedrohlich, Einsam, "
    "Vertraeumt, Nostalgisch, Majestaetisch, Romantisch, Lebhaft, Froehlich, Friedlich\n"
    "- Lichtsituation (0-3 Werte, NUR wenn im Bild erkennbar — leer lassen wenn unauffaellig): "
    "Gegenlicht, Seitenlicht, Hartes Licht, Weiches Licht, Diffuses Licht, "
    "Hell-Dunkel, Silhouette, Lichtstrahlen, High-Key, Low-Key, "
    "Kantenlicht, Oberlicht, Mischlicht, Kunstlicht, Natuerliches Licht, Frontlicht\n"
    "- Perspektive (genau 1 Wert — Normalperspektive NUR wenn Kamera klar auf Augenhoehe "
    "und horizontal steht, sonst den spezifischen Winkel waehlen): "
    "Froschperspektive, Vogelperspektive, Draufsicht, Aufsicht, Untersicht, "
    "Schraegsicht, Normalperspektive\n"
    "- Technik (0-2 Werte, NUR bei offensichtlichem Merkmal — leer lassen wenn nichts): "
    "Schwarzweiss, Makro, Bokeh, Langzeitbelichtung, Bewegungsunschaerfe, Infrarot\n"
    "\n"
    "Regeln:\n"
    "- Fuer alle Whitelist-Kategorien NUR Werte aus der jeweiligen Liste verwenden.\n"
    "- Format: JSON-Array mit maximal {max_keywords} Keywords.\n"
    "- Antworte NUR mit dem JSON-Array, kein weiterer Text."
)

# Semaphore to limit concurrent Ollama requests (shared service protection)
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.ollama_max_concurrent)
    return _semaphore


class OllamaClient:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5)
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """Return model names available on the Ollama server, alphabetically."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("Failed to fetch Ollama model list: %s", e)
            return []
        names = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return sorted(names)

    async def analyze_image(self, image_data: bytes, model: str | None = None, prompt: str | None = None) -> list[str]:
        b64_image = base64.b64encode(image_data).decode("utf-8")
        prompt = prompt or VISION_PROMPT.format(max_keywords=settings.max_keywords)

        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "images": [b64_image],
            "stream": False,
            "options": {"temperature": 0.1},
        }

        sem = _get_semaphore()
        async with sem:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()

        data = resp.json()
        raw_response = data.get("response", "")
        return self._parse_keywords(raw_response)

    def _parse_keywords(self, raw: str) -> list[str]:
        """Parse the raw Ollama response into a flat list of keywords.

        The prompt asks for a plain JSON array but LLaVA variants
        (especially llava:7b) reliably disobey and return a JSON object
        keyed by category name whose values are lists. Both shapes are
        accepted and flattened; non-JSON prose falls back to comma-split.
        """
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        parsed = self._try_json(cleaned)
        if parsed is not None:
            return self._flatten_json_keywords(parsed)[: settings.max_keywords]

        # Fallback: locate an embedded JSON object or array in prose.
        # Greedy matches first so we don't stop at the first inner "]" when
        # the model wraps a dict around several category arrays.
        for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
            match = re.search(pattern, cleaned)
            if match:
                parsed = self._try_json(match.group())
                if parsed is not None:
                    return self._flatten_json_keywords(parsed)[: settings.max_keywords]

        logger.warning("Could not parse JSON from Ollama response, falling back to text split")
        parts = [p.strip().strip('"').strip("'") for p in cleaned.split(",")]
        return [p for p in parts if p and len(p) < 50][: settings.max_keywords]

    @staticmethod
    def _try_json(s: str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _flatten_json_keywords(value) -> list[str]:
        """Recursively flatten any mix of list/dict/scalar into an ordered
        list of non-empty string keywords. Preserves first-seen order and
        leaves deduplication to the downstream combinator."""
        result: list[str] = []

        def add(item) -> None:
            if item is None:
                return
            if isinstance(item, str):
                s = item.strip()
                if s:
                    result.append(s)
                return
            if isinstance(item, dict):
                for v in item.values():
                    add(v)
                return
            if isinstance(item, (list, tuple)):
                for x in item:
                    add(x)
                return
            # numbers and bools get stringified — preserves the original
            # parser's behaviour on ["Foo", 42] style mixed arrays.
            s = str(item).strip()
            if s:
                result.append(s)

        add(value)
        return result
