"""yt-dlp integration for downloading videos and audio from various platforms."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

import yt_dlp

from src.config.settings import settings

logger = logging.getLogger(__name__)


# Platform detection patterns
PLATFORM_PATTERNS = {
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


@dataclass
class MediaInfo:
    """Normalized media metadata."""
    url: str
    platform: str
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    uploader: Optional[str] = None
    description: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    formats: Optional[List[Dict[str, Any]]] = None
    extractor: Optional[str] = None
    webpage_url: Optional[str] = None


def detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to."""
    for platform, pattern in PLATFORM_PATTERNS.items():
        if re.search(pattern, url, re.IGNORECASE):
            return platform
    return "generic"


def is_valid_url(url: str) -> bool:
    """Quick validation for a URL."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(("http://", "https://", "www.")):
        return False
    return bool(re.match(r"^https?://[^\s]+\.[^\s]+", url))


def _build_base_opts(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build common yt-dlp options."""
    opts: Dict[str, Any] = {
        "quiet": False,
        "no_warnings": False,
        "noprogress": True,
        "skip_download": True,
        "extract_flat": False,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "geo_bypass": True,
        "socket_timeout": settings.yt_dlp_socket_timeout,
        "retries": settings.yt_dlp_retries,
        "concurrent_fragment_downloads": settings.yt_dlp_concurrent_fragments,
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "extractor_args": {"youtube": {"player_client": ["default"]}},
    }
    if extra:
        opts.update(extra)
    return opts


def _format_size(bytes_val: Optional[int]) -> Optional[str]:
    if not bytes_val:
        return None
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def _format_duration(seconds: Optional[int]) -> Optional[str]:
    if not seconds:
        return None
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class YTDLPDownloader:
    """yt-dlp wrapper for extraction and downloading."""

    def __init__(self):
        self._info_cache: Dict[str, MediaInfo] = {}

    async def extract_info(self, url: str) -> Optional[MediaInfo]:
        """Extract normalized metadata about a URL."""
        cache_key = hashlib.sha256(url.encode()).hexdigest()
        if cache_key in self._info_cache:
            return self._info_cache[cache_key]

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, self._extract_sync, url)
        if info:
            self._info_cache[cache_key] = info
        return info

    def _extract_sync(self, url: str) -> Optional[MediaInfo]:
        opts = _build_base_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                data = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.exception("yt-dlp extract failed for %s: %s", url, e)
            return None

        if not data:
            return None

        # Some extractors wrap entries (playlists). Take the first.
        if "entries" in data and data["entries"]:
            data = data["entries"][0] or {}

        platform = detect_platform(data.get("webpage_url") or data.get("url") or url)
        extractor = data.get("extractor") or platform

        formats_raw = data.get("formats") or []
        formats: List[Dict[str, Any]] = []
        for f in formats_raw:
            if not f:
                continue
            # Audio-only
            if (f.get("vcodec") in (None, "none")) and f.get("acodec") not in (None, "none"):
                formats.append({
                    "type": "audio",
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "acodec": f.get("acodec"),
                    "abr": f.get("abr"),
                    "asr": f.get("asr"),
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "tbr": f.get("tbr"),
                })
                continue
            # Video
            formats.append({
                "type": "video",
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "height": f.get("height"),
                "width": f.get("width"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "fps": f.get("fps"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "tbr": f.get("tbr"),
                "format_note": f.get("format_note"),
            })

        return MediaInfo(
            url=url,
            platform=platform,
            title=data.get("title") or data.get("fulltitle") or "Unknown",
            thumbnail=data.get("thumbnail"),
            duration=data.get("duration"),
            uploader=data.get("uploader") or data.get("channel") or data.get("creator"),
            description=data.get("description"),
            view_count=data.get("view_count"),
            like_count=data.get("like_count"),
            formats=formats,
            extractor=extractor,
            webpage_url=data.get("webpage_url") or url,
        )

    async def download(
        self,
        url: str,
        job_id: int,
        quality: str = "best",
        kind: str = "video",
        progress_hook=None,
    ) -> Optional[str]:
        """Download to a file on disk and return its path."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._download_sync, url, job_id, quality, kind, progress_hook
        )

    def _download_sync(self, url: str, job_id: int, quality: str, kind: str, progress_hook=None) -> Optional[str]:
        download_dir = settings.download_path
        download_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(download_dir / f"{job_id}_%(id)s.%(ext)s")

        format_selector = self._build_format_selector(quality, kind)

        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "nocheckcertificate": True,
            "socket_timeout": settings.yt_dlp_socket_timeout,
            "retries": settings.yt_dlp_retries,
            "concurrent_fragment_downloads": settings.yt_dlp_concurrent_fragments,
            "outtmpl": outtmpl,
            "format": format_selector,
            "merge_output_format": "mp4" if kind == "video" else None,
            "postprocessors": [],
            "geo_bypass": True,
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "extractor_args": {"youtube": {"player_client": ["default"]}},
        }

        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        if kind == "audio":
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
            opts["format"] = "bestaudio/best"
            opts["outtmpl"] = str(download_dir / f"{job_id}_%(id)s.%(ext)s")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
                # Find resulting file
                if "requested_downloads" in info and info["requested_downloads"]:
                    return info["requested_downloads"][0].get("filepath")
                # Fallback: look for file matching outtmpl
                vid = info.get("id", str(uuid.uuid4()))
                for ext in ("mp4", "webm", "mkv", "mp3", "m4a", "opus"):
                    candidate = download_dir / f"{job_id}_{vid}.{ext}"
                    if candidate.exists():
                        return str(candidate)
                return None
        except Exception as e:
            logger.exception("yt-dlp download failed: %s", e)
            raise

    def _build_format_selector(self, quality: str, kind: str) -> str:
        if kind == "audio":
            return "ba/b"

        q = (quality or "best").lower()
        if q in ("best", ""):
            return "bv*+ba/b"
        if q in ("worst",):
            return "wv*+wa/w"
        height_map = {
            "1080p": 1080, "720p": 720, "480p": 480, "360p": 360,
            "240p": 240, "144p": 144,
        }
        h = height_map.get(q)
        if h:
            # Merge video + audio formats at or below height
            return f"bv*[height<={h}]+ba[height<={h}]/b[height<={h}]/bv*+ba/b"
        return "bv*+ba/b"


# Singleton
_downloader: Optional[YTDLPDownloader] = None


def get_downloader() -> YTDLPDownloader:
    global _downloader
    if _downloader is None:
        _downloader = YTDLPDownloader()
    return _downloader
