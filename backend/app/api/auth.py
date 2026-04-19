from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings


async def api_key_middleware(request: Request, call_next):
    # /api/v1/health and /metrics are unauthenticated — health is probed by
    # the Lightroom plugin before it has the key, and /metrics is scraped by
    # Prometheus (which lives behind the LAN firewall, not exposed publicly).
    if request.url.path in ("/api/v1/health", "/metrics"):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if api_key != settings.api_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)
