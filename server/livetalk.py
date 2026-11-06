"""Live talk through the speaker (WebSocket /talk): the session, the speaker hand-over and the clean-up."""
import asyncio
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field

from fastapi import HTTPException

from server import config, core, playback, talk
from server.access import Principal, base_url, media_url, record
from server.auth import ROLE_RANK, token_hash
from server.config import SESSION_COOKIE, TALK_DRAIN
from server.speaker import cast_play, run_cast

# --- Live talk (WebSocket /talk) ---
#
# Protocol (JSON text frames unless noted):
#   client -> {"type": "start", "mime": MediaRecorder.mimeType, "chime": bool, "volume": 0-1 | null}
#   server -> {"type": "ready", "id", "max_seconds", "format"}   then the client sends binary recorder chunks
#   server -> {"type": "live"}                                    the speaker has loaded the live stream
#   client -> {"type": "stop"} | {"type": "ping"}  (server answers a ping with {"type": "pong"})
#   server -> {"type": "ended", "reason", "seconds", "detail"?}  and closes (1000)
#   server -> {"type": "error", "code", "detail"}                 and closes (44xx / 4503) instead of starting
# One talker at a time. Music pauses for the talk and resumes after it, as after an announcement.

TALK_CLOSE = {"bad_request": 4400, "unauthorized": 4401, "forbidden": 4403, "busy": 4409, "unavailable": 4503}

talk_transcoder = talk.FfmpegTranscoder  # replaced by a fake in tests
talk_available = talk.ffmpeg_available


@dataclass
class TalkSession:
    id: str
    who: Principal
    chime: bool
    volume: float | None
    transcoder: object
    live_url: str
    stream: talk.LiveStream = field(default_factory=talk.LiveStream)
    gen: int | None = None  # _say_gen once the talk has taken over the speaker
    end_reason: str | None = None  # set by a helper task that wants the talk to end
    detail: str | None = None
    first_chunk: float | None = None
    last_chunk: float | None = None
    received: int = 0
    ended_at: float | None = None

    @property
    def seconds(self):
        return self.last_chunk - self.first_chunk if self.first_chunk is not None else 0.0


_talk: TalkSession | None = None  # the talk in progress
_talk_last: TalkSession | None = None  # the previous one, whose stream the speaker may still be reading
_talk_on_speaker: TalkSession | None = None  # owns the speaker from its start until the music is back


class TalkSender:
    """Sends from the talk loop and its helper tasks one at a time; a closed socket is ignored."""

    def __init__(self, ws):
        self.ws, self.lock = ws, asyncio.Lock()

    async def __call__(self, message):
        async with self.lock:
            try:
                await self.ws.send_json(message)
            except Exception:  # the client is gone (the exception type depends on the server)
                pass


async def talk_refuse(ws, code, detail):
    try:
        await ws.send_json({"type": "error", "code": code, "detail": detail})
        await ws.close(TALK_CLOSE[code], reason=code)
    except Exception:  # the client is gone
        pass


def ws_caller(ws):
    """(Principal, None), or (None, (error code, detail)) for a WebSocket that isn't signed in.

    Browsers can't set headers on a WebSocket, so the session cookie authenticates and the Origin
    check stands in for the X-Requested-With header; scripts may send the API token instead.
    """
    origin = ws.headers.get("origin")
    if origin:
        allowed = {ws.headers.get("host", "")}
        if config.settings.public_base_url:
            allowed.add(urllib.parse.urlsplit(config.settings.public_base_url).netloc)
        if urllib.parse.urlsplit(origin).netloc not in allowed:
            return None, ("forbidden", "Cross-site connection refused")
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        if not secrets.compare_digest(auth[7:].strip().encode(), config.settings.api_token.encode()):
            return None, ("unauthorized", "Missing or invalid API token")
        who = Principal("admin", "api-token")
    else:
        sid = ws.cookies.get(SESSION_COOKIE)
        user = core.db.session_user(token_hash(sid))[0] if sid else None
        if user is None:
            return None, ("unauthorized", "Not signed in")
        who = Principal(user["role"], user["display_name"], user, token_hash(sid))
    return who, None


