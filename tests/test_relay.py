"""MqttRelayTransport against a fake broker + relay (no network), and the settings that select it."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from conftest import BASE, TOKEN

import transport as transport_module
from transport import MqttRelayTransport, TransportError

TOPIC = "speaker-relay/test-relay"


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.step = 0.0  # advance on every read (lets a command's wait loop reach its deadline)

    def __call__(self):
        self.now += self.step
        return self.now


class FakeRelay:
    """Plays the firmware's part: answers <base>/cmd on <base>/result with the speaker object."""

    def __init__(self, clock):
        self.clock = clock
        self.playing_since = None  # clock time the current position was taken at, while PLAYING
        self.speaker = {"connected": True, "ip": "192.0.2.20", "app": "", "volume": 0.3, "muted": False,
                        "media": {"title": "", "state": "", "position": 0, "content_id": ""}}
        self.answer = True  # False = swallow commands (relay hung)
        self.fail = None  # error string to reply with

    def handle(self, cmd):
        if not self.answer:
            return None
        out = {"id": cmd["id"]}
        if self.fail:
            return {**out, "ok": False, "error": self.fail}
        media = self.speaker["media"]
        self._settle()
        kind = cmd["cmd"]
        if kind == "play":
            if "volume" in cmd:
                self.speaker["volume"] = cmd["volume"]
            self.speaker["app"] = "Default Media Receiver"
            media.update(content_id=cmd["url"], title=cmd["title"], state="PLAYING",
                         position=cmd.get("position", 0))
            media.pop("idle_reason", None)
        elif kind == "volume":
            self.speaker["volume"] = cmd["level"]
        elif kind == "pause":
            media["state"] = "PAUSED"
        elif kind == "resume":
            media["state"] = "PLAYING"
        elif kind == "stop":
            self.speaker["app"] = ""
            media["state"] = ""
        self.playing_since = self.clock.now if media["state"] == "PLAYING" else None
        return {**out, "ok": True, "speaker": json.loads(json.dumps(self.speaker))}

    def _settle(self):
        """Bring the position up to now, like the firmware extrapolating between Cast status updates."""
        if self.playing_since is not None:
            self.speaker["media"]["position"] += self.clock.now - self.playing_since
            self.playing_since = self.clock.now

    def finish(self, reason="FINISHED"):
        self._settle()
        self.playing_since = None
        self.speaker["media"].update(state="IDLE", idle_reason=reason)


class FakeMqttClient:
    """Stands in for paho's Client: records calls and routes published commands to a FakeRelay."""

    def __init__(self, relay):
        self.relay = relay
        self.published, self.subscribed, self.calls = [], [], []
        self.on_connect = self.on_disconnect = self.on_message = None
        self.publish_rc = 0

    def reconnect_delay_set(self, min_delay, max_delay):
        self.calls.append(("reconnect_delay_set", min_delay, max_delay))

    def connect_async(self, host, port, keepalive):
        self.calls.append(("connect_async", host, port, keepalive))

    def loop_start(self):
        self.calls.append(("loop_start",))

    def loop_stop(self):
        self.calls.append(("loop_stop",))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def subscribe(self, topics):
        self.subscribed.extend(topics)

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append({"topic": topic, "payload": json.loads(payload), "qos": qos, "retain": retain})
        if self.publish_rc == 0 and topic.endswith("/cmd"):
            reply = self.relay.handle(json.loads(payload))
            if reply is not None:
                self.deliver("result", reply)
        return SimpleNamespace(rc=self.publish_rc)

    # broker -> us
    def deliver(self, leaf, payload, retain=False):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.on_message(self, None, SimpleNamespace(topic=f"{TOPIC}/{leaf}", payload=body.encode(), retain=retain))

    def commands(self):
        return [p["payload"] for p in self.published if p["topic"] == f"{TOPIC}/cmd"]


def mqtt_cfg(**overrides):
    from app import MqttSettings

    return MqttSettings(host="broker.example.com", base_topic=TOPIC, username="change-me", password="change-me",
                        **overrides)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def relay(clock):
    return FakeRelay(clock)


