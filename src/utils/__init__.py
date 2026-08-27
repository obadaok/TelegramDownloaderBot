"""Utility helpers for the Telegram Downloader Bot."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from src.config.settings import settings


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path(settings.data_dir) / "bot.log", encoding="utf-8"),
        ],
    )


def clean_temp_files() -> None:
    """Remove temporary files."""
    from pathlib import Path
    for p in [settings.data_dir, settings.download_path, settings.thumbnail_path]:
        path = Path(p) if isinstance(p, str) else p
        if path.exists():
            for f in path.iterdir():
                if f.is_file() and f.suffix.lower() in (".tmp", ".part", ".ytdl"):
                    try:
                        f.unlink()
                    except OSError:
                        pass


def get_file_size(path: str) -> float:
    """Get file size in MB."""
    return os.path.getsize(path) / (1024 * 1024)


def is_valid_url(url: str) -> bool:
    """Validate URL format."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(("http://", "https://", "www.")):
        return False
    return bool(re.match(r"^https?://[^\s]+\.[^\s]+", url))


def detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to."""
    patterns = {
        "youtube": r"(?:youtube\.com|youtu\.be)",
        "tiktok": r"tiktok\.com",
        "instagram": r"instagram\.com",
        "facebook": r"facebook\.com|fb\.watch",
        "twitter": r"twitter\.com|x\.com",
        "reddit": r"reddit\.com|redd\.it",
        "vimeo": r"vimeo\.com",
        "twitch": r"twitch\.tv",
        "soundcloud": r"soundcloud\.com",
        "pinterest": r"pinterest\.com",
        "dailymotion": r"dailymotion\.com",
        "vk": r"vk\.com",
        "bilibili": r"bilibili\.com",
        "rumble": r"rumble\.com",
    }
    for platform, pattern in patterns.items():
        if re.search(pattern, url, re.IGNORECASE):
            return platform
    return "generic"


def truncate_text(text: str, max_len: int = 200) -> str:
    """Truncate text to max length."""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "..."


def format_size(bytes_val: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def format_duration(seconds: int) -> str:
    """Format duration to HH:MM:SS."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def is_admin(telegram_id: int) -> bool:
    """Check if user is an admin."""
    return telegram_id in settings.admin_ids


def get_user_name(user) -> str:
    """Get display name for a Telegram user."""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return f"User {user.id}"