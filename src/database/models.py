"""Database models and session management."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    Float, ForeignKey, JSON, Index, UniqueConstraint,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

from src.config.settings import settings


Base = declarative_base()


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class Quality(str, Enum):
    BEST = "best"
    Q360 = "360p"
    Q480 = "480p"
    Q720 = "720p"
    Q1080 = "1080p"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    jobs = relationship("DownloadJob", back_populates="user", cascade="all, delete-orphan")


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, ForeignKey("users.telegram_id"), index=True)
    url = Column(Text, index=True)
    platform = Column(String(50))
    title = Column(Text)
    thumbnail_url = Column(Text)
    duration = Column(Float, nullable=True)
    job_type = Column(String(20))
    quality = Column(String(20))
    status = Column(String(20), default=JobStatus.PENDING.value, index=True)
    error_message = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)
    file_size = Column(Float, nullable=True)
    progress = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="jobs")


# Create engine
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
    async with async_session_maker() as session:
        return session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()