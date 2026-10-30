"""An offline speaker fails fast: /status polls share one read, a breaker skips the connect timeout while the
speaker is known to be down, and a background probe notices when it comes back. Both transports."""
import asyncio
import threading
import time
from types import SimpleNamespace

import httpx
import pychromecast.error
import pytest
from conftest import REAL_ENSURE_PROBE, TOKEN
from test_relay import FakeMqttClient, FakeRelay, mqtt_cfg

from transport import MqttRelayTransport

ATTEMPT = 0.4  # how long one (fake) connect attempt takes here; the real one is ~10 s
POLLS = 6  # browser tabs polling /status at once


class SlowSpeaker:
    """Stands in for CastTransport.get_cast: every connect takes ATTEMPT seconds, then fails or succeeds."""

    def __init__(self, cast, up=False):
        self.cast, self.up = cast, up
        self.attempts = 0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.attempts += 1
        time.sleep(ATTEMPT)
        if not self.up:
            raise pychromecast.error.ChromecastConnectionError("Failed to connect")
        return self.cast


@pytest.fixture
def slow(app, monkeypatch, fake_speaker):
    speaker = SlowSpeaker(fake_speaker)
    monkeypatch.setattr(app.transport, "get_cast", speaker)
    return speaker


def api(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url="http://test",
                             headers={"Authorization": f"Bearer {TOKEN}"})


async def polls_and_a_command(app, command=("/volume", {"level": 0.4})):
    """POLLS concurrent /status requests, then a command right behind them. Returns their responses and how
    long the command took."""
    async with api(app) as c:
        polls = [asyncio.create_task(c.get("/status")) for _ in range(POLLS)]
        await asyncio.sleep(0.05)  # the polls are in flight first, as when a user clicks during polling
        started = time.monotonic()
        r = await c.post(*command[:1], json=command[1])
        took = time.monotonic() - started
        return await asyncio.gather(*polls), r, took


# --- Cast ---

def test_offline_command_behind_many_polls_takes_one_attempt(app, slow, fresh_state):
    statuses, r, took = asyncio.run(polls_and_a_command(app))
    assert {s.status_code for s in statuses} == {503}
    assert r.status_code == 503 and "not responding" in r.json()["detail"]
    assert slow.attempts == 1  # before: one connect timeout per poll, then the command's own
    assert took < 2 * ATTEMPT  # before: (POLLS + 1) * ATTEMPT
    assert fresh_state.probes == 1  # a background retry was started


def test_live_command_behind_many_polls_still_works(app, slow):
    slow.up = True
    statuses, r, took = asyncio.run(polls_and_a_command(app))
    assert {s.status_code for s in statuses} == {200}
    assert r.status_code == 200 and slow.cast.volume == 0.4
    assert slow.attempts == 3  # one shared read (receiver + media) + the command, not one read per poll
    assert took < 3 * ATTEMPT


def test_known_offline_speaker_fails_at_once(client, app, slow):
    assert client.post("/pause").status_code == 503
    started = time.monotonic()
    for path in ("/pause", "/resume", "/stop"):
        r = client.post(path)
        assert r.status_code == 503 and "not responding" in r.json()["detail"]
    assert client.get("/status").status_code == 503
    assert time.monotonic() - started < ATTEMPT
    assert slow.attempts == 1


def test_hold_expiry_tries_the_speaker_again(client, app, slow, monkeypatch):
    monkeypatch.setattr(app, "OFFLINE_HOLD", 0)
    assert client.post("/pause").status_code == 503
    slow.up = True
    assert client.post("/pause").status_code == 200
    assert slow.attempts == 2 and app._offline is None


def test_background_probe_notices_recovery(app, slow, monkeypatch):
    monkeypatch.setattr(app, "ensure_probe", REAL_ENSURE_PROBE)
    monkeypatch.setattr(app, "PROBE_INTERVAL", 0.05)

    async def scenario():
        async with api(app) as c:
            assert (await c.post("/pause")).status_code == 503
            slow.up = True  # the speaker is switched back on
            deadline = time.monotonic() + 5 * ATTEMPT
            while app._offline is not None and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            recovered = app._offline is None
            r = await c.post("/volume", json={"level": 0.6})
            app.reset_reachability()  # don't leave the probe running past the loop
            return recovered, r

    recovered, r = asyncio.run(scenario())
    assert recovered
    assert r.status_code == 200 and slow.cast.volume == 0.6


