import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.auth import api_key_middleware
from app.api.routes import router
from app.db.repository import Repository
from app.monitoring import refresh_batch_gauges

logger = logging.getLogger(__name__)

# Refresh batch/chunk state gauges at the Prometheus scrape cadence.
GAUGE_REFRESH_INTERVAL = 15.0


async def _periodic_gauge_refresh(repo: Repository) -> None:
    while True:
        try:
            await refresh_batch_gauges(repo)
        except Exception:
            logger.exception("batch gauge refresh failed")
        await asyncio.sleep(GAUGE_REFRESH_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = Repository()
    await repo.connect()
    await repo.run_migrations()
    app.state.repo = repo
    await refresh_batch_gauges(repo)  # populate on startup so first scrape is accurate
    gauge_task = asyncio.create_task(_periodic_gauge_refresh(repo))
    try:
        yield
    finally:
        gauge_task.cancel()
        try:
            await gauge_task
        except asyncio.CancelledError:
            pass
        await repo.close()


app = FastAPI(title="LR-AutoTag", version="0.1.0", lifespan=lifespan)
app.middleware("http")(api_key_middleware)
app.include_router(router, prefix="/api/v1")

# Prometheus instrumentation: request counters/histograms per endpoint.
# /metrics is added outside the API router so it bypasses the /api/v1 prefix
# and the X-API-Key check (see api_key_middleware).
Instrumentator(
    should_group_status_codes=True,
    excluded_handlers=["/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
