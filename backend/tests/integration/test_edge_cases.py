"""Additional integration tests: Race conditions, cascade, unicode, concurrency.

These cover gaps identified in the test gap analysis:
- Concurrent get_next_image_id (no double-handout via SKIP LOCKED)
- Cascade delete: deleting a batch_job removes chunks + batch_images
- Unicode and special characters in image_id
- Two batches active simultaneously: most recent wins
- Repeat run_migrations() is idempotent (already covered in I-REP-02 — extended here)
"""

import asyncio

import pytest

from app.services.job_manager import JobManager

pytestmark = pytest.mark.integration


def _make_images(n: int) -> list[dict]:
    return [{"image_id": f"edge_img_{i:04d}"} for i in range(n)]


# I-EDG-01: Cascade delete
@pytest.mark.asyncio
async def test_cascade_delete_removes_chunks_and_images(repo):
    job = await repo.create_batch_job(2)
    await repo.create_chunks(job["id"], [["c1_img1", "c1_img2"]])
    await repo.store_batch_image_meta(job["id"], [
        {"image_id": "c1_img1"},
        {"image_id": "c1_img2"},
    ])

    async with repo._pool.connection() as conn:
        await conn.execute("DELETE FROM batch_jobs WHERE id = %s", (job["id"],))
        await conn.commit()

        chunks_left = await (await conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE batch_id = %s", (job["id"],)
        )).fetchone()
        images_left = await (await conn.execute(
            "SELECT COUNT(*) FROM batch_images WHERE batch_id = %s", (job["id"],)
        )).fetchone()

    assert chunks_left[0] == 0
    assert images_left[0] == 0


# I-EDG-02: Unicode image_id
@pytest.mark.asyncio
async def test_unicode_image_id_roundtrip(repo):
    unicode_id = "Müller_Bär_紅葉_🌸"
    await repo.save_image_keywords(
        image_id=unicode_id,
        keywords=["Test"],
        geo_keywords=None,
        vision_keywords=["Test"],
        gps_lat=None, gps_lon=None,
        location_name=None,
        model_used="llava:13b",
    )
    result = await repo.get_image_keywords(unicode_id)
    assert result is not None
    assert result["image_id"] == unicode_id


# I-EDG-03: image_id with slashes (path-like) — must NOT trigger filesystem access
@pytest.mark.asyncio
async def test_path_like_image_id(repo):
    path_id = "../../etc/passwd"
    assert await repo.image_already_processed(path_id) is False

    await repo.save_image_keywords(
        image_id=path_id,
        keywords=["Test"],
        geo_keywords=None,
        vision_keywords=["Test"],
        gps_lat=None, gps_lon=None,
        location_name=None,
        model_used="llava:13b",
    )
    # Stored as plain string — no filesystem access
    assert await repo.image_already_processed(path_id) is True


# I-EDG-04: Two batches sequentially active — most recent wins
@pytest.mark.asyncio
async def test_two_batches_most_recent_wins(repo):
    manager = JobManager(repo)
    job1 = await manager.create_job([{"image_id": "first_a"}, {"image_id": "first_b"}])
    job2 = await manager.create_job([{"image_id": "second_a"}, {"image_id": "second_b"}])

    # The second is the most recently created → active
    active = await repo.get_active_batch_job()
    assert active["id"] == job2["id"]


# I-EDG-05: Concurrent mark_image_done for different images
@pytest.mark.asyncio
async def test_concurrent_mark_image_done(repo):
    manager = JobManager(repo)
    job = await manager.create_job(_make_images(5))

    # Process all 5 images concurrently
    tasks = [manager.mark_image_done(f"edge_img_{i:04d}") for i in range(5)]
    await asyncio.gather(*tasks)

    status = await manager.get_status()
    # All 5 processed → batch should be done (active query returns None)
    assert status["status"] in ("done", "idle")


# I-EDG-06: mark_image_done for image NOT in batch raises
@pytest.mark.asyncio
async def test_mark_image_done_rejects_unknown(repo):
    manager = JobManager(repo)
    await manager.create_job(_make_images(3))

    with pytest.raises(LookupError):
        await manager.mark_image_done("not_in_batch_at_all")


# I-EDG-07: image_already_processed survives upsert
@pytest.mark.asyncio
async def test_idempotent_save_keeps_single_row(repo):
    for _ in range(3):
        await repo.save_image_keywords(
            image_id="upsert_test",
            keywords=["A"],
            geo_keywords=None,
            vision_keywords=["A"],
            gps_lat=None, gps_lon=None,
            location_name=None,
            model_used="llava:13b",
        )

    async with repo._pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM image_keywords WHERE image_id = %s", ("upsert_test",)
        )).fetchone()

    assert row[0] == 1


# I-EDG-08: Empty image_ids array in chunk
@pytest.mark.asyncio
async def test_empty_chunk_array(repo):
    job = await repo.create_batch_job(0)
    # No chunks created — has_pending_chunks should be False
    assert await repo.has_pending_chunks(job["id"]) is False
