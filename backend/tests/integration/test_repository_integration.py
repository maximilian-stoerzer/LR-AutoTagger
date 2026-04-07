"""Integration tests for Repository against real PostgreSQL — I-REP-01 to I-REP-10."""

import pytest

pytestmark = pytest.mark.integration


# I-REP-01
@pytest.mark.asyncio
async def test_migration_creates_tables(repo):
    assert await repo.ping() is True


# I-REP-02
@pytest.mark.asyncio
async def test_double_migration_idempotent(repo):
    await repo.run_migrations()
    assert await repo.ping() is True


# I-REP-03
@pytest.mark.asyncio
async def test_batch_job_crud_lifecycle(repo):
    job = await repo.create_batch_job(100)
    assert job["status"] == "running"
    assert job["total_images"] == 100

    await repo.update_batch_job_status(job["id"], "paused")
    active = await repo.get_active_batch_job()
    assert active["status"] == "paused"

    await repo.update_batch_job_status(job["id"], "done")
    active = await repo.get_active_batch_job()
    assert active is None  # done is not active


# I-REP-04
@pytest.mark.asyncio
async def test_chunk_creation_and_query(repo):
    job = await repo.create_batch_job(10)
    await repo.create_chunks(job["id"], [["img_1", "img_2"], ["img_3", "img_4"]])

    # chunks should be in 'processing' state after create
    has = await repo.has_pending_chunks(job["id"])
    assert has is True


# I-REP-05
@pytest.mark.asyncio
async def test_image_keywords_upsert(repo):
    await repo.save_image_keywords(
        image_id="test_img",
        keywords=["Bruecke", "Fluss"],
        geo_keywords=["Heidelberg"],
        vision_keywords=["Bruecke", "Fluss"],
        gps_lat=49.4,
        gps_lon=8.7,
        location_name="Heidelberg",
        model_used="llava:13b",
    )

    result = await repo.get_image_keywords("test_img")
    assert result["keywords"] == ["Bruecke", "Fluss"]

    # Update
    await repo.save_image_keywords(
        image_id="test_img",
        keywords=["Berg", "Schnee"],
        geo_keywords=None,
        vision_keywords=["Berg", "Schnee"],
        gps_lat=None,
        gps_lon=None,
        location_name=None,
        model_used="llava:13b",
    )

    result = await repo.get_image_keywords("test_img")
    assert result["keywords"] == ["Berg", "Schnee"]


# I-REP-06
@pytest.mark.asyncio
async def test_get_next_unprocessed_image(repo):
    job = await repo.create_batch_job(3)
    images = [
        {"image_id": "img_b"},
        {"image_id": "img_a"},
        {"image_id": "img_c"},
    ]
    await repo.store_batch_image_meta(job["id"], images)

    first = await repo.get_next_unprocessed_image(job["id"])
    assert first == "img_a"  # alphabetical order


# I-REP-07
@pytest.mark.asyncio
async def test_mark_chunk_image_done_completes_chunk(repo):
    job = await repo.create_batch_job(2)
    await repo.create_chunks(job["id"], [["img_1", "img_2"]])
    await repo.store_batch_image_meta(
        job["id"],
        [
            {"image_id": "img_1"},
            {"image_id": "img_2"},
        ],
    )

    await repo.mark_chunk_image_done(job["id"], "img_1")
    # Chunk not yet complete
    assert await repo.has_pending_chunks(job["id"]) is True

    await repo.mark_chunk_image_done(job["id"], "img_2")
    # Now chunk should be done
    assert await repo.has_pending_chunks(job["id"]) is False


# I-REP-08
@pytest.mark.asyncio
async def test_has_pending_chunks_after_all_done(repo):
    job = await repo.create_batch_job(1)
    await repo.create_chunks(job["id"], [["img_1"]])
    await repo.store_batch_image_meta(job["id"], [{"image_id": "img_1"}])

    await repo.mark_chunk_image_done(job["id"], "img_1")
    assert await repo.has_pending_chunks(job["id"]) is False


# I-REP-09
@pytest.mark.asyncio
async def test_image_already_processed(repo):
    assert await repo.image_already_processed("nonexistent") is False

    await repo.save_image_keywords(
        image_id="exists",
        keywords=["Test"],
        geo_keywords=None,
        vision_keywords=["Test"],
        gps_lat=None,
        gps_lon=None,
        location_name=None,
        model_used="llava:13b",
    )

    assert await repo.image_already_processed("exists") is True


# I-REP-10
@pytest.mark.asyncio
async def test_nonexistent_image_returns_none(repo):
    result = await repo.get_image_keywords("does_not_exist")
    assert result is None
