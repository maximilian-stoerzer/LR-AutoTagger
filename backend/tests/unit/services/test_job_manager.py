"""Unit tests for app.services.job_manager — U-JOB-01 to U-JOB-13."""

from unittest.mock import AsyncMock

import pytest

from app.services.job_manager import JobManager


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.image_already_processed = AsyncMock(return_value=False)
    repo.create_batch_job = AsyncMock(
        return_value={
            "id": "job-123",
            "status": "running",
            "total_images": 0,
            "processed": 0,
            "failed": 0,
            "skipped": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    repo.increment_batch_progress = AsyncMock()
    repo.create_chunks = AsyncMock()
    repo.store_batch_image_meta = AsyncMock()
    repo.get_active_batch_job = AsyncMock(return_value=None)
    repo.get_next_unprocessed_image = AsyncMock(return_value=None)
    repo.update_batch_job_status = AsyncMock()
    repo.mark_chunk_image_done = AsyncMock()
    repo.has_pending_chunks = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def manager(mock_repo):
    return JobManager(mock_repo)


def _images(n: int) -> list[dict]:
    return [{"image_id": f"img_{i:04d}"} for i in range(n)]


# U-JOB-01
@pytest.mark.asyncio
async def test_create_job_100_images(manager, mock_repo):
    result = await manager.create_job(_images(100))
    mock_repo.create_chunks.assert_called_once()
    chunks_arg = mock_repo.create_chunks.call_args[0][1]
    assert len(chunks_arg) == 2  # 50 + 50
    assert len(chunks_arg[0]) == 50
    assert len(chunks_arg[1]) == 50


# U-JOB-02
@pytest.mark.asyncio
async def test_already_tagged_skipped(manager, mock_repo):
    # First 50 already processed
    call_count = 0

    async def _check(image_id):
        nonlocal call_count
        call_count += 1
        return call_count <= 50

    mock_repo.image_already_processed = _check

    result = await manager.create_job(_images(100))

    assert result["skipped"] == 50
    mock_repo.increment_batch_progress.assert_called()


# U-JOB-03
@pytest.mark.asyncio
async def test_all_already_processed(manager, mock_repo):
    mock_repo.image_already_processed = AsyncMock(return_value=True)

    result = await manager.create_job(_images(10))

    assert result["skipped"] == 10
    # No chunks created for 0 new images
    mock_repo.create_chunks.assert_not_called()


# U-JOB-04
@pytest.mark.asyncio
async def test_exactly_50_images_one_chunk(manager, mock_repo):
    await manager.create_job(_images(50))
    chunks_arg = mock_repo.create_chunks.call_args[0][1]
    assert len(chunks_arg) == 1
    assert len(chunks_arg[0]) == 50


# U-JOB-05
@pytest.mark.asyncio
async def test_51_images_two_chunks(manager, mock_repo):
    await manager.create_job(_images(51))
    chunks_arg = mock_repo.create_chunks.call_args[0][1]
    assert len(chunks_arg) == 2
    assert len(chunks_arg[0]) == 50
    assert len(chunks_arg[1]) == 1


# U-JOB-06
@pytest.mark.asyncio
async def test_pause_when_running(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "running"})
    await manager.pause()
    mock_repo.update_batch_job_status.assert_called_with("job-123", "paused")


# U-JOB-07
@pytest.mark.asyncio
async def test_pause_when_not_running(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "done"})
    await manager.pause()
    mock_repo.update_batch_job_status.assert_not_called()


# U-JOB-08
@pytest.mark.asyncio
async def test_resume_when_paused(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "paused"})
    await manager.resume()
    mock_repo.update_batch_job_status.assert_called_with("job-123", "running")


# U-JOB-09
@pytest.mark.asyncio
async def test_cancel_when_running(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "running"})
    await manager.cancel()
    mock_repo.update_batch_job_status.assert_called_with("job-123", "cancelled")


# U-JOB-10
@pytest.mark.asyncio
async def test_cancel_when_paused(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "paused"})
    await manager.cancel()
    mock_repo.update_batch_job_status.assert_called_with("job-123", "cancelled")


# U-JOB-11
@pytest.mark.asyncio
async def test_get_next_image_no_active_job(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value=None)
    job_id, image_id = await manager.get_next_image_id()
    assert job_id is None
    assert image_id is None


# U-JOB-12
@pytest.mark.asyncio
async def test_mark_image_done_completes_job(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "running"})
    mock_repo.get_batch_image_meta = AsyncMock(return_value={"gps_lat": None, "gps_lon": None})
    mock_repo.has_pending_chunks = AsyncMock(return_value=False)

    await manager.mark_image_done("img_0001")

    mock_repo.increment_batch_progress.assert_called_with("job-123", processed=1)
    mock_repo.update_batch_job_status.assert_called_with("job-123", "done")


# U-JOB-13
@pytest.mark.asyncio
async def test_get_status_no_job(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value=None)
    result = await manager.get_status()
    assert result["status"] == "idle"


# U-JOB-14: mark_image_done raises if no active batch (was: silent failure)
@pytest.mark.asyncio
async def test_mark_image_done_raises_without_active_job(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="No active batch"):
        await manager.mark_image_done("img_001")


# U-JOB-15: mark_image_done raises if image is not part of batch
@pytest.mark.asyncio
async def test_mark_image_done_raises_for_unknown_image(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-123", "status": "running"})
    mock_repo.get_batch_image_meta = AsyncMock(return_value=None)
    with pytest.raises(LookupError, match="not part of active batch"):
        await manager.mark_image_done("rogue_img")
    # Progress must NOT be incremented
    mock_repo.increment_batch_progress.assert_not_called()


# U-JOB-16: get_next_image_id returns (job_id, image_id) tuple
@pytest.mark.asyncio
async def test_get_next_image_id_returns_tuple(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-xyz", "status": "running"})
    mock_repo.get_next_unprocessed_image = AsyncMock(return_value="img_42")

    job_id, image_id = await manager.get_next_image_id()
    assert job_id == "job-xyz"
    assert image_id == "img_42"


# U-JOB-17: get_next_image_id when batch paused
@pytest.mark.asyncio
async def test_get_next_image_id_when_paused(manager, mock_repo):
    mock_repo.get_active_batch_job = AsyncMock(return_value={"id": "job-xyz", "status": "paused"})
    job_id, image_id = await manager.get_next_image_id()
    assert job_id is None
    assert image_id is None
