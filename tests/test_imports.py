"""Basic syntax and import tests."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_import_settings():
    from src.config.settings import settings
    assert settings is not None

def test_import_models():
    from src.database.models import User, DownloadJob, JobStatus, Quality
    assert JobStatus.PENDING.value == "pending"
