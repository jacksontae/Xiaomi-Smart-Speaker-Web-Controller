"""Talkie, a walkie-talkie between the members (WebSocket /talkie): connections, talks and kept clips."""
import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import WebSocket

from server import config, core, livetalk, talk
from server.access import Principal
from server.config import TALK_DRAIN, TALKIE_KEEP, TALKIE_SWEEP, utc_iso
from server.livetalk import TalkSender, talk_pump, talk_refuse, ws_caller

# --- Talkie (WebSocket /talkie): a walkie-talkie between the members of this server ---
#
# One room for everyone. The web app keeps the socket open on every page while signed in: it carries who has the
# app open, and the talks. A talk is one of two modes:
#   walkie   live only: streamed to the members in the room, kept nowhere. One talker at a time (its own lock: the
#            speaker's /talk is separate). Listeners play GET /talkie/live/{id}, an MP3 stream of the talk as it is
#            spoken.
#   message  kept only: never live, takes no lock (several members may record at once), kept as a clip for a day.
# A start must say its mode (the app before the modes, which sent none, never shipped).
# "In the room" is a connection whose app has the Walkie open (it says so with "room"; one that never said counts
# as in, as before the room). Only they get the live audio and may start a walkie talk; everyone hears who talks.
#
# Protocol (JSON text frames unless noted):
#   server -> {"type": "hello", "me", "online": [{id, name, in_room}], "live": {id, user_id, name, url?} | null,
#              "clips": [clip]}                       "url" only for a connection in the room
#   server -> {"type": "online", "online"}             a member came, left, entered or left the room (tabs count once)
#   client -> {"type": "room", "in": true | false}     the Walkie opened or closed (/talkie?room=0|1 sets it at once)
#   client -> {"type": "start", "mime": MediaRecorder.mimeType, "mode": "walkie" | "message"}
#   server -> {"type": "ready", "id", "max_seconds"}   then the client sends binary recorder chunks
#   server -> {"type": "error", "code", "detail"}      instead (busy, not_in_room, bad_request, unavailable,
#                                                      transcoder_error)
#   server -> {"type": "live", "id", "user_id", "name", "url"?}   to everyone else when a live talk starts ("url"
#                                                      only in the room; also to a connection entering the room)
#   client -> {"type": "stop"} | {"type": "ping"}      (a ping is answered with {"type": "pong"})
#   server -> {"type": "ended", "id", "user_id", "reason", "clip": {...} | null}   when a talk ends: to everyone
#                                                      for a live talk, to the talker alone for a message
#   server -> {"type": "clip", "clip"}                 to everyone when a talk is kept
#   server -> {"type": "clip_deleted", "id"}           to everyone when its author deleted it (DELETE
#                                                      /talkie/clips/{id})
# A talk ends on stop, after TALKIE_MAX_SECONDS, when the audio stops coming, when its talker's socket closes or (a
# walkie talk) leaves the room. Talks under TALKIE_MIN_SECONDS keep no clip. A refused connection gets an error
# frame and is closed (44xx), as /talk. Only deletes go to the activity log: the rest is chat.

TALKIE_MODES = {"walkie": (True, False), "message": (False, True)}  # mode -> (live, kept)


@dataclass(eq=False)
class TalkieConn:
    """One open /talkie socket (a member may have several: tabs, devices)."""
    ws: WebSocket
    who: Principal
    send: TalkSender
    room: bool | None = None  # the app said its Walkie is open (True) or not (False); None: never said
    talk: "TalkieTalk | None" = None  # its own talk in progress, of either mode

    @property
    def user_id(self):
        return self.who.user["id"]

    @property
    def in_room(self):
        return self.room is not False


@dataclass(eq=False)
class TalkieTalk:
    id: str
    conn: TalkieConn
    transcoder: object
    live: bool = True  # streamed to the room (and holds the one-talker lock)
    kept: bool = True  # saved as a clip when it ends
    # the whole talk stays readable: a listener who joins late hears it from the start
    stream: talk.LiveStream = field(default_factory=lambda: talk.LiveStream(backlog=1 << 30))
    started: float | None = None  # loop time of "ready" (the recorder starts then)
    last_chunk: float | None = None
    received: int = 0
    pump: asyncio.Task | None = None
    ended: bool = False
    ended_at: float | None = None

    @property
    def seconds(self):
        return self.last_chunk - self.started if self.last_chunk is not None else 0.0

    def view(self, audio=True):
        """Who is talking; with the live audio's URL for a connection in the room."""
        user = self.conn.who.user
        view = {"id": self.id, "user_id": user["id"], "name": user["display_name"]}
        return view | {"url": f"/talkie/live/{self.id}"} if audio else view