@pytest.fixture
def make_relay_transport(relay, clock):
    def make(online=True, **cfg):
        holder = {}

        def factory(c):
            holder["client"] = FakeMqttClient(relay)
            return holder["client"]

        t = MqttRelayTransport(mqtt_cfg(**cfg), name="Test Speaker", client_factory=factory, clock=clock,
                               wall=lambda: clock.now + 1_700_000_000)
        t.fake = holder["client"]
        if online:
            t.fake.on_connect(t.fake, None, {}, 0, None)
            t.fake.deliver("online", "true", retain=True)
        return t

    return make


@pytest.fixture
def mqtt_transport(make_relay_transport):
    return make_relay_transport()


# --- Connection ---

def test_start_connects_with_backoff_and_subscribes(make_relay_transport):
    t = make_relay_transport(online=False, port=8883, keepalive=30, reconnect_min=2, reconnect_max=120)
    assert ("reconnect_delay_set", 2, 120) in t.fake.calls
    t.start()
    assert ("connect_async", "broker.example.com", 8883, 30) in t.fake.calls and ("loop_start",) in t.fake.calls
    assert not t.broker_connected
    t.fake.on_connect(t.fake, None, {}, 5, None)  # refused (e.g. bad credentials): stay disconnected
    assert not t.broker_connected and t.fake.subscribed == []
    t.fake.on_connect(t.fake, None, {}, 0, None)
    assert t.broker_connected
    assert sorted(t.fake.subscribed) == [(f"{TOPIC}/online", 1), (f"{TOPIC}/result", 1), (f"{TOPIC}/status", 1)]
    t.close()
    assert t.fake.calls[-2:] == [("disconnect",), ("loop_stop",)]


def test_paho_client_is_configured_for_tls_and_credentials():
    pytest.importorskip("paho.mqtt.client")
    client = transport_module.paho_client(mqtt_cfg(client_id="speaker-service-test"))
    assert client._client_id == b"speaker-service-test"
    assert client._username == b"change-me" and client._ssl


# --- Command payloads ---

def test_command_payloads(mqtt_transport):
    t = mqtt_transport
    t.play("https://speaker.example.com/yt/a.m4a?sig=x", "audio/mp4", "Song", 0.4, 12.5)
    t.play("https://speaker.example.com/tts.mp3?sig=y", "audio/mp3")
    t.set_volume(0.25)
    t.pause()
    t.resume()
    t.stop()
    sent = t.fake.commands()
    ids = [c.pop("id") for c in sent]
    assert len(set(ids)) == len(ids)
    assert sent == [
        {"cmd": "play", "url": "https://speaker.example.com/yt/a.m4a?sig=x", "content_type": "audio/mp4",
         "title": "Song", "volume": 0.4, "position": 12.5},
        {"cmd": "play", "url": "https://speaker.example.com/tts.mp3?sig=y", "content_type": "audio/mp3", "title": ""},
        {"cmd": "volume", "level": 0.25},
        {"cmd": "pause"},
        {"cmd": "resume"},
        {"cmd": "stop"},
    ]
    assert all(p["qos"] == 1 and not p["retain"] for p in t.fake.published)


def test_status_command_refreshes_stale_state(mqtt_transport, clock):
    t = mqtt_transport
    t.media()
    assert [c["cmd"] for c in t.fake.commands()] == ["status"]
    t.media()  # fresh: no second round trip
    assert len(t.fake.commands()) == 1
    clock.now += t.cfg.status_refresh + 0.1
    t.receiver()
    assert len(t.fake.commands()) == 2


# --- Status mapping ---

def test_media_state_maps_relay_status(mqtt_transport, relay, clock):
    t = mqtt_transport
    url = "https://speaker.example.com/yt/a.m4a?sig=x"
    t.play(url, "audio/mp4", "Song", None, 30)
    m = t.media()
    assert (m.content_id, m.content_type, m.title, m.player_state) == (url, "audio/mp4", "Song", "PLAYING")
    assert m.current_time == 30 and m.adjusted_current_time == 30 and m.idle_reason is None
    clock.now += 1.5  # still fresh; the position keeps running while PLAYING
    assert t.media().adjusted_current_time == pytest.approx(31.5)
    relay.finish()
    clock.now += 5
    m = t.media()
    assert (m.player_state, m.idle_reason) == ("IDLE", "FINISHED")
    r = t.receiver()
    assert (r.name, r.ip, r.app, r.volume, r.muted) == ("Test Speaker", "192.0.2.20", "Default Media Receiver", 0.3,
                                                        False)


