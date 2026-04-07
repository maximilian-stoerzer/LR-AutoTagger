import logging

from app.config import settings
from app.db.repository import Repository
from app.pipeline.geocoder import Geocoder
from app.pipeline.image_processor import resize_for_analysis
from app.pipeline.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class KeywordPipeline:
    def __init__(self, repo: Repository):
        self.repo = repo
        self.ollama = OllamaClient()
        self.geocoder = Geocoder()

    async def analyze_single(
        self,
        image_data: bytes,
        gps_lat: float | None = None,
        gps_lon: float | None = None,
        image_id: str | None = None,
    ) -> dict:
        """Full pipeline for a single image: resize → geocode → vision → combine."""

        # 1. Resize
        resized = resize_for_analysis(image_data)

        # 2. Reverse Geocoding (if GPS available)
        geo_result = None
        geo_keywords: list[str] = []
        location_name = None

        if gps_lat is not None and gps_lon is not None:
            geo_result = await self.geocoder.reverse(gps_lat, gps_lon)
            if geo_result:
                geo_keywords = geo_result.get("geo_keywords", [])
                location_name = geo_result.get("location_name")

        # 3. Vision Analysis
        vision_keywords = await self.ollama.analyze_image(resized)

        # 4. Combine & deduplicate
        keywords = self._combine_keywords(vision_keywords, geo_keywords)

        # 5. Persist if image_id provided
        if image_id:
            await self.repo.save_image_keywords(
                image_id=image_id,
                keywords=keywords,
                geo_keywords=geo_keywords or None,
                vision_keywords=vision_keywords,
                gps_lat=gps_lat,
                gps_lon=gps_lon,
                location_name=location_name,
                model_used=settings.ollama_model,
            )

        return {
            "image_id": image_id,
            "keywords": keywords,
            "geo_keywords": geo_keywords,
            "vision_keywords": vision_keywords,
            "location_name": location_name,
        }

    def _combine_keywords(self, vision: list[str], geo: list[str]) -> list[str]:
        """Merge vision and geo keywords, deduplicate case-insensitively."""
        seen: set[str] = set()
        result: list[str] = []

        # Geo keywords first (high confidence)
        for kw in geo:
            key = kw.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(kw.strip())

        # Then vision keywords
        for kw in vision:
            key = kw.lower().strip()
            if key and key not in seen:
                seen.add(key)
                result.append(kw.strip())

        return result[: settings.max_keywords]