_talkie_conns: list[TalkieConn] = []
_talkie: TalkieTalk | None = None  # the live talk in progress
_talkie_last: TalkieTalk | None = None  # the previous one, whose stream a slow listener may still be reading
_talkie_swept = 0.0  # monotonic time of the last sweep for old clip files


def talkie_online():
    """Members with the app open, each once, in the order they came; in the room from any of their tabs."""
    seen = {}
    for c in _talkie_conns:
        member = seen.setdefault(c.user_id, {"id": c.user_id, "name": c.who.user["display_name"], "in_room": False})
        member["in_room"] = member["in_room"] or c.in_room
    return list(seen.values())


async def talkie_broadcast(message, skip=None):
    await asyncio.gather(*(c.send(message) for c in list(_talkie_conns) if c is not skip))


async def talkie_presence(before, skip=None):
    """Tell everyone the online list when it differs from `before`."""
    if (online := talkie_online()) != before:
        await talkie_broadcast({"type": "online", "online": online}, skip=skip)


def talkie_live_view(conn):
    return _talkie and _talkie.view(audio=conn.in_room)


def talkie_cutoff():
    return utc_iso(datetime.now(UTC) - TALKIE_KEEP)


def clip_view(clip):
    return {"id": clip["id"], "user_id": clip["user_id"], "name": clip["name"], "seconds": clip["seconds"],
            "created_at": clip["created_at"], "url": f"/talkie/clips/{clip['id']}.mp3"}


def talkie_clips():
    """The last day's clips, newest first."""
    talkie_sweep()
    return [clip_view(c) for c in core.db.list_clips(talkie_cutoff())]


def talkie_sweep(force=False):
    """Delete clips older than TALKIE_KEEP with their files, at most once every TALKIE_SWEEP seconds. Files without
    a row (a member deleted while their clip was being saved) go once they are as old."""
    global _talkie_swept
    now = time.monotonic()
    if not force and _talkie_swept and now - _talkie_swept < TALKIE_SWEEP:
        return
    _talkie_swept = now
    for name in core.db.expire_clips(talkie_cutoff()):
        (config.TALKIE_DIR / name).unlink(missing_ok=True)
    if config.TALKIE_DIR.is_dir():
        old = time.time() - TALKIE_KEEP.total_seconds()
        for path in config.TALKIE_DIR.glob("*.mp3"):
            if path.stat().st_mtime < old:
                path.unlink(missing_ok=True)


def talkie_caller(ws):
    """(Principal, None), or (None, (error code, detail)): any signed-in member, never the API token."""
    who, problem = ws_caller(ws)
    if who is not None and who.user is None:
        return None, ("forbidden", "Talkie is for members signed in to the app")
    return who, problem


def signed_out(conn):
    """The member was signed out, disabled or deleted since the socket opened."""
    return core.db.session_user(conn.who.session)[0] is None


async def talkie_loop(conn):
    """Read the member's messages until the socket closes; audio goes to their talk, timers end it."""
    loop = asyncio.get_running_loop()
    pending = None
    try:
        while True:
            mine = conn.talk
            timeout = None  # nothing to time while the member only listens
            if mine is not None:
                now = loop.time()
                last_audio = mine.last_chunk or mine.started
                if now >= mine.started + config.TALKIE_MAX_SECONDS:
                    await talkie_end(mine, "max_length")
                    continue
                if now - last_audio >= config.TALK_IDLE_TIMEOUT:
                    await talkie_end(mine, "idle")
                    continue
                timeout = min(config.TALK_TICK, mine.started + config.TALKIE_MAX_SECONDS - now)
            if pending is None:
                pending = asyncio.ensure_future(conn.ws.receive())
            done, _ = await asyncio.wait({pending}, timeout=timeout)
            if not done:
                continue
            message, pending = pending.result(), None
            if message["type"] == "websocket.disconnect":
                return
            if message.get("bytes"):
                if mine is not None:
                    await talkie_audio(mine, message["bytes"])
            elif message.get("text"):
                try:
                    msg = json.loads(message["text"])
                    kind = msg.get("type")
                except (ValueError, AttributeError):
                    msg, kind = {}, None
                if kind == "start":
                    await talkie_start(conn, msg)
                elif kind == "stop" and mine is not None:
                    await talkie_end(mine, "stopped")
                elif kind == "room" and isinstance(msg.get("in"), bool):
                    await talkie_room(conn, msg["in"])
                elif kind == "ping":
                    if signed_out(conn):
                        await talk_refuse(conn.ws, "unauthorized", "Not signed in")
                        return
                    await conn.send({"type": "pong"})
    finally:
        if pending is not None:
            pending.cancel()


async def talkie_room(conn, inside):
    """The connection's Walkie opened or closed: it gets the live audio from now on, or no longer talks live."""
    before, was_in = talkie_online(), conn.in_room
    conn.room = inside
    if inside and not was_in and _talkie is not None and _talkie.conn is not conn:
        await conn.send({"type": "live", **_talkie.view()})  # join the talk going on
    if not inside and conn.talk is not None and conn.talk.live:
        await talkie_end(conn.talk, "left_room")
    await talkie_presence(before)


