import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Rate limiting: max 1 request per second for public Nominatim
_last_request_time: float = 0.0
_lock = asyncio.Lock()


class Geocoder:
    def __init__(self):
        self.base_url = settings.nominatim_url
        self.user_agent = settings.nominatim_user_agent

    async def reverse(self, lat: float, lon: float) -> dict | None:
        """Reverse geocode GPS coordinates to location info.

        Returns dict with keys: location_name, city, state, country, geo_keywords
        or None if geocoding fails.
        """
        await self._throttle()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/reverse",
                    params={
                        "lat": lat,
                        "lon": lon,
                        "format": "jsonv2",
                        "accept-language": "de",
                        "zoom": 14,
                    },
                    headers={"User-Agent": self.user_agent},
                    timeout=10,
                )
                resp.raise_for_status()
        except Exception:
            logger.exception("Reverse geocoding failed for lat=%s, lon=%s", lat, lon)
            return None

        data = resp.json()
        if "error" in data:
            logger.warning("Nominatim error: %s", data["error"])
            return None

        address = data.get("address", {})

        city = address.get("city") or address.get("town") or address.get("village") or address.get("municipality")
        state = address.get("state")
        country = address.get("country")
        suburb = address.get("suburb")
        county = address.get("county")

        # Build location name
        parts = [p for p in [city, state, country] if p]
        location_name = ", ".join(parts) if parts else data.get("display_name", "")

        # Build geo keywords
        geo_keywords = []
        for value in [suburb, city, county, state, country]:
            if value and value not in geo_keywords:
                geo_keywords.append(value)

        return {
            "location_name": location_name,
            "city": city,
            "state": state,
            "country": country,
            "geo_keywords": geo_keywords,
        }

    async def _throttle(self):
        global _last_request_time
        async with _lock:
            now = time.monotonic()
            elapsed = now - _last_request_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            _last_request_time = time.monotonic()
