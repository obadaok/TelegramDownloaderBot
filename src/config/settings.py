"""Configuration management for the Telegram Downloader Bot."""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Union

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bot
    bot_token: str = ""
    admin_ids: Union[List[int], int] = []

    # Concurrency & limits
    max_concurrent_downloads: int = 3
    max_queue_size: int = 50
    max_file_size_mb: int = 1900  # Telegram Bot API limit
    download_timeout_sec: int = 1800
    job_ttl_sec: int = 900  # dedupe TTL for repeated URLs

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    redis_url: str = "redis://localhost:6379/0"

    # yt-dlp tuning
    yt_dlp_concurrent_fragments: int = 4
    yt_dlp_socket_timeout: int = 60
    yt_dlp_retries: int = 5

    # Logging
    log_level: str = "INFO"

    # Runtime
    is_render: bool = False
    data_dir: str = "./data"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def download_path(self) -> Path:
        return self.data_path / "downloads"

    @property
    def thumbnail_path(self) -> Path:
        return self.data_path / "thumbnails"

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.download_path.mkdir(parents=True, exist_ok=True)
        self.thumbnail_path.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    if "RENDER" in os.environ:
        s.is_render = True
    # Normalize admin_ids to a list of ints
    if isinstance(s.admin_ids, int):
        s.admin_ids = [s.admin_ids]
    elif isinstance(s.admin_ids, str):
        if s.admin_ids:
            s.admin_ids = [int(x.strip()) for x in s.admin_ids.split(",") if x.strip()]
        else:
            s.admin_ids = []
    return s


settings = get_settings()
