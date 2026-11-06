"""HTTP service that makes a Google Cast speaker announce text and play YouTube audio, internet radio,
podcast episodes and uploaded audio files.

The speaker fetches every stream from this service (TTS and YouTube are proxied). The service
drives the speaker directly over Cast on the LAN, or through the ESP32 relay (firmware/) over MQTT
when it runs elsewhere; see transport.py. Media URLs then go out under `public_base_url`.

Operators can also talk through the speaker live from the browser's microphone (WebSocket /talk, see talk.py),
and every member can use the Talkie, a walkie-talkie between the app's members (WebSocket /talkie).

Callers authenticate with either `Authorization: Bearer <api_token>` (acts as admin) or the
`sid` session cookie of a web account (admin, operator or viewer). The speaker cannot send
headers, so the media URLs handed to it are signed with an HMAC of the token instead.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import server.routes  # noqa: F401 - registers every endpoint on the routers below, in a fixed order
from server import config, core, livetalk, schedules, talkie
from server.access import admin_api, operator_api, public_api, viewer_api
from server.config import readable_errors
from server.speaker import reset_reachability
from server.version import __version__
from server.webui import AppStatic


@asynccontextmanager
async def lifespan(_app):
    core.transport.start()  # the mqtt transport connects to the broker here; cast connects on first use
    runner = asyncio.create_task(schedules.schedule_loop())
    try:
        yield
    finally:
        runner.cancel()
        reset_reachability()
        for session in (livetalk._talk, talkie._talkie,
                        *(c.talk for c in talkie._talkie_conns if c.talk is not talkie._talkie)):
            if session is not None:
                session.transcoder.kill()  # never leave an ffmpeg behind
        core.transport.close()


app = FastAPI(title="Speaker Service", version=__version__, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Keep `detail` a readable string, like every other error."""
    return JSONResponse({"detail": readable_errors(exc.errors())}, status_code=422)


# Endpoints without a role guard first, then the static files, then the role-guarded routers (same order as when
# they were all registered here).
app.include_router(public_api)
app.mount("/static", AppStatic(directory=config.STATIC_DIR), name="static")

for router in (viewer_api, operator_api, admin_api):
    app.include_router(router)


def main():
    import uvicorn

    # No access log: its lines carry client addresses and full query strings (signed media links, searches).
    # Errors and the app's own messages still go to stdout/stderr.
    uvicorn.run(app, host="0.0.0.0", port=config.settings.port, access_log=False)
