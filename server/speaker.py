"""Speaker commands, one at a time, failing fast while the speaker is known to be unreachable."""
import asyncio

from fastapi import HTTPException

from server import config, core
from server.config import TTS_CHUNK
from server.transport import SPEAKER_ERRORS, UNREACHABLE_ERRORS, TransportError

# --- Speaker ---

def cast_play(url, content_type, title=None, volume=None, current_time=None, keep_volume=False, live=False):
    if volume is None and not keep_volume:
        volume = config.settings.default_volume
    core.transport.play(url, content_type, title, volume, current_time, live=live)


# --- Speaker reachability ---
# A connect attempt to a dead speaker takes ~10 s (Cast) or command_timeout (relay). Without a breaker every
# command and every tab's /status poll would pay that in turn behind cast_lock, so after an unreachable error the
# speaker counts as offline: calls fail at once with the last error while a background probe retries it.

OFFLINE_HOLD = 30.0  # fail fast for this long after an unreachable error; each failed probe renews it
PROBE_INTERVAL = 3.0  # pause between background attempts while the speaker is offline
STATUS_TTL = 1.0  # /status polls this close together share one read of the speaker

_offline = None  # {"until": loop time, "detail": message of the last unreachable error} while known offline
_probe = None  # the background task retrying an offline speaker
_status_cache = None  # (loop time, (ReceiverState, MediaState)) from the last /status read
_status_flight = None  # the /status read in progress, awaited by every concurrent poll
_transport_gen = 0  # bumped when settings replace the transport: a call still on the old one changes nothing


def speaker_error_detail(e):
    if isinstance(e, TransportError):
        return str(e)
    return f"Speaker {config.settings.speaker_ip} is not responding ({type(e).__name__}); is it on the same network?"


def fail_fast():
    """Raise the last error at once while the speaker is known to be offline."""
    if _offline is not None and asyncio.get_running_loop().time() < _offline["until"]:
        raise HTTPException(503, _offline["detail"])


def mark_offline(detail):
    global _offline
    _offline = {"until": asyncio.get_running_loop().time() + OFFLINE_HOLD, "detail": detail}
    ensure_probe()


def mark_online():
    global _offline
    if _offline is not None:
        print("speaker reachable again")
    _offline = None


def reset_reachability():
    """Forget what we knew about the speaker (the transport was replaced, or the app is shutting down)."""
    global _offline, _status_cache, _probe
    _offline = _status_cache = None
    if _probe is not None:
        _probe.cancel()
        _probe = None


def ensure_probe():
    global _probe
    if _probe is None or _probe.done():
        _probe = core.spawn(probe_speaker())


async def probe_speaker():
    """Retry an offline speaker in the background so a recovery is noticed within ~PROBE_INTERVAL."""
    while _offline is not None:
        await asyncio.sleep(PROBE_INTERVAL)
        async with core.cast_lock:
            if _offline is None:
                break  # a command got through meanwhile
            try:
                await call_speaker(core.transport.media)
            except HTTPException:
                pass  # still offline; call_speaker renewed the hold


async def call_speaker(fn, *args, **kwargs):
    """Run a blocking transport call in a worker thread and keep track of reachability. Hold cast_lock."""
    gen = _transport_gen
    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)
    except SPEAKER_ERRORS as e:
        detail = speaker_error_detail(e)
        if isinstance(e, UNREACHABLE_ERRORS) and gen == _transport_gen:
            mark_offline(detail)
        raise HTTPException(503, detail) from e
    if gen == _transport_gen:
        mark_online()
    return result


async def run_cast(fn, *args, **kwargs):
    """Run a speaker command, one at a time. Fails at once (503) while the speaker is known to be offline."""
    global _status_cache
    fail_fast()
    async with core.cast_lock:
        fail_fast()  # the call we queued behind may just have found it offline
        try:
            return await call_speaker(fn, *args, **kwargs)
        finally:
            _status_cache = None  # the command may have changed what /status shows


async def speaker_state():
    """(receiver, media) for /status. Polls from many tabs share one read in flight, and reuse it for STATUS_TTL
    seconds, so they never queue up one connect timeout each in front of a user's command."""
    global _status_flight
    now = asyncio.get_running_loop().time()
    if _status_cache is not None and now - _status_cache[0] < STATUS_TTL:
        return _status_cache[1]
    fail_fast()
    if _status_flight is None:
        _status_flight = asyncio.ensure_future(_read_speaker_state())
        _status_flight.add_done_callback(lambda f: f.cancelled() or f.exception())  # never "unretrieved"
    return await asyncio.shield(_status_flight)  # a poll that hangs up mustn't cancel the others' read


async def _read_speaker_state():
    global _status_cache, _status_flight
    try:
        async with core.cast_lock:
            fail_fast()
            gen = _transport_gen
            state = await call_speaker(lambda: (core.transport.receiver(), core.transport.media()))
            if gen == _transport_gen:
                _status_cache = (asyncio.get_running_loop().time(), state)
            return state
    finally:
        _status_flight = None


def split_text(text, size=TTS_CHUNK):
    chunks, current = [], ""
    for word in text.split():
        while len(word) > size:  # Thai has no spaces, so long runs need a hard cut
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:size])
            word = word[size:]
        if len(current) + len(word) + 1 > size:
            chunks.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        chunks.append(current)
    return chunks