def talk_caller(ws):
    """(Principal, None), or (None, (error code, detail)) for a connection that may not talk live."""
    who, problem = ws_caller(ws)
    if who is not None and ROLE_RANK[who.role] < ROLE_RANK["operator"]:
        return None, ("forbidden", "Live talk needs the operator role")
    return who, problem


def parse_talk_start(message):
    """(input format, chime, volume) from the start message; ValueError with a readable reason."""
    if message.get("type") != "websocket.receive" or message.get("text") is None:
        raise ValueError("Send a start message (JSON text) first")
    try:
        start = json.loads(message["text"])
    except ValueError:
        raise ValueError("The start message is not JSON") from None
    if not isinstance(start, dict) or start.get("type") != "start":
        raise ValueError('The first message must be {"type": "start", ...}')
    fmt = talk.input_format(start.get("mime") if isinstance(start.get("mime"), str) else "")
    if fmt is None:
        raise ValueError(f"Unsupported recording format; use one of {', '.join(sorted(talk.INPUT_FORMATS))}")
    volume = start.get("volume")
    if volume is not None and (isinstance(volume, bool) or not isinstance(volume, (int, float))
                               or not 0 <= volume <= 1):
        raise ValueError("volume must be between 0 and 1")
    return fmt, bool(start.get("chime")), volume


async def run_talk(ws, session, send):
    """Run one talk from ffmpeg start to clean-up; every path ends with ffmpeg gone and the stream closed."""
    global _talk, _talk_last, _talk_on_speaker
    pump = speaker = None
    started = False
    try:
        await session.transcoder.start()
        started = True
        pump = asyncio.create_task(talk_pump(session))
        await send({"type": "ready", "id": session.id, "max_seconds": config.settings.talk_max_seconds,
                    "format": "audio/mpeg"})
        _talk_on_speaker = session
        speaker = asyncio.create_task(talk_start_speaker(session, send))
        session.end_reason = await talk_receive(ws, session, send)
    except talk.TranscoderError as e:
        session.end_reason, session.detail = "transcoder_error", str(e)
    finally:
        _talk, _talk_last = None, session  # the next talker may start while this one winds down
        try:
            await end_talk(ws, session, send, speaker, pump, started)
        except asyncio.CancelledError:  # server shutting down mid clean-up: at least stop ffmpeg
            session.transcoder.kill()
            if _talk_on_speaker is session:
                _talk_on_speaker = None
            raise


async def end_talk(ws, session, send, speaker, pump, started):
    """Stop ffmpeg, close the stream, log, hand the speaker back and tell the client how it ended."""
    global _talk_on_speaker
    if speaker is not None:
        await asyncio.wait({speaker}, timeout=config.TALK_SPEAKER_WAIT)
        speaker.cancel()
    await session.transcoder.finish(TALK_DRAIN)
    if pump is not None:
        await asyncio.wait({pump}, timeout=TALK_DRAIN)
        pump.cancel()
    await session.stream.close()
    session.ended_at = time.monotonic()
    reason = session.end_reason or "disconnected"
    if started:
        suffix = "" if reason in ("stopped", "disconnected") else f" ({reason.replace('_', ' ')})"
        record(session.who, "talk", f"Talked live for {talk.format_seconds(session.seconds)}{suffix}")
    if session.gen is not None and session.gen == playback._say_gen:
        core.spawn(talk_finish_on_speaker(session))
    elif _talk_on_speaker is session:
        _talk_on_speaker = None
    ended = {"type": "ended", "reason": reason, "seconds": round(session.seconds, 1)}
    await send(ended | ({"detail": session.detail} if session.detail else {}))
    try:
        await ws.close(1000)
    except Exception:  # already closed by the client
        pass


