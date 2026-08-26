"""Queue worker for handling download tasks."""
import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config.settings import settings
from src.database.models import JobType, JobStatus, Quality, User
from src.database import get_db_session
from src.queue import RedisQueue
from src.utils.logger import setup_logging
from src.download.youtube_downloader import YTDLPDownloader, get_downloader

logger = logging.getLogger(__name__)


@dataclass
class DownloadTask:
    job_id: int
    telegram_user_id: int
    url: str
    job_type: JobType
    quality: Quality
    priority: int = 1


class RedisQueue:
    """Wrapper around Redis for task queuing."""

    def __init__(self):
        from aioredis import from_url

        self._redis_url = settings.redis_url
        self._redis = None

    async def init(self):
        self._redis = await from_url(self._redis_url, decode_responses=True)

    async def close(self):
        if self._redis:
            await self._redis.close()

    async def push(self, task: Dict[str, Any]):
        """Push a task to the queue."""
        if not self._redis:
            raise RuntimeError("Redis queue not initialized")
        await self._redis.rpush("download_queue", str(task))

    async def pop(self) -> Optional[Dict[str, Any]]:
        """Pop a task from the queue."""
        if not self._redis:
            raise RuntimeError("Redis queue not initialized")
        item = await self._redis.lpop("download_queue")
        return json.loads(item) if item else None


class DownloadWorker:
    """Worker that processes download tasks."""

    def __init__(self, queue: RedisQueue):
        self.queue = queue
        self.downloader = get_downloader()
        self.db: Optional[asyncio.Semaphore] = None

    async def init(self):
        """Initialize the worker."""
        self.db = asyncio.Semaphore(settings.max_concurrent_downloads)
        await self.queue.init()

    async def close(self):
        await self.queue.close()

    async def _get_user(self, telegram_user_id: int) -> Optional[User]:
        """Get user from database."""
        async with get_db_session() as session:
            result = await session.execute(
                "SELECT * FROM users WHERE telegram_id = :id", 
                {"id": telegram_user_id}
            )
            return result.scalar_one_or_none()

    async def _create_user(self, telegram_user_id: int, username: str = None) -> User:
        """Create a new user record."""
        async with get_db_session() as session:
            user = User(
                telegram_id=telegram_user_id,
                username=username,
                display_name=username or "Unknown"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def _create_job(self, job_id: int, user: User, url: str, job_type: JobType, quality: Quality) -> DownloadJob:
        """Create a new job record."""
        async with get_db_session() as session:
            job = DownloadJob(
                url=url,
                telegram_user_id=user.id,
                platform=job_type.value,
                title="",
                thumbnail_url="",
                duration=0.0,
                job_type=job_type.value,
                quality=quality.value,
                status=JobStatus.PENDING.value,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def _update_job_status(self, job_id: int, status: JobStatus, **kwargs):
        """Update job status in database."""
        async with get_db_session() as session:
            result = await session.execute(
                "UPDATE download_jobs SET status = :status, updated_at = NOW() WHERE id = :id",
                {"status": status.value, "id": job_id}
            )
            if result.rowcount == 0:
                logger.warning("No job found with id %d", job_id)
                return

    async def _download_and_notify(self, task: Dict[str, Any]):
        """Perform the actual download and notify the user."""
        job_id = task["job_id"]
        telegram_user_id = task["telegram_user_id"]
        url = task["url"]
        job_type = DownloadTask.from_dict(task)
        quality = job_type.quality

        logger.info("Starting download job %d for user %d", job_id, telegram_user_id)

        # Check if job already exists and is completed
        async with get_db_session() as session:
            result = await session.execute(
                "SELECT * FROM download_jobs WHERE id = :id", {"id": job_id}
            )
            job = result.scalar_one_or_none()
            if not job:
                logger.error("Job %d not found in DB", job_id)
                return

            if job.status != JobStatus.PENDING.value:
                logger.info("Job %d already in state %s", job_id, job.status)
                return

            # Get or create user
            user = await self._get_user(telegram_user_id)
            if not user:
                user = await self._create_user(telegram_user_id, task.get("username", ""))

            # Update job info
            job.title = job_type.title or "Unknown"
            job.thumbnail_url = job_type.thumbnail or ""
            job.duration = job_type.duration or 0.0
            job.job_type = job_type.job_type
            job.quality = job_type.quality

            # Start downloading
            try:
                file_path = await self.downloader.download(
                    url=url,
                    job_id=job_id,
                    quality=quality,
                    kind=job_type.job_type
                )
                job.file_path = file_path
                job.status = JobStatus.COMPLETED.value
                job.file_size = os.path.getsize(file_path) if file_path else 0.0
                job.status = JobStatus.COMPLETED.value
                logger.info("Download completed for job %d", job_id)
            except Exception as e:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)
                logger.error("Download failed for job %d: %s", job_id, e)
                raise

            # Update job status
            await self._update_job_status(job_id, JobStatus.COMPLETED, file_path=file_path)

            # Notify user (this would go through the bot)
            # In a real implementation, this would trigger a Telegram message
            logger.info("Job %d completed successfully", job_id)

    async def process_tasks(self):
        """Main processing loop."""
        while True:
            try:
                task = await self.queue.pop()
                if not task:
                    # Queue is empty, wait a bit
                    await asyncio.sleep(1)
                    continue

                logger.info("Processing task: %s", task)
                await self._download_and_notify(task)

            except Exception as e:
                logger.exception("Error processing task: %s", e)
                await asyncio.sleep(1)

    async def start(self):
        """Start the worker."""
        await self.init()
        try:
            while True:
                await self.process_tasks()
        except asyncio.CancelledError:
            logger.info("Worker stopped")
            await self.close()


async def start_worker():
    """Main entry point for the worker."""
    queue = RedisQueue()
    worker = DownloadWorker(queue)
    await worker.init()
    try:
        await worker.process_tasks()
    finally:
        await worker.close()