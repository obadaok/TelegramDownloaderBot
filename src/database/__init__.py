"""Database module for the Telegram Downloader Bot."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from src.config.settings import settings

Base = declarative_base()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=300,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncSession:
    """Get a database session."""
    async with async_session_maker() as session:
        return session


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connection."""
    await engine.dispose()


# Import models to register them with Base.metadata
from src.database.models import User, DownloadJob  # noqa: E402