async def talk_receive(ws, session, send):
    """Feed recorder chunks to ffmpeg until the talk should end; returns the reason."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + config.settings.talk_max_seconds
    last_audio = loop.time()
    pending = None
    try:
        while True:
            if session.end_reason:
                return session.end_reason
            if session.gen is not None and session.gen != playback._say_gen:
                return "interrupted"  # something else was played or announced
            now = loop.time()
            if now >= deadline:
                return "max_length"
            if now - last_audio >= config.TALK_IDLE_TIMEOUT:
                return "idle"
            if pending is None:
                pending = asyncio.ensure_future(ws.receive())
            done, _ = await asyncio.wait({pending}, timeout=min(config.TALK_TICK, deadline - now))
            if not done:
                continue
            message, pending = pending.result(), None
            if message["type"] == "websocket.disconnect":
                return "disconnected"
            if message.get("bytes"):
                chunk = message["bytes"]
                last_audio = loop.time()
                if session.first_chunk is None:
                    session.first_chunk = last_audio
                session.last_chunk = last_audio
                session.received += len(chunk)
                if session.received > config.TALK_MAX_RATE * config.settings.talk_max_seconds:
                    return "too_large"
                await session.transcoder.write(chunk)
            elif message.get("text"):
                try:
                    kind = json.loads(message["text"]).get("type")
                except (ValueError, AttributeError):
                    kind = None
                if kind == "stop":
                    return "stopped"
                if kind == "ping":
                    await send({"type": "pong"})
    finally:
        if pending is not None:
            pending.cancel()


async def talk_pump(session):
    """Move ffmpeg's MP3 output into the live stream until ffmpeg exits."""
    while chunk := await session.transcoder.read():
        await session.stream.append(chunk)


async def wait_until_idle(gen, url, timeout):
    """Poll until the speaker has finished `url`, moved on to something else, or `timeout` has passed."""
    loop = asyncio.get_running_loop()
    deadline, seen = loop.time() + timeout, False
    while loop.time() < deadline and gen == playback._say_gen:
        m = await run_cast(core.transport.media)
        if m.content_id == url:
            seen = True
            if m.player_state == "IDLE":
                return
        elif seen:
            return
        await asyncio.sleep(config.TALK_POLL)


async def talk_start_speaker(session, send):
    """Take over the speaker like an announcement: remember the music, optional chime, then the live stream."""
    try:
        if config.settings.resume_after_say:
            playback._resume = await run_cast(playback.capture_youtube) or playback._resume
        q = playback._queue
        if q is not None:
            q.after_say = playback._resume is None and await run_cast(playback.queue_after_say, q)
        playback._say_gen += 1
        session.gen = gen = playback._say_gen
        if session.chime:
            chime = media_url("/talk/chime.wav", tone="start")
            await run_cast(cast_play, chime, "audio/wav", "Chime", session.volume)
            await wait_until_idle(gen, chime, config.TALK_CHIME_WAIT)
            if gen != playback._say_gen:
                return
        await run_cast(cast_play, session.live_url, "audio/mpeg", f"Live: {session.who.actor}", session.volume,
                       live=True)
        await send({"type": "live"})
    except HTTPException as e:
        session.end_reason, session.detail = "speaker_error", str(e.detail)


async def talk_finish_on_speaker(session):
    """After a talk: let the speaker play out the stream, closing chime, then resume the interrupted music."""
    global _talk_on_speaker
    gen = session.gen
    try:
        if session.chime:
            await wait_until_idle(gen, session.live_url, config.TALK_END_WAIT)
            if gen != playback._say_gen:
                return
            await run_cast(cast_play, media_url("/talk/chime.wav", tone="end"), "audio/wav", "Chime",
                           session.volume)
        if playback._resume and gen == playback._say_gen:
            await playback.resume_after_announcement(gen, f"{base_url()}/talk/")
        elif playback._queue is not None and playback._queue.after_say and gen == playback._say_gen:
            await wait_until_idle(gen, session.live_url, config.TALK_END_WAIT)  # then queue_tick moves the queue on
    except HTTPException as e:
        print(f"talk: {e.detail}")
    finally:
        if _talk_on_speaker is session:
            _talk_on_speaker = None