def test_nothing_loaded_maps_to_unknown(mqtt_transport):
    m = mqtt_transport.media()
    assert m.player_state == "UNKNOWN" and m.content_id is None and m.current_time is None
    r = mqtt_transport.receiver()
    assert r.app is None


def test_periodic_status_updates_state_and_relay_info(mqtt_transport, relay):
    t = mqtt_transport
    relay.speaker["media"].update(state="PAUSED", content_id="https://speaker.example.com/x", position=7)
    t.fake.deliver("status", {"version": "1.2.0", "ip": "192.0.2.21", "rssi": -60, "heap": 150000,
                              "speaker": relay.speaker})
    m = t.media()
    assert m.player_state == "PAUSED" and m.current_time == 7
    assert t.fake.commands() == []  # a live status message counts as fresh
    info = t.relay_status()
    assert info["online"] and info["firmware_version"] == "1.2.0" and info["relay_ip"] == "192.0.2.21"
    assert info["rssi"] == -60 and info["last_seen"].endswith("Z") and info["base_topic"] == TOPIC


def test_retained_status_is_not_trusted_as_fresh(mqtt_transport, relay):
    t = mqtt_transport
    t.fake.deliver("status", {"version": "1.0", "speaker": relay.speaker}, retain=True)
    t.media()
    assert [c["cmd"] for c in t.fake.commands()] == ["status"]


def test_garbage_messages_are_ignored(mqtt_transport):
    t = mqtt_transport
    t.fake.deliver("status", "not json")
    t.fake.deliver("status", "[1, 2]")
    t.fake.deliver("result", {"id": "someone-else", "ok": True})
    assert t.online


# --- Online / offline ---

def test_never_seen_relay_is_offline(make_relay_transport):
    t = make_relay_transport(online=False)
    t.fake.on_connect(t.fake, None, {}, 0, None)
    assert not t.online
    with pytest.raises(TransportError, match="never seen"):
        t.pause()
    assert t.fake.commands() == []
    assert t.relay_status()["last_seen"] is None


def test_last_will_marks_relay_offline_and_status_brings_it_back(mqtt_transport, relay):
    t = mqtt_transport
    assert t.online
    t.fake.deliver("online", "false", retain=True)
    assert not t.online
    with pytest.raises(TransportError, match="offline"):
        t.stop()
    t.fake.deliver("status", {"version": "1.0", "speaker": relay.speaker})
    assert t.online


def test_silence_past_offline_after_marks_relay_offline(mqtt_transport, clock):
    t = mqtt_transport
    clock.now += t.cfg.offline_after - 1
    assert t.online
    clock.now += 2
    assert not t.online
    assert not t.relay_status()["online"] and t.relay_status()["seconds_since_seen"] >= t.cfg.offline_after
    with pytest.raises(TransportError, match=r"last seen \d+ s ago"):
        t.media()


def test_broker_disconnect_marks_relay_offline(mqtt_transport):
    t = mqtt_transport
    t.fake.on_disconnect(t.fake, None, {}, 7, None)
    assert not t.online and not t.relay_status()["broker_connected"]
    with pytest.raises(TransportError, match="MQTT broker"):
        t.pause()


def test_unanswered_command_times_out(mqtt_transport, relay, clock):
    relay.answer = False
    clock.step = 5.0
    with pytest.raises(TransportError, match="did not answer 'pause' within 10 s"):
        mqtt_transport.pause()


def test_relay_error_is_reported(mqtt_transport, relay):
    relay.fail = 'speaker "Kitchen" not found on this network'
    with pytest.raises(TransportError, match="Speaker relay: speaker \"Kitchen\" not found"):
        mqtt_transport.set_volume(0.5)


def test_failed_publish_is_reported(mqtt_transport):
    mqtt_transport.fake.publish_rc = 4
    with pytest.raises(TransportError, match="publish failed"):
        mqtt_transport.pause()


# --- Through the app: announcement -> resume, queue, /status ---

@pytest.fixture
def relay_app(app, monkeypatch, mqtt_transport):
    monkeypatch.setattr(app, "transport", mqtt_transport)
    return app


