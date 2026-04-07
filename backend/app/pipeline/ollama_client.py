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
    "Kategorien: Objekte, Szene, Umgebung, Tageszeit, Jahreszeit, Wetter.\n"
    "Format: JSON-Array mit maximal {max_keywords} Keywords.\n"
    "Nur sachliche/technische Begriffe, keine Stimmungsbeschreibungen.\n"
    "Antworte NUR mit dem JSON-Array, kein weiterer Text."
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

    async def analyze_image(self, image_data: bytes) -> list[str]:
        b64_image = base64.b64encode(image_data).decode("utf-8")
        prompt = VISION_PROMPT.format(max_keywords=settings.max_keywords)

        payload = {
            "model": self.model,
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
        # Try to extract JSON array from response
        # LLaVA sometimes wraps in markdown code blocks
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            keywords = json.loads(cleaned)
            if isinstance(keywords, list):
                return [str(k).strip() for k in keywords if str(k).strip()][: settings.max_keywords]
        except json.JSONDecodeError:
            pass

        # Fallback: try to find array in text
        match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if match:
            try:
                keywords = json.loads(match.group())
                if isinstance(keywords, list):
                    return [str(k).strip() for k in keywords if str(k).strip()][: settings.max_keywords]
            except json.JSONDecodeError:
                pass

        # Last resort: split comma-separated text
        logger.warning("Could not parse JSON from Ollama response, falling back to text split")
        parts = [p.strip().strip('"').strip("'") for p in cleaned.split(",")]
        return [p for p in parts if p and len(p) < 50][: settings.max_keywords]
