import pathlib

from psycopg_pool import AsyncConnectionPool

from app.config import settings

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "migrations"


class Repository:
    def __init__(self):
        self._pool: AsyncConnectionPool | None = None

    async def connect(self):
        self._pool = AsyncConnectionPool(conninfo=settings.database_url, min_size=2, max_size=10)
        await self._pool.open()

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def ping(self) -> bool:
        try:
            async with self._pool.connection() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def run_migrations(self):
        async with self._pool.connection() as conn:
            # Ensure schema_version table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)

            row = await (await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")).fetchone()
            current_version = row[0]

            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for mf in migration_files:
                version = int(mf.stem.split("_")[0])
                if version > current_version:
                    sql = mf.read_text()
                    await conn.execute(sql)
            await conn.commit()

    # --- Image Keywords ---

    async def get_image_keywords(self, image_id: str) -> dict | None:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT image_id, keywords, geo_keywords, vision_keywords, "
                    "gps_lat, gps_lon, location_name, model_used, processed_at "
                    "FROM image_keywords WHERE image_id = %s",
                    (image_id,),
                )
            ).fetchone()
            if not row:
                return None
            return {
                "image_id": row[0],
                "keywords": row[1],
                "geo_keywords": row[2],
                "vision_keywords": row[3],
                "gps_lat": row[4],
                "gps_lon": row[5],
                "location_name": row[6],
                "model_used": row[7],
                "processed_at": row[8].isoformat() if row[8] else None,
            }

    async def image_already_processed(self, image_id: str) -> bool:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute("SELECT 1 FROM image_keywords WHERE image_id = %s", (image_id,))
            ).fetchone()
            return row is not None

    async def save_image_keywords(
        self,
        image_id: str,
        keywords: list[str],
        geo_keywords: list[str] | None,
        vision_keywords: list[str] | None,
        gps_lat: float | None,
        gps_lon: float | None,
        location_name: str | None,
        model_used: str,
    ):
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO image_keywords
                    (image_id, keywords, geo_keywords, vision_keywords, gps_lat, gps_lon, location_name, model_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (image_id) DO UPDATE SET
                    keywords = EXCLUDED.keywords,
                    geo_keywords = EXCLUDED.geo_keywords,
                    vision_keywords = EXCLUDED.vision_keywords,
                    gps_lat = EXCLUDED.gps_lat,
                    gps_lon = EXCLUDED.gps_lon,
                    location_name = EXCLUDED.location_name,
                    model_used = EXCLUDED.model_used,
                    processed_at = now()
                """,
                (image_id, keywords, geo_keywords, vision_keywords, gps_lat, gps_lon, location_name, model_used),
            )
            await conn.commit()

    # --- Batch Jobs ---

    async def create_batch_job(self, total_images: int) -> dict:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "INSERT INTO batch_jobs (total_images, status) VALUES (%s, 'running') "
                    "RETURNING id, status, total_images, processed, failed, skipped, created_at",
                    (total_images,),
                )
            ).fetchone()
            await conn.commit()
            return {
                "id": str(row[0]),
                "status": row[1],
                "total_images": row[2],
                "processed": row[3],
                "failed": row[4],
                "skipped": row[5],
                "created_at": row[6].isoformat(),
            }

    async def get_active_batch_job(self) -> dict | None:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT id, status, total_images, processed, failed, skipped, created_at, updated_at "
                    "FROM batch_jobs WHERE status IN ('running', 'paused', 'pending') "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            ).fetchone()
            if not row:
                return None
            return {
                "id": str(row[0]),
                "status": row[1],
                "total_images": row[2],
                "processed": row[3],
                "failed": row[4],
                "skipped": row[5],
                "created_at": row[6].isoformat(),
                "updated_at": row[7].isoformat(),
            }

    async def update_batch_job_status(self, job_id: str, status: str):
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE batch_jobs SET status = %s, updated_at = now() WHERE id = %s",
                (status, job_id),
            )
            await conn.commit()

    async def increment_batch_progress(self, job_id: str, processed: int = 0, failed: int = 0, skipped: int = 0):
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE batch_jobs SET processed = processed + %s, failed = failed + %s, "
                "skipped = skipped + %s, updated_at = now() WHERE id = %s",
                (processed, failed, skipped, job_id),
            )
            await conn.commit()

    # --- Chunks ---

    async def create_chunks(self, batch_id: str, image_id_lists: list[list[str]]):
        async with self._pool.connection() as conn:
            for image_ids in image_id_lists:
                await conn.execute(
                    "INSERT INTO chunks (batch_id, image_ids, status) VALUES (%s, %s, 'processing')",
                    (batch_id, image_ids),
                )
            await conn.commit()

    async def get_next_pending_chunk(self, batch_id: str) -> dict | None:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT id, image_ids, attempt FROM chunks "
                    "WHERE batch_id = %s AND status = 'pending' "
                    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
                    (batch_id,),
                )
            ).fetchone()
            if not row:
                return None
            chunk_id = str(row[0])
            await conn.execute(
                "UPDATE chunks SET status = 'processing', started_at = now(), attempt = attempt + 1 WHERE id = %s",
                (chunk_id,),
            )
            await conn.commit()
            return {"id": chunk_id, "image_ids": row[1], "attempt": row[2] + 1}

    async def complete_chunk(self, chunk_id: str):
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE chunks SET status = 'done', completed_at = now() WHERE id = %s",
                (chunk_id,),
            )
            await conn.commit()

    async def fail_chunk(self, chunk_id: str, error: str, max_retries: int):
        async with self._pool.connection() as conn:
            row = await (await conn.execute("SELECT attempt FROM chunks WHERE id = %s", (chunk_id,))).fetchone()
            attempt = row[0] if row else 0
            if attempt >= max_retries:
                new_status = "failed"
            else:
                new_status = "pending"  # Back to queue for retry
            await conn.execute(
                "UPDATE chunks SET status = %s, error_message = %s, completed_at = now() WHERE id = %s",
                (new_status, error, chunk_id),
            )
            await conn.commit()

    async def has_pending_chunks(self, batch_id: str) -> bool:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT 1 FROM chunks WHERE batch_id = %s AND status IN ('pending', 'processing') LIMIT 1",
                    (batch_id,),
                )
            ).fetchone()
            return row is not None

    # --- Batch Image Metadata ---

    async def store_batch_image_meta(self, batch_id: str, images: list[dict]):
        async with self._pool.connection() as conn:
            for img in images:
                await conn.execute(
                    "INSERT INTO batch_images (batch_id, image_id, gps_lat, gps_lon) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (batch_id, img["image_id"], img.get("gps_lat"), img.get("gps_lon")),
                )
            await conn.commit()

    async def get_next_unprocessed_image(self, batch_id: str) -> str | None:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT image_id FROM batch_images "
                    "WHERE batch_id = %s AND status = 'pending' "
                    "ORDER BY image_id LIMIT 1",
                    (batch_id,),
                )
            ).fetchone()
            return row[0] if row else None

    async def get_batch_image_meta(self, batch_id: str, image_id: str) -> dict | None:
        async with self._pool.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT gps_lat, gps_lon FROM batch_images "
                    "WHERE batch_id = %s AND image_id = %s",
                    (batch_id, image_id),
                )
            ).fetchone()
            if not row:
                return None
            return {"gps_lat": row[0], "gps_lon": row[1]}

    async def mark_batch_image_done(self, batch_id: str, image_id: str):
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE batch_images SET status = 'done' WHERE batch_id = %s AND image_id = %s",
                (batch_id, image_id),
            )
            await conn.commit()

    async def mark_chunk_image_done(self, batch_id: str, image_id: str):
        """Mark image done in batch_images and check if its chunk is complete."""
        await self.mark_batch_image_done(batch_id, image_id)

        async with self._pool.connection() as conn:
            # Find the chunk containing this image and check if all its images are done
            rows = await (
                await conn.execute(
                    "SELECT c.id, c.image_ids FROM chunks c "
                    "WHERE c.batch_id = %s AND c.status = 'processing' AND %s = ANY(c.image_ids)",
                    (batch_id, image_id),
                )
            ).fetchall()

            for row in rows:
                chunk_id = str(row[0])
                chunk_image_ids = row[1]
                # Check if all images in this chunk are done
                pending = await (
                    await conn.execute(
                        "SELECT COUNT(*) FROM batch_images "
                        "WHERE batch_id = %s AND image_id = ANY(%s) AND status = 'pending'",
                        (batch_id, chunk_image_ids),
                    )
                ).fetchone()
                if pending[0] == 0:
                    await conn.execute(
                        "UPDATE chunks SET status = 'done', completed_at = now() WHERE id = %s",
                        (chunk_id,),
                    )
            await conn.commit()
