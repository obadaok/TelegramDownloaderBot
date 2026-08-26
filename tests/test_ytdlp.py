"""URL validation and yt-dlp tests."""
import pytest

from src.utils import detect_platform, is_valid_url


class TestURLValidation:
    def test_youtube_url(self):
        assert is_valid_url("https://youtube.com/watch?v=abc")
        assert is_valid_url("https://youtu.be/abc")

    def test_tiktok_url(self):
        assert is_valid_url("https://www.tiktok.com/@user/video/123")

    def test_invalid_url(self):
        assert not is_valid_url("not a url")
        assert not is_valid_url("")
        assert not is_valid_url(None)

    def test_detect_youtube(self):
        assert detect_platform("https://youtube.com/watch?v=abc") == "youtube"
        assert detect_platform("https://youtu.be/abc") == "youtube"

    def test_detect_tiktok(self):
        assert detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"

    def test_detect_generic(self):
        assert detect_platform("https://example.com/video") == "generic"