def test_probe_keeps_failing_fast_while_down(app, slow, monkeypatch):
    monkeypatch.setattr(app, "ensure_probe", REAL_ENSURE_PROBE)
    monkeypatch.setattr(app, "PROBE_INTERVAL", 0.05)
    monkeypatch.setattr(app, "OFFLINE_HOLD", ATTEMPT)  # shorter than probe + attempt: renewal has to work

    async def scenario():
        async with api(app) as c:
            assert (await c.post("/pause")).status_code == 503
            took = []
            for _ in range(6):
                await asyncio.sleep(ATTEMPT / 2)
                started = time.monotonic()
                assert (await c.post("/pause")).status_code == 503
                took.append(time.monotonic() - started)
            app.reset_reachability()
            return took

    took = asyncio.run(scenario())
    # A command may wait for the probe's attempt in progress, but never pays a second attempt of its own.
    assert max(took) < 1.5 * ATTEMPT
    assert slow.attempts >= 2  # the probe kept retrying


def test_refused_command_does_not_mark_speaker_offline(client, app, fake_speaker, monkeypatch):
    def refuse(*args, **kwargs):
        raise pychromecast.error.RequestFailed("LOAD")

    monkeypatch.setattr(fake_speaker.media_controller, "pause", refuse)
    assert client.post("/pause").status_code == 503
    assert app._offline is None
    assert client.get("/status").status_code == 200


def test_status_is_shared_briefly_but_commands_refresh_it(client, app, fake_speaker):
    assert client.get("/status").json()["volume"] == 0.2
    fake_speaker.volume = 0.9  # changed behind our back (the speaker's own buttons)
    assert client.get("/status").json()["volume"] == 0.2  # within STATUS_TTL: the shared read
    assert client.post("/volume", json={"level": 0.5}).status_code == 200
    assert client.get("/status").json()["volume"] == 0.5


def test_status_cache_expires(client, app, fake_speaker, monkeypatch):
    monkeypatch.setattr(app, "STATUS_TTL", 0)
    client.get("/status")
    fake_speaker.volume = 0.9
    assert client.get("/status").json()["volume"] == 0.9


def test_changing_the_speaker_clears_offline_state(client, app, slow):
    assert client.post("/pause").status_code == 503
    assert app._offline is not None
    r = client.post("/settings", json={"speaker_ip": "192.0.2.11"})
    assert r.status_code == 200 and app._offline is None


# --- MQTT relay ---

@pytest.fixture
def hung_relay(app, monkeypatch):
    """A relay that's online on the broker but never answers, timing out on the real clock."""
    relay = FakeRelay(clock=SimpleNamespace(now=0.0))  # its clock only stamps positions
    relay.answer = False
    holder = {}

    def factory(cfg):
        holder["client"] = FakeMqttClient(relay)
        return holder["client"]

    t = MqttRelayTransport(mqtt_cfg(command_timeout=ATTEMPT), name="Test Speaker", client_factory=factory)
    holder["client"].on_connect(holder["client"], None, {}, 0, None)
    holder["client"].deliver("online", "true", retain=True)
    t.relay = relay
    monkeypatch.setattr(app, "transport", t)
    return t


def test_hung_relay_command_behind_many_polls_takes_one_timeout(app, hung_relay):
    statuses, r, took = asyncio.run(polls_and_a_command(app, ("/pause", None)))
    assert {s.status_code for s in statuses} == {503}
    assert r.status_code == 503 and "did not answer" in r.json()["detail"]
    assert took < 2 * ATTEMPT  # before: (POLLS + 1) * command_timeout


def test_relay_error_does_not_mark_speaker_offline(client, app, hung_relay):
    hung_relay.relay.answer, hung_relay.relay.fail = True, "busy"
    assert client.post("/pause").status_code == 503
    assert app._offline is None


def test_relay_recovers_through_the_probe(app, hung_relay, monkeypatch):
    monkeypatch.setattr(app, "ensure_probe", REAL_ENSURE_PROBE)
    monkeypatch.setattr(app, "PROBE_INTERVAL", 0.05)

    async def scenario():
        async with api(app) as c:
            assert (await c.post("/pause")).status_code == 503
            hung_relay.relay.answer = True
            deadline = time.monotonic() + 5 * ATTEMPT
            while app._offline is not None and time.monotonic() < deadline:
                await asyncio.sleep(0.05)
            recovered = app._offline is None
            r = await c.post("/pause")
            app.reset_reachability()
            return recovered, r

    recovered, r = asyncio.run(scenario())
    assert recovered and r.status_code == 200