def test_announcement_resumes_track_through_relay(relay_app, client, relay, clock, monkeypatch):
    app, t = relay_app, relay_app.transport
    spawned = []
    monkeypatch.setattr(app, "spawn", lambda coro: spawned.append(coro))
    track = app.media_url("/yt/abc.m4a")
    asyncio.run(app.run_cast(app.cast_play, track, "audio/mp4", "Song"))
    clock.now += 40  # 40 s into the song (status refreshed through the relay)
    r = client.post("/say", json={"text": "dinner is ready"})
    assert r.status_code == 200 and r.json()["will_resume"] == "Song"
    plays = [c for c in t.fake.commands() if c["cmd"] == "play"]
    assert plays[-1]["url"].startswith(f"{BASE}/tts.mp3?") and plays[-1]["title"] == "Announcement"
    relay.finish()
    clock.now += 5
    (watcher,) = spawned
    asyncio.run(watcher)
    resumed = [c for c in t.fake.commands() if c["cmd"] == "play"][-1]
    assert resumed["url"] == track and resumed["content_type"] == "audio/mp4" and resumed["title"] == "Song"
    assert resumed["position"] == pytest.approx(40 - app.RESUME_REWIND)
    assert app._resume is None


def test_resume_dropped_when_relay_goes_offline(relay_app, clock):
    app = relay_app
    app._resume = {"url": f"{BASE}/yt/abc.m4a", "content_type": "audio/mp4", "title": "Song", "position": 1}
    app._say_gen = 3
    app.transport.fake.deliver("online", "false")
    asyncio.run(app.resume_after_announcement(3, f"{BASE}/tts.mp3"))
    assert app._resume is None


def test_queue_advances_when_relay_reports_finished(relay_app, client, relay, clock, monkeypatch):
    app = relay_app
    for vid in ("aaaaaaaaaaa", "bbbbbbbbbbb"):
        (app.CACHE_DIR / f"{vid}.m4a").write_bytes(b"audio")
    pl = app.db.create_playlist("Mix")
    for vid in ("aaaaaaaaaaa", "bbbbbbbbbbb"):
        app.db.add_item(pl["id"], {"kind": "youtube", "source": vid, "title": vid, "duration": 1.0,
                                   "thumbnail": None, "lang": None}, 100)
    assert client.post(f"/playlists/{pl['id']}/play", json={}).status_code == 200
    first = [c for c in app.transport.fake.commands() if c["cmd"] == "play"][-1]
    assert "/yt/aaaaaaaaaaa.m4a" in first["url"]
    relay.finish()
    clock.now += 5
    asyncio.run(app.queue_tick())
    second = [c for c in app.transport.fake.commands() if c["cmd"] == "play"][-1]
    assert "/yt/bbbbbbbbbbb.m4a" in second["url"] and app._queue.pos == 1


def test_status_shows_relay_to_admins_only(relay_app, client, as_role):
    body = client.get("/status").json()
    relay = body["relay"]
    assert relay["transport"] == "mqtt" and relay["online"] and relay["broker_connected"]
    assert body["ip"] == "192.0.2.20" and body["volume"] == 0.3
    assert "relay" not in as_role("viewer").get("/status").json()
    assert "relay" not in as_role("operator").get("/status").json()
    assert as_role("admin").get("/status").json()["relay"]["online"]


def test_status_while_relay_offline(relay_app, client, as_role):
    relay_app.transport.fake.deliver("online", "false")
    r = client.get("/status")
    assert r.status_code == 503 and "offline" in r.json()["detail"]
    assert r.json()["relay"]["online"] is False
    r = as_role("viewer").get("/status")
    assert r.status_code == 503 and "relay" not in r.json()


def test_cast_status_has_no_relay(client):
    assert client.get("/status").json()["relay"] is None


# --- Settings ---

def test_mqtt_transport_needs_a_host(app):
    with pytest.raises(ValueError, match="mqtt.host"):
        app.Settings(transport="mqtt")
    s = app.Settings(transport="mqtt", mqtt={"host": " broker.example.com "})
    assert s.mqtt.host == "broker.example.com" and s.mqtt.port == 8883 and s.mqtt.tls


