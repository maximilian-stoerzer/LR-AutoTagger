from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.pipeline.keyword_pipeline import KeywordPipeline
from app.pipeline.ollama_client import OllamaClient
from app.pipeline.sun_calculator import VALID_LOCATIONS as SUN_CALC_VALID_LOCATIONS
from app.services.job_manager import JobManager

router = APIRouter()


def _repo(request: Request):
    return request.app.state.repo


def _validate_sun_calc_location(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in SUN_CALC_VALID_LOCATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"sun_calc_location must be one of {sorted(SUN_CALC_VALID_LOCATIONS)}",
        )
    return value


# --- Health ---


@router.get("/health")
async def health(request: Request):
    repo = _repo(request)
    db_ok = await repo.ping()

    ollama = OllamaClient()
    ollama_ok = await ollama.health()

    return {
        "status": "ok" if (db_ok and ollama_ok) else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "ollama": "ok" if ollama_ok else "unavailable",
    }


# --- Models ---


@router.get("/models")
async def models():
    """List installed Ollama models (used by the plugin to populate the
    model picker in its settings dialog)."""
    ollama = OllamaClient()
    names = await ollama.list_models()
    return {"models": names, "default": settings.ollama_model}


# --- Single Image Analysis ---


@router.post("/analyze")
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    gps_lat: float | None = Form(None),
    gps_lon: float | None = Form(None),
    image_id: str | None = Form(None),
    ollama_model: str | None = Form(None),
    sun_calc_location: str | None = Form(None),
):
    sun_calc_location = _validate_sun_calc_location(sun_calc_location)
    repo = _repo(request)
    image_data = await file.read()

    pipeline = KeywordPipeline(repo)
    result = await pipeline.analyze_single(
        image_data=image_data,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        image_id=image_id,
        ollama_model=ollama_model,
        sun_calc_location=sun_calc_location,
    )
    return result


# --- Batch Mode ---
#
# Flow:
# 1. Plugin sends POST /batch/start with image metadata (image_id, gps_lat, gps_lon)
# 2. Backend creates job + chunks, returns job_id
# 3. Plugin polls GET /batch/next — backend returns next image_id to process
# 4. Plugin uploads that image via POST /batch/image (multipart: file + image_id + gps)
# 5. Backend processes it through the pipeline, updates progress
# 6. Repeat 3-5 until GET /batch/next returns nothing
# 7. Plugin polls GET /batch/status for overall progress


@router.post("/batch/start")
async def batch_start(request: Request):
    body = await request.json()
    images = body.get("images", [])
    if not images:
        return JSONResponse(status_code=400, content={"detail": "No images provided"})

    repo = _repo(request)
    manager = JobManager(repo)
    job = await manager.create_job(images)
    return job


@router.get("/batch/next")
async def batch_next(request: Request):
    """Returns the next image_id that needs to be uploaded and processed."""
    repo = _repo(request)
    manager = JobManager(repo)
    job_id, next_id = await manager.get_next_image_id()
    if not next_id:
        return {"job_id": job_id, "image_id": None, "message": "No more images to process"}
    return {"job_id": job_id, "image_id": next_id}


@router.post("/batch/image")
async def batch_image(
    request: Request,
    image_id: Annotated[str, Form()],
    file: UploadFile = File(...),
    gps_lat: float | None = Form(None),
    gps_lon: float | None = Form(None),
    ollama_model: str | None = Form(None),
    sun_calc_location: str | None = Form(None),
):
    """Plugin uploads a single image for the active batch job. Backend processes it immediately."""
    sun_calc_location = _validate_sun_calc_location(sun_calc_location)
    repo = _repo(request)
    manager = JobManager(repo)

    # Validate up-front: image_id must belong to the active batch
    job = await repo.get_active_batch_job()
    if job is None:
        return JSONResponse(status_code=409, content={"detail": "No active batch job"})
    meta = await repo.get_batch_image_meta(job["id"], image_id)
    if meta is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"image_id {image_id} is not part of the active batch"},
        )

    image_data = await file.read()

    pipeline = KeywordPipeline(repo)
    result = await pipeline.analyze_single(
        image_data=image_data,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        image_id=image_id,
        ollama_model=ollama_model,
        sun_calc_location=sun_calc_location,
    )

    # Update batch progress (raises if validation regresses, but we already checked above)
    await manager.mark_image_done(image_id)

    return result


@router.post("/batch/skip")
async def batch_skip(request: Request):
    """Plugin marks an image as skipped (e.g. because LR already has
    keywords on it locally). Takes it out of the queue without triggering
    an inference.

    Body: {"image_id": "..."}
    """
    body = await request.json()
    image_id = body.get("image_id")
    if not image_id:
        return JSONResponse(status_code=400, content={"detail": "image_id is required"})

    repo = _repo(request)
    manager = JobManager(repo)
    try:
        await manager.mark_image_skipped(image_id)
    except ValueError:
        return JSONResponse(status_code=409, content={"detail": "No active batch job"})
    except LookupError as e:
        return JSONResponse(status_code=404, content={"detail": str(e)})
    return {"status": "skipped", "image_id": image_id}


@router.get("/batch/status")
async def batch_status(request: Request):
    repo = _repo(request)
    manager = JobManager(repo)
    return await manager.get_status()


@router.post("/batch/pause")
async def batch_pause(request: Request):
    repo = _repo(request)
    manager = JobManager(repo)
    await manager.pause()
    return {"status": "paused"}


@router.post("/batch/resume")
async def batch_resume(request: Request):
    repo = _repo(request)
    manager = JobManager(repo)
    await manager.resume()
    return {"status": "running"}


@router.post("/batch/cancel")
async def batch_cancel(request: Request):
    repo = _repo(request)
    manager = JobManager(repo)
    await manager.cancel()
    return {"status": "cancelled"}


@router.get("/results/{image_id}")
async def get_results(request: Request, image_id: str):
    repo = _repo(request)
    result = await repo.get_image_keywords(image_id)
    if not result:
        return JSONResponse(status_code=404, content={"detail": "Image not found"})
    return result
