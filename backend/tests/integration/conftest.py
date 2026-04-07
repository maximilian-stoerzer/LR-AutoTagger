"""Integration test fixtures — requires real PostgreSQL test database.

Set TEST_DATABASE_URL env var, e.g.:
  TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/lr_autotag_test
"""

import os

import pytest
import pytest_asyncio

from app.db.repository import Repository

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
skip_no_db = pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DATABASE_URL not set")


@pytest_asyncio.fixture
async def repo():
    """Provide a Repository connected to the test DB, with fresh schema."""
    if not TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set")

    # Temporarily override settings
    from app.config import settings

    original = settings.database_url
    settings.database_url = TEST_DB_URL

    r = Repository()
    await r.connect()

    # Clean slate: drop and re-create tables
    async with r._pool.connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS batch_images CASCADE")
        await conn.execute("DROP TABLE IF EXISTS chunks CASCADE")
        await conn.execute("DROP TABLE IF EXISTS image_keywords CASCADE")
        await conn.execute("DROP TABLE IF EXISTS batch_jobs CASCADE")
        await conn.execute("DROP TABLE IF EXISTS schema_version CASCADE")
        await conn.commit()

    await r.run_migrations()

    yield r

    await r.close()
    settings.database_url = original
