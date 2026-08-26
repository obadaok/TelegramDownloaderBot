"""Database tests."""
import pytest
import asyncio
from src.database import init_db, close_db
from src.database.models import User, DownloadJob, JobStatus, JobType, Quality


@pytest.mark.asyncio
async def test_init_db():
    await init_db()
    await close_db()
