"""How the service reaches the speaker.

- `CastTransport`: talks Cast v2 to the speaker directly with pychromecast (server on the speaker's LAN).
- `MqttRelayTransport`: publishes commands to the ESP32 relay (firmware/) through an MQTT broker and
  rebuilds the speaker state from the relay's results and status messages (server anywhere).

Both expose the same small surface, so app.py (queue, resume-after-announcement, /status) does not
care which one is in use: play / set_volume / pause / resume / stop, media() and receiver().
Methods block; app.py calls them from a worker thread under its cast lock.
"""
import itertools
import json
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import pychromecast
import pychromecast.error
from pychromecast.const import CAST_TYPE_AUDIO
from pychromecast.models import CastInfo, HostServiceInfo

DEFAULT_MEDIA_RECEIVER = "CC1AD845"


class TransportError(Exception):
    """The speaker (or the relay in front of it) can't carry out a command. str() is shown to the caller."""


SPEAKER_ERRORS = (pychromecast.error.PyChromecastError, OSError, TransportError)


@dataclass
class MediaState:
    """What the speaker is playing. Field names follow pychromecast's MediaStatus, which app.py grew up on."""
    content_id: str | None = None
    content_type: str | None = None
    title: str | None = None
    player_state: str = "UNKNOWN"  # PLAYING, BUFFERING, PAUSED, IDLE or UNKNOWN
    idle_reason: str | None = None  # FINISHED, ERROR, CANCELLED, INTERRUPTED
    duration: float | None = None
    current_time: float | None = None  # None when nothing has reported a position
    adjusted_current_time: float = 0.0  # current_time plus the time spent playing since it was reported


@dataclass
class ReceiverState:
    name: str | None = None
    ip: str | None = None
    app: str | None = None
    volume: float | None = None
    muted: bool = False


# --- Direct Cast (LAN) ---

def connect_speaker(ip):
    """Connect without pychromecast's blocking 30 s HTTP probe for the cast type.

    Bounded retries make an unreachable speaker fail in ~10 s instead of hanging;
    when the worker later gives up, get_cast() sees a dead thread and reconnects.
    """
    info = CastInfo({HostServiceInfo(ip, 8009)}, None, None, None, ip, 8009, CAST_TYPE_AUDIO, None)
    return pychromecast.Chromecast(info, tries=2, retry_wait=1, timeout=4)


class CastTransport:
    kind = "cast"

    def __init__(self, ip, name=None):
        self.ip, self.name = ip, name
        self._cast = None

    def start(self):
        pass  # connects lazily on the first command

    def close(self):
        self.drop()

    def get_cast(self):
        if self._cast is not None and not self._cast.socket_client.is_alive():
            self.drop()  # worker thread is gone; pychromecast won't reconnect it
        if self._cast is None:
            self._cast = connect_speaker(self.ip)
            self._cast.wait(timeout=10)
        elif not self._cast.socket_client.is_connected:
            self._cast.wait(timeout=10)  # pychromecast is already reconnecting; let it finish
        return self._cast

    def drop(self):
        if self._cast is not None:
            # Signal the worker to stop without joining: Chromecast.disconnect(timeout=0) raises if it's still alive.
            self._cast.socket_client.disconnect()
            self._cast = None

    def play(self, url, content_type, title=None, volume=None, position=None):
        cast = self.get_cast()
        if volume is not None:
            cast.set_volume(volume)
        # Other apps (e.g. Spotify) ignore LOAD for arbitrary URLs, so switch receivers first.
        if cast.app_id != DEFAULT_MEDIA_RECEIVER:
            cast.start_app(DEFAULT_MEDIA_RECEIVER)
            cast.wait(timeout=10)
        mc = cast.media_controller
        # BUFFERED (not the LIVE default) so the receiver honours current_time and allows seeking.
        mc.play_media(url, content_type, title=title, current_time=position, stream_type="BUFFERED")
        mc.block_until_active(timeout=10)

    def set_volume(self, level):
        self.get_cast().set_volume(level)

    def pause(self):
        self.get_cast().media_controller.pause()

    def resume(self):
        self.get_cast().media_controller.play()

    def stop(self):
        self.get_cast().quit_app()

    def media(self):
        m = self.get_cast().media_controller.status
        return MediaState(
            content_id=m.content_id, content_type=m.content_type, title=m.title, player_state=m.player_state,
            idle_reason=getattr(m, "idle_reason", None), duration=m.duration, current_time=m.current_time,
            adjusted_current_time=m.adjusted_current_time,
        )

    def receiver(self):
        cast = self.get_cast()
        s = cast.status
        return ReceiverState(name=cast.cast_info.friendly_name or self.name, ip=self.ip, app=s.display_name,
                             volume=s.volume_level, muted=s.volume_muted)

    def relay_status(self):
        return None  # no relay in between


# --- ESP32 relay over MQTT ---

