from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import api_key_middleware
from app.api.routes import router
from app.db.repository import Repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = Repository()
    await repo.connect()
    await repo.run_migrations()
    app.state.repo = repo
    yield
    await repo.close()


app = FastAPI(title="LR-AutoTag", version="0.1.0", lifespan=lifespan)
app.middleware("http")(api_key_middleware)
app.include_router(router, prefix="/api/v1")
