from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings


async def api_key_middleware(request: Request, call_next):
    if request.url.path == "/api/v1/health":
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if api_key != settings.api_key:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)