def paho_client(cfg):
    """A configured paho-mqtt client (not yet connected). Imported lazily: only the mqtt transport needs it."""
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.client_id or "",
                         protocol=mqtt.MQTTv311)
    if cfg.tls:
        client.tls_set(ca_certs=cfg.ca_file or None)  # None = the system's trusted CAs
    if cfg.username:
        client.username_pw_set(cfg.username, cfg.password or None)
    return client


def _failed(reason_code):
    """paho 2 passes a ReasonCode; plain ints (fakes, MQTT 3 return codes) are failures when non-zero."""
    return bool(getattr(reason_code, "is_failure", reason_code))


class MqttRelayTransport:
    """Drives the speaker through the relay's MQTT topics (see firmware/README.md):

    - commands are published to `<base>/cmd` with an "id"; the relay answers on `<base>/result`
      with {"id", "ok", "error"?, "speaker": {...}};
    - `<base>/status` (retained, every 30 s) carries {"version", "ip", "rssi", "heap", "speaker"};
    - `<base>/online` (retained) is "true", or "false" from the relay's last will.

    The relay counts as online only while our broker session is up, its last will hasn't fired, and
    something arrived from it within `offline_after` seconds (status is every 30 s, so a relay that
    dies without the broker noticing still drops out). Speaker state older than `status_refresh`
    seconds is refreshed with a "status" command before it is used, because the relay only
    publishes status every 30 s and the queue needs to see a track end promptly.
    """
    kind = "mqtt"
    LOADED_MEMORY = 50  # content types remembered for URLs we loaded (the relay doesn't report them)

    def __init__(self, cfg, name=None, client_factory=paho_client, clock=time.monotonic, wall=time.time):
        self.cfg, self.name = cfg, name
        self.base = cfg.base_topic.strip("/")
        self.clock, self.wall = clock, wall
        self._cond = threading.Condition()
        self._prefix = secrets.token_hex(3)  # keeps our ids apart from another server's or an earlier run's
        self._ids = itertools.count(1)
        self._results = {}  # id -> result payload, for commands someone is waiting on
        self._waiting = set()
        self.broker_connected = False
        self._relay_lwt = None  # last value seen on <base>/online
        self._seen_at = self._seen_wall = None  # last sign of life from the relay
        self._speaker = {}  # last "speaker" object from the relay
        self._speaker_at = None  # clock() when _speaker was reported fresh; None = not fresh (e.g. retained)
        self._info = {}  # version, ip, rssi, heap from <base>/status
        self._loaded = OrderedDict()  # url -> content type
        self.client = client_factory(cfg)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        # paho reconnects by itself with exponential backoff between these bounds (also for the first connect).
        self.client.reconnect_delay_set(min_delay=cfg.reconnect_min, max_delay=cfg.reconnect_max)

    def topic(self, leaf):
        return f"{self.base}/{leaf}"

    # --- connection ---

    def start(self):
        self.client.connect_async(self.cfg.host, self.cfg.port, keepalive=self.cfg.keepalive)
        self.client.loop_start()

    def close(self):
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if _failed(reason_code):
            print(f"mqtt: broker refused the connection ({reason_code}); retrying")
            return
        with self._cond:
            self.broker_connected = True
        client.subscribe([(self.topic("status"), 1), (self.topic("result"), 1), (self.topic("online"), 1)])
        print(f"mqtt: connected; relay topics under {self.base}/")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        with self._cond:
            self.broker_connected = False
            self._cond.notify_all()  # waiting commands fail now instead of at their timeout
        print(f"mqtt: disconnected ({reason_code}); reconnecting")

    def _on_message(self, client, userdata, msg):
        leaf = msg.topic.removeprefix(self.base + "/")
        payload = msg.payload.decode("utf-8", "replace").strip()
        with self._cond:
            if leaf == "online":
                self._relay_lwt = payload.lower() == "true"
                if self._relay_lwt:
                    self._alive(retained_ok=True)
                return
            try:
                doc = json.loads(payload)
            except ValueError:
                print(f"mqtt: ignoring non-JSON message on {msg.topic}")
                return
            if not isinstance(doc, dict):
                return
            if leaf == "status":
                self._info = {k: doc.get(k) for k in ("version", "ip", "rssi", "heap")}
                if isinstance(doc.get("speaker"), dict):
                    self._take_speaker(doc["speaker"], fresh=not msg.retain)
                if not msg.retain:
                    self._alive()
            elif leaf == "result":
                self._alive()
                if doc.get("ok") and isinstance(doc.get("speaker"), dict):
                    self._take_speaker(doc["speaker"], fresh=True)
                rid = doc.get("id")
                if rid in self._waiting:
                    self._results[rid] = doc
                    self._cond.notify_all()

    def _alive(self, retained_ok=False):
        """Something arrived from the relay. A retained "online: true" counts once, as a grace period."""
        self._seen_at, self._seen_wall = self.clock(), self.wall()
        if not retained_ok:
            self._relay_lwt = True  # it is talking, so the last will (if any) is out of date

    def _take_speaker(self, speaker, fresh):
        self._speaker = speaker
        self._speaker_at = self.clock() if fresh else None

    @property
    def online(self):
        with self._cond:
            return self._online()

    def _online(self):
        return (self.broker_connected and self._relay_lwt is not False and self._seen_at is not None
                and self.clock() - self._seen_at < self.cfg.offline_after)

    def _offline_error(self):
        if not self.broker_connected:
            return TransportError("Speaker relay unavailable: not connected to the MQTT broker")
        if self._seen_wall is None:
            return TransportError("Speaker relay is offline (never seen)")
        ago = int(self.wall() - self._seen_wall)
        return TransportError(f"Speaker relay is offline (last seen {ago} s ago)")

    # --- commands ---

    def command(self, cmd, timeout=None, **fields):
        """Publish one command and wait for the relay's result. Raises TransportError on any failure."""
        timeout = self.cfg.command_timeout if timeout is None else timeout
        with self._cond:
            if not self._online():
                raise self._offline_error()
            rid = f"{self._prefix}-{next(self._ids)}"
            self._waiting.add(rid)
        try:
            info = self.client.publish(self.topic("cmd"), json.dumps({"cmd": cmd, "id": rid, **fields}), qos=1)
            if getattr(info, "rc", 0):
                raise TransportError(f"Speaker relay unavailable: MQTT publish failed (rc {info.rc})")
            deadline = self.clock() + timeout
            with self._cond:
                while rid not in self._results:
                    left = deadline - self.clock()
                    if left <= 0:
                        raise TransportError(f"Speaker relay did not answer {cmd!r} within {timeout:g} s")
                    if not self.broker_connected:
                        raise TransportError("Speaker relay unavailable: lost the MQTT broker connection")
                    self._cond.wait(min(left, 0.25))  # short slices: re-check the broker link too
                result = self._results.pop(rid)
        finally:
            with self._cond:
                self._waiting.discard(rid)
                self._results.pop(rid, None)
        if not result.get("ok"):
            raise TransportError(f"Speaker relay: {result.get('error') or 'command failed'}")
        return result

    def play(self, url, content_type, title=None, volume=None, position=None):
        fields = {"url": url, "content_type": content_type, "title": title or ""}
        if volume is not None:
            fields["volume"] = volume
        if position:
            fields["position"] = position
        with self._cond:
            self._loaded[url] = content_type
            self._loaded.move_to_end(url)
            while len(self._loaded) > self.LOADED_MEMORY:
                self._loaded.popitem(last=False)
        self.command("play", timeout=self.cfg.play_timeout, **fields)

    def set_volume(self, level):
        self.command("volume", level=level)

    def pause(self):
        self.command("pause")

    def resume(self):
        self.command("resume")

    def stop(self):
        self.command("stop")

    def _fresh_speaker(self):
        with self._cond:
            stale = self._speaker_at is None or self.clock() - self._speaker_at > self.cfg.status_refresh
        if stale:
            self.command("status")
        with self._cond:
            return dict(self._speaker), self._speaker_at

    def media(self):
        speaker, at = self._fresh_speaker()
        m = speaker.get("media") or {}
        url = m.get("content_id") or None
        state = m.get("state") or "UNKNOWN"
        position = m.get("position")
        adjusted = float(position or 0.0)
        if state == "PLAYING" and at is not None:
            adjusted += max(0.0, self.clock() - at)  # the relay's figure was current when it was reported
        with self._cond:
            content_type = self._loaded.get(url)
        return MediaState(
            content_id=url, content_type=content_type, title=m.get("title") or None, player_state=state,
            idle_reason=m.get("idle_reason") or None, duration=None,
            current_time=float(position) if url and position is not None else None,
            adjusted_current_time=adjusted,
        )

    def receiver(self):
        speaker, _ = self._fresh_speaker()
        return ReceiverState(name=self.name, ip=speaker.get("ip") or None, app=speaker.get("app") or None,
                             volume=speaker.get("volume"), muted=bool(speaker.get("muted")))

    def relay_status(self):
        with self._cond:
            seen = self._seen_wall
            return {
                "transport": "mqtt",
                "broker_connected": self.broker_connected,
                "online": self._online(),
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seen)) if seen else None,
                "seconds_since_seen": round(self.wall() - seen, 1) if seen else None,
                "firmware_version": self._info.get("version"),
                "relay_ip": self._info.get("ip"),
                "rssi": self._info.get("rssi"),
                "speaker_connected": self._speaker.get("connected"),
                "speaker_error": self._speaker.get("error"),
                "base_topic": self.base,
            }


def make_transport(settings):
    if settings.transport == "mqtt":
        return MqttRelayTransport(settings.mqtt, name=settings.speaker_name)
    return CastTransport(settings.speaker_ip, name=settings.speaker_name)
