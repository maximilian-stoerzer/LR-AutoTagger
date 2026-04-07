"""Integration tests for Batch flow with real DB — I-BAT-01 to I-BAT-05."""

import pytest

from app.services.job_manager import JobManager

pytestmark = pytest.mark.integration


def _make_images(n: int) -> list[dict]:
    return [{"image_id": f"batch_img_{i:04d}", "gps_lat": 49.4, "gps_lon": 8.7} for i in range(n)]


# I-BAT-01
@pytest.mark.asyncio
async def test_complete_batch_lifecycle(repo, sample_jpeg):
    manager = JobManager(repo)
    job = await manager.create_job(_make_images(3))
    assert job["status"] == "running"

    # Process all images
    for _ in range(3):
        _job_id, img_id = await manager.get_next_image_id()
        assert img_id is not None
        await manager.mark_image_done(img_id)

    # Should be done now (active job query returns None when status=done)
    status = await manager.get_status()
    assert status["status"] in ("done", "idle")


# I-BAT-02
@pytest.mark.asyncio
async def test_idempotency_skips_tagged(repo):
    # Pre-tag some images
    for i in range(3):
        await repo.save_image_keywords(
            image_id=f"batch_img_{i:04d}",
            keywords=["Existing"],
            geo_keywords=None,
            vision_keywords=["Existing"],
            gps_lat=None,
            gps_lon=None,
            location_name=None,
            model_used="llava:13b",
        )

    manager = JobManager(repo)
    job = await manager.create_job(_make_images(5))

    assert job["skipped"] == 3
    # Only 2 new images to process
    count = 0
    while True:
        _job_id, img_id = await manager.get_next_image_id()
        if not img_id:
            break
        await manager.mark_image_done(img_id)
        count += 1

    assert count == 2


# I-BAT-03
@pytest.mark.asyncio
async def test_pause_and_resume(repo):
    manager = JobManager(repo)
    job = await manager.create_job(_make_images(5))

    # Process one
    _job_id, img_id = await manager.get_next_image_id()
    await manager.mark_image_done(img_id)

    # Pause
    await manager.pause()
    status = await manager.get_status()
    assert status["status"] == "paused"

    # Next should return None while paused
    _, next_img = await manager.get_next_image_id()
    assert next_img is None

    # Resume
    await manager.resume()
    _, next_img = await manager.get_next_image_id()
    assert next_img is not None


# I-BAT-04
@pytest.mark.asyncio
async def test_cancel_stops_processing(repo):
    manager = JobManager(repo)
    job = await manager.create_job(_make_images(5))

    await manager.cancel()

    status = await manager.get_status()
    # After cancel, no active job (cancelled is not in active states)
    # Actually get_active_batch_job checks for running/paused/pending
    assert status["status"] == "idle" or status.get("message")


# I-BAT-05
@pytest.mark.asyncio
async def test_progress_tracking(repo):
    manager = JobManager(repo)
    job = await manager.create_job(_make_images(3))

    # Process one
    _job_id, img_id = await manager.get_next_image_id()
    await manager.mark_image_done(img_id)

    status = await manager.get_status()
    assert status["processed"] >= 1
