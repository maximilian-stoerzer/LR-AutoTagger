import asyncio
import logging

from app.config import settings
from app.db.repository import Repository
from app.pipeline import (
    exif_classifier,
    exif_extractor,
    keyword_normalizer,
    pixel_analyzer,
    prompt_builder,
    sun_calculator,
)
from app.monitoring import keywords_per_image, track_stage
from app.pipeline.geocoder import Geocoder
from app.pipeline.image_processor import resize_for_analysis
from app.pipeline.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Directional sunlight keywords — vetoed by diffuse weather or night.
_DIRECTIONAL_LIGHT = {"Hartes Licht", "Gegenlicht", "Seitenlicht", "Frontlicht", "Lichtstrahlen"}

# Mutually exclusive keyword pairs (first-in-list wins).
_EXCLUSIVE_PAIRS: list[tuple[str, str]] = [
    # Lichtsituation
    ("Hartes Licht", "Weiches Licht"),
    ("Hartes Licht", "Diffuses Licht"),
    ("High-Key", "Low-Key"),
    ("Silhouette", "Frontlicht"),
    ("Silhouette", "High-Key"),
    # Wetter
    ("Sonnig", "Bedeckt"),
    ("Sonnig", "Nebel"),
]


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
        ollama_model: str | None = None,
        sun_calc_location: str | None = None,
    ) -> dict:
        """Full pipeline: EXIF → Pixel → Prompt-Build → (Geo ∥ Vision) →
        Normalize → EXIF-Veto → Combine.

        Categories that EXIF/pixels already answer are NOT sent to the
        vision model. The prompt is shorter, the model has less room to
        hallucinate, and deterministic values are always correct.
        """

        # ── Phase 1: deterministic analysis (before Ollama) ──────────

        with track_stage("preprocess"):
            exif = exif_extractor.extract(image_data)
            pixels = pixel_analyzer.analyze(image_data)

        # GPS fallback: parameter → EXIF.
        if gps_lat is None or gps_lon is None:
            gps_lat = exif.gps_lat
            gps_lon = exif.gps_lon

        # EXIF-derived keywords (deterministic, always correct).
        derived_keywords = exif_classifier.derive_keywords(exif, pixels)

        # Tageszeit from sun elevation (deterministic).
        loc = sun_calc_location or settings.sun_calc_default_location
        time_of_day = exif_classifier.classify_time_of_day(
            exif.datetime_original,
            gps_lat,
            gps_lon,
            default_location=loc,
        )
        if time_of_day:
            derived_keywords.append(time_of_day)

        # Tageslichtphase (Goldene/Blaue Stunde) from sun calculator.
        sun_kw = sun_calculator.classify(
            exif.datetime_original,
            gps_lat,
            gps_lon,
            default_location=loc,
        )
        if sun_kw:
            derived_keywords.append(sun_kw)

        # Build the dynamic prompt — shorter when EXIF provides answers.
        prompt = prompt_builder.build(exif, pixels)

        # ── Phase 2: async I/O (Ollama + Geocoding in parallel) ──────

        resized = resize_for_analysis(image_data)

        geo_task = self.geocoder.reverse(gps_lat, gps_lon) if gps_lat is not None and gps_lon is not None else None
        vision_task = self.ollama.analyze_image(resized, model=ollama_model, prompt=prompt)

        if geo_task is not None:
            geo_result, vision_keywords = await asyncio.gather(geo_task, vision_task, return_exceptions=True)
            if isinstance(geo_result, BaseException):
                logger.warning("Reverse geocoding failed: %s", geo_result)
                geo_result = None
            if isinstance(vision_keywords, BaseException):
                raise vision_keywords
        else:
            geo_result = None
            vision_keywords = await vision_task

        # ── Phase 3: post-processing ─────────────────────────────────

        # EN→DE normalization (fixes models that answer in English).
        vision_keywords = keyword_normalizer.normalize(vision_keywords)

        # EXIF-based vetos: remove vision keywords that EXIF data rules out.
        technik_vetos = exif_classifier.get_technik_vetos(exif, pixels)
        if technik_vetos:
            vision_keywords = [kw for kw in vision_keywords if kw not in technik_vetos]

        # Cross-category and intra-category vetos: remove keywords that
        # contradict each other (weather vs light, mutually exclusive pairs).
        consistency_vetos = self._get_consistency_vetos(vision_keywords, derived_keywords)
        if consistency_vetos:
            vision_keywords = [kw for kw in vision_keywords if kw not in consistency_vetos]

        geo_keywords: list[str] = []
        location_name = None
        if geo_result:
            geo_keywords = geo_result.get("geo_keywords", [])
            location_name = geo_result.get("location_name")

        # ── Phase 4: combine ─────────────────────────────────────────

        keywords = self._combine_keywords(vision_keywords, geo_keywords, derived_keywords)

        if image_id:
            await self.repo.save_image_keywords(
                image_id=image_id,
                keywords=keywords,
                geo_keywords=geo_keywords or None,
                vision_keywords=vision_keywords,
                gps_lat=gps_lat,
                gps_lon=gps_lon,
                location_name=location_name,
                model_used=ollama_model or settings.ollama_model,
            )

        keywords_per_image.observe(len(keywords))

        return {
            "image_id": image_id,
            "keywords": keywords,
            "geo_keywords": geo_keywords,
            "vision_keywords": vision_keywords,
            "derived_keywords": derived_keywords,
            "location_name": location_name,
        }

    @staticmethod
    def _get_consistency_vetos(vision_kw: list[str], derived_kw: list[str]) -> set[str]:
        """Return keywords that contradict other recognised keywords.

        Covers three kinds of contradiction:
        1. Cross-category: weather/time rules out certain light values.
        2. Intra-category: mutually exclusive pairs (first-in-list wins).
        """
        all_kw = {kw.lower() for kw in vision_kw} | {kw.lower() for kw in derived_kw}
        position = {kw.lower(): i for i, kw in enumerate(vision_kw)}
        vetos: set[str] = set()

        # Diffuse weather / night rule out directional sunlight.
        diffuse_weather = {"bedeckt", "nebel", "regen", "schnee"}
        if all_kw & diffuse_weather:
            vetos.update(_DIRECTIONAL_LIGHT)
        if "nacht" in all_kw and "kunstlicht" not in all_kw:
            vetos.update(_DIRECTIONAL_LIGHT)

        # Mutually exclusive pairs — keep whichever LLaVA listed first.
        for a, b in _EXCLUSIVE_PAIRS:
            if a.lower() in all_kw and b.lower() in all_kw:
                idx_a = position.get(a.lower(), len(vision_kw))
                idx_b = position.get(b.lower(), len(vision_kw))
                vetos.add(b if idx_a <= idx_b else a)

        return vetos

    def _combine_keywords(
        self,
        vision: list[str],
        geo: list[str],
        derived: list[str],
    ) -> list[str]:
        """Merge vision, geo and derived keywords, deduplicate case-insensitively.

        Order: geo (high confidence, location) → derived (EXIF + sun, exact) →
        vision (bulk of the content).
        """
        seen: set[str] = set()
        result: list[str] = []

        for source in (geo, derived, vision):
            for kw in source:
                key = kw.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    result.append(kw.strip())

        return result[: settings.max_keywords]