async def talkie_start(conn, msg):
    global _talkie
    if conn.talk is not None:
        return  # already talking
    mode = msg.get("mode")
    if not isinstance(mode, str) or mode not in TALKIE_MODES:
        await conn.send({"type": "error", "code": "bad_request",
                         "detail": f"Missing or unknown mode; use one of {', '.join(sorted(TALKIE_MODES))}"})
        return
    live, kept = TALKIE_MODES[mode]
    fmt = talk.input_format(msg.get("mime") if isinstance(msg.get("mime"), str) else "")
    if fmt is None:
        await conn.send({"type": "error", "code": "bad_request",
                         "detail": f"Unsupported recording format; use one of {', '.join(sorted(talk.INPUT_FORMATS))}"})
        return
    if signed_out(conn):
        await talk_refuse(conn.ws, "unauthorized", "Not signed in")
        return
    if not livetalk.talk_available():
        await conn.send({"type": "error", "code": "unavailable",
                         "detail": "Talkie needs ffmpeg on the server, and it isn't installed"})
        return
    if live and not conn.in_room:
        await conn.send({"type": "error", "code": "not_in_room", "detail": "Open the Walkie to talk live"})
        return
    if live and _talkie is not None:
        await conn.send({"type": "error", "code": "busy",
                         "detail": f"{_talkie.conn.who.user['display_name']} is talking right now"})
        return
    transcoder = livetalk.talk_transcoder(fmt)
    session = conn.talk = TalkieTalk(secrets.token_urlsafe(9), conn, transcoder, live=live, kept=kept)
    if live:
        _talkie = session
    try:
        await session.transcoder.start()
    except talk.TranscoderError as e:
        conn.talk = None
        if _talkie is session:
            _talkie = None
        await conn.send({"type": "error", "code": "transcoder_error", "detail": str(e)})
        return
    session.pump = asyncio.create_task(talk_pump(session))
    session.started = asyncio.get_running_loop().time()
    await conn.send({"type": "ready", "id": session.id, "max_seconds": config.TALKIE_MAX_SECONDS})
    if live:
        await asyncio.gather(*(c.send({"type": "live", **session.view(audio=c.in_room)})
                               for c in list(_talkie_conns) if c is not conn))


async def talkie_audio(session, chunk):
    session.last_chunk = asyncio.get_running_loop().time()
    session.received += len(chunk)
    if session.received > config.TALK_MAX_RATE * config.TALKIE_MAX_SECONDS:
        await talkie_end(session, "too_large")
        return
    try:
        await session.transcoder.write(chunk)
    except talk.TranscoderError as e:
        await session.conn.send({"type": "error", "code": "transcoder_error", "detail": str(e)})
        await talkie_end(session, "transcoder_error")


async def talkie_end(session, reason):
    """Stop ffmpeg, close the stream, keep the clip (unless walkie) and tell who heard of it. Runs once per talk."""
    global _talkie, _talkie_last
    if session.ended:
        return
    session.ended = True
    if session.conn.talk is session:
        session.conn.talk = None
    if _talkie is session:
        _talkie, _talkie_last = None, session  # the next talker may start while this one winds down
    try:
        await session.transcoder.finish(TALK_DRAIN)
        if session.pump is not None:
            await asyncio.wait({session.pump}, timeout=TALK_DRAIN)
            session.pump.cancel()
    finally:
        await session.stream.close()
        session.ended_at = time.monotonic()
    clip = await talkie_save(session) if session.kept else None
    ended = {"type": "ended", "id": session.id, "user_id": session.conn.user_id, "reason": reason, "clip": clip}
    if session.live:
        await talkie_broadcast(ended)
    else:
        await session.conn.send(ended)  # nobody else knew of it
    if clip is not None:
        await talkie_broadcast({"type": "clip", "clip": clip})


async def talkie_save(session):
    """Keep the talk as a clip; None when it was too short (or couldn't be saved)."""
    data = bytes(session.stream.data)
    if session.seconds < config.TALKIE_MIN_SECONDS or not data:
        return None
    name = f"{session.id}.mp3"

    def write():
        config.TALKIE_DIR.mkdir(parents=True, exist_ok=True)
        (config.TALKIE_DIR / name).write_bytes(data)

    try:
        await asyncio.to_thread(write)
        clip = core.db.add_clip(session.id, session.conn.user_id, round(session.seconds, 1), name)
    except Exception as e:  # disk full, or the member was deleted meanwhile
        print(f"talkie: clip not kept: {type(e).__name__}: {e}")
        (config.TALKIE_DIR / name).unlink(missing_ok=True)
        return None
    return clip_view(clip)
