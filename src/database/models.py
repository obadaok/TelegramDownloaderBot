"""Database models for the Telegram Downloader Bot."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    Float, ForeignKey, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from src.database.base import Base


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