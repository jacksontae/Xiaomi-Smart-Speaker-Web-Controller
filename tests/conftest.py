"""Test setup: isolate config/cache in a temp dir and replace the speaker with a fake."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="speaker-test-"))
os.environ["CONFIG_PATH"] = str(_TMP / "config.json")
os.environ["CACHE_DIR"] = str(_TMP / "cache")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402

BASE = "http://test-host:8090"
REAL_GET_CAST = app_module.get_cast


class FakeMediaController:
    def __init__(self):
        self.status = SimpleNamespace(
            title=None, player_state="UNKNOWN", duration=None, current_time=None,
            adjusted_current_time=0.0, content_id=None, content_type=None,
        )
        self.loads = []
        self.paused = self.played = False

    def play_media(self, url, content_type, **kwargs):
        self.loads.append({"url": url, "content_type": content_type, **kwargs})
        self.status.content_id, self.status.content_type = url, content_type
        self.status.title, self.status.player_state = kwargs.get("title"), "PLAYING"

    def block_until_active(self, timeout=None):
        pass

    def pause(self):
        self.paused = True

    def play(self):
        self.played = True


class FakeCast:
    def __init__(self):
        self.app_id = None
        self.started = []
        self.volume = 0.2
        self.quit = False
        self.media_controller = FakeMediaController()
        self.cast_info = SimpleNamespace(friendly_name="Test Speaker")

    @property
    def status(self):
        return SimpleNamespace(display_name="Default Media Receiver" if self.app_id else None,
                               volume_level=self.volume, volume_muted=False)

    def start_app(self, app_id):
        self.started.append(app_id)
        self.app_id = app_id

    def wait(self, timeout=None):
        pass

    def set_volume(self, level):
        self.volume = level

    def quit_app(self):
        self.quit = True
        self.app_id = None


@pytest.fixture
def app():
    return app_module


@pytest.fixture(autouse=True)
def fake_speaker(monkeypatch):
    cast = FakeCast()
    monkeypatch.setattr(app_module, "get_cast", lambda: cast)
    app_module.settings = app_module.Settings(public_base_url=BASE)
    app_module.save_settings(app_module.settings)
    app_module._resume = None
    app_module._say_gen = 0
    return cast


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(app_module.app)
