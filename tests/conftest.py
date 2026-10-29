"""Test setup: isolate config/cache/database in a temp dir and replace the speaker with a fake."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="speaker-test-"))
os.environ["CONFIG_PATH"] = str(_TMP / "config.json")
os.environ["CACHE_DIR"] = str(_TMP / "cache")
os.environ["DATA_PATH"] = str(_TMP / "data.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402
import transport as transport_module  # noqa: E402
from auth import Throttle, hash_password, new_session_token, token_hash  # noqa: E402
from store import Store  # noqa: E402

BASE = "http://test-host:8090"
TOKEN = "test-token"
PASSWORD = "correct horse"
PASSWORD_HASH = hash_password(PASSWORD)  # scrypt is slow; hash once for every test user
REAL_SCHEDULE_PREFETCH = app_module.schedule_prefetch
REAL_YT_DOWNLOAD = app_module.yt_download
REAL_YT_EXTRACT = app_module.yt_extract


class FakeMediaController:
    def __init__(self):
        self.status = SimpleNamespace(
            title=None, player_state="UNKNOWN", duration=None, current_time=None,
            adjusted_current_time=0.0, content_id=None, content_type=None, idle_reason=None,
        )
        self.loads = []
        self.paused = self.played = False

    def play_media(self, url, content_type, **kwargs):
        self.loads.append({"url": url, "content_type": content_type, **kwargs})
        self.status.content_id, self.status.content_type = url, content_type
        self.status.title, self.status.player_state = kwargs.get("title"), "PLAYING"
        self.status.idle_reason = None

    def finish(self, reason="FINISHED"):
        """The receiver reached the end of (or failed) the loaded media."""
        self.status.player_state, self.status.idle_reason = "IDLE", reason

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
    app_module.settings = app_module.Settings(public_base_url=BASE, api_token=TOKEN)
    speaker = transport_module.CastTransport("192.0.2.10", name=app_module.settings.speaker_name)
    speaker.get_cast = lambda: cast
    monkeypatch.setattr(app_module, "transport", speaker)
    app_module.save_settings(app_module.settings)
    app_module._resume = None
    app_module._say_gen = 0
    return cast


def _no_network(*args, **kwargs):
    raise AssertionError("tests must not reach YouTube; monkeypatch yt_download / yt_extract")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch, tmp_path):
    """Empty database, no queue, no throttling history; background tasks recorded instead of spawned."""
    monkeypatch.setattr(app_module, "db", Store(tmp_path / "data.db"))
    monkeypatch.setattr(app_module, "login_throttle", Throttle(limit=5, window=300))
    monkeypatch.setattr(app_module, "yt_download", _no_network)
    monkeypatch.setattr(app_module, "yt_extract", _no_network)
    app_module.clear_queue()
    app_module._downloads.clear()
    spawned = SimpleNamespace(watchers=0, prefetch=[])
    monkeypatch.setattr(app_module, "ensure_queue_watcher", lambda: setattr(spawned, "watchers", spawned.watchers + 1))
    monkeypatch.setattr(app_module, "schedule_prefetch", lambda q: spawned.prefetch.append(q.peek_next()))
    return spawned


def make_user(username="alice", role="admin", display_name=None, disabled=False):
    user = app_module.db.create_user(username, display_name or username.title(), role, PASSWORD_HASH)
    if disabled:
        user = app_module.db.update_user(user["id"], {"disabled": True})
    return user


def session_client(user, csrf=True):
    """A browser signed in as `user` (cookie session), sending the web UI's CSRF header unless csrf=False."""
    from fastapi.testclient import TestClient

    sid = new_session_token()
    app_module.db.create_session(token_hash(sid), user["id"])
    c = TestClient(app_module.app, headers={"X-Requested-With": "speaker-web"} if csrf else {})
    c.cookies.set("sid", sid)
    c.sid = sid
    return c


@pytest.fixture
def as_role():
    """as_role("operator") -> a signed-in browser client for a fresh user with that role."""
    def make(role, username=None):
        return session_client(make_user(username or f"{role}-user", role))

    return make


@pytest.fixture
def client():
    """A client holding the API token, like the web UI or an integration would."""
    from fastapi.testclient import TestClient

    return TestClient(app_module.app, headers={"Authorization": f"Bearer {TOKEN}"})


@pytest.fixture
def anon():
    """A client with no token, like the speaker fetching media or an outsider on the LAN."""
    from fastapi.testclient import TestClient

    return TestClient(app_module.app)


def path_of(url):
    """Strip the scheme and host so a signed media URL can be fetched through TestClient."""
    return url.removeprefix(BASE)