@pytest.mark.parametrize("topic", ["", "/", "relay/+", "relay/#"])
def test_base_topic_rejects_wildcards(app, topic):
    with pytest.raises(ValueError):
        app.MqttSettings(base_topic=topic)


def test_base_topic_is_trimmed(app):
    assert app.MqttSettings(base_topic="/speaker-relay/x/").base_topic == "speaker-relay/x"


@pytest.mark.parametrize("bad", ["speaker.example.com", "ftp://speaker.example.com", "https://", "https://x/?a=1"])
def test_public_base_url_validation(app, bad):
    with pytest.raises(ValueError, match="public_base_url"):
        app.Settings(public_base_url=bad)


def test_public_base_url_normalized(app):
    assert app.Settings(public_base_url="https://speaker.example.com/ ").public_base_url == \
        "https://speaker.example.com"
    assert app.Settings(public_base_url="").public_base_url is None


def test_media_urls_use_public_base_url(app):
    app.settings = app.Settings(public_base_url="https://speaker.example.com", api_token=TOKEN)
    assert app.media_url("/tts.mp3", text="x").startswith("https://speaker.example.com/tts.mp3?")


def test_reconnect_bounds_validated(app):
    with pytest.raises(ValueError, match="reconnect_max"):
        app.MqttSettings(reconnect_min=30, reconnect_max=5)


def test_password_is_never_in_repr_or_public_settings(app):
    s = app.Settings(transport="mqtt", mqtt={"host": "broker.example.com", "password": "change-me"})
    assert "change-me" not in repr(s)
    public = app.public_settings(s)
    assert "change-me" not in json.dumps(public) and public["mqtt"]["password_set"] is True
    assert "api_token" not in public


def test_env_overrides_apply_but_are_not_saved(app, monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"api_token": TOKEN, "mqtt": {"username": "from-file"}}))
    monkeypatch.setattr(app, "CONFIG_PATH", cfg)
    env = {"SPEAKER_TRANSPORT": "mqtt", "MQTT_HOST": "broker.example.com", "MQTT_PORT": "8884",
           "MQTT_USERNAME": "from-env", "MQTT_PASSWORD": "env-secret", "PUBLIC_BASE_URL": "https://speaker.example.com",
           "MQTT_TLS": ""}
    s = app.load_settings(env)
    assert s.transport == "mqtt" and s.mqtt.host == "broker.example.com" and s.mqtt.port == 8884
    assert s.mqtt.username == "from-env" and s.mqtt.password == "env-secret" and s.mqtt.tls is True
    s.default_volume = 0.5
    app.save_settings(s, env)
    saved = json.loads(cfg.read_text())
    assert "env-secret" not in cfg.read_text() and "password" not in saved["mqtt"]
    assert saved["mqtt"]["username"] == "from-file" and "host" not in saved["mqtt"]
    assert "transport" not in saved and saved["default_volume"] == 0.5


def test_settings_api_merges_mqtt_and_masks_password(client, app, monkeypatch):
    built = []

    def fake_make(s):
        built.append(s.transport)
        return SimpleNamespace(start=lambda: None, close=lambda: None, kind=s.transport,
                               relay_status=lambda: None)

    monkeypatch.setattr(app, "make_transport", fake_make)
    r = client.post("/settings", json={"transport": "mqtt", "mqtt": {"host": "broker.example.com",
                                                                    "password": "api-secret"}})
    assert r.status_code == 200, r.text
    assert built == ["mqtt"] and app.transport.kind == "mqtt"
    assert "api-secret" not in r.text and r.json()["settings"]["mqtt"]["password_set"]
    r = client.post("/settings", json={"mqtt": {"port": 8884}})
    assert r.status_code == 200 and app.settings.mqtt.password == "api-secret"  # partial update kept it
    assert app.settings.mqtt.host == "broker.example.com"
    log = json.dumps(client.get("/activity").json())
    assert "api-secret" not in log and "mqtt.password=***" in log
    assert client.post("/settings", json={"mqtt": {"base_topic": "a/#"}}).status_code == 422
    assert client.post("/settings", json={"transport": "mqtt", "mqtt": {"host": ""}}).status_code == 422
    assert client.post("/settings", json={"default_volume": 0.3}).status_code == 200
    assert built == ["mqtt", "mqtt"]  # unrelated changes don't rebuild the transport
