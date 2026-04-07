import logging

from app.config import settings
from app.db.repository import Repository

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self, repo: Repository):
        self.repo = repo

    async def create_job(self, images: list[dict]) -> dict:
        """Create a new batch job.

        images: list of dicts with keys: image_id, (optional) gps_lat, gps_lon

        The backend creates the job and chunks. The plugin then drives processing
        by polling /batch/next and uploading images via /batch/image.
        """
        # Filter already processed images (idempotency)
        new_images = []
        skipped = 0
        for img in images:
            if await self.repo.image_already_processed(img["image_id"]):
                skipped += 1
            else:
                new_images.append(img)

        total = len(new_images) + skipped
        job = await self.repo.create_batch_job(total)

        if skipped > 0:
            await self.repo.increment_batch_progress(job["id"], skipped=skipped)

        # Create chunks of image_ids
        chunk_size = settings.batch_chunk_size
        chunks = []
        for i in range(0, len(new_images), chunk_size):
            chunk_images = new_images[i : i + chunk_size]
            chunks.append([img["image_id"] for img in chunk_images])

        if chunks:
            await self.repo.create_chunks(job["id"], chunks)

        # Store image metadata for geocoding lookup
        await self.repo.store_batch_image_meta(job["id"], new_images)

        job["skipped"] = skipped
        return job

    async def get_next_image_id(self) -> tuple[str | None, str | None]:
        """Get the next image_id that needs processing in the active batch.

        Returns a (job_id, image_id) tuple. Either may be None.
        """
        job = await self.repo.get_active_batch_job()
        if not job or job["status"] != "running":
            return (None, None)
        image_id = await self.repo.get_next_unprocessed_image(job["id"])
        return (job["id"], image_id)

    async def mark_image_done(self, image_id: str) -> None:
        """Mark an image as processed and update batch/chunk progress.

        Raises:
            ValueError: if no active batch exists.
            LookupError: if image_id is not part of the active batch.
        """
        job = await self.repo.get_active_batch_job()
        if not job:
            raise ValueError("No active batch job")

        # Validate that the image belongs to this batch
        meta = await self.repo.get_batch_image_meta(job["id"], image_id)
        if meta is None:
            raise LookupError(f"image_id {image_id!r} is not part of active batch {job['id']}")

        await self.repo.increment_batch_progress(job["id"], processed=1)
        await self.repo.mark_chunk_image_done(job["id"], image_id)

        # Check if batch is complete
        if not await self.repo.has_pending_chunks(job["id"]):
            await self.repo.update_batch_job_status(job["id"], "done")
            logger.info("Batch job %s completed", job["id"])

    async def get_status(self) -> dict:
        job = await self.repo.get_active_batch_job()
        if not job:
            return {"status": "idle", "message": "No active batch job"}
        return job

    async def pause(self):
        job = await self.repo.get_active_batch_job()
        if job and job["status"] == "running":
            await self.repo.update_batch_job_status(job["id"], "paused")

    async def resume(self):
        job = await self.repo.get_active_batch_job()
        if job and job["status"] == "paused":
            await self.repo.update_batch_job_status(job["id"], "running")

    async def cancel(self):
        job = await self.repo.get_active_batch_job()
        if job and job["status"] in ("running", "paused"):
            await self.repo.update_batch_job_status(job["id"], "cancelled")
