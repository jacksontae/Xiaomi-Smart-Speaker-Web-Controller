"""Live talk endpoints: the /talk WebSocket and its status."""
import asyncio
import secrets

from fastapi import WebSocket

from server import config, livetalk
from server.access import media_url, operator_api, public_api
from server.livetalk import TalkSender, TalkSession, parse_talk_start, run_talk, talk_caller, talk_refuse

# --- Live talk (WebSocket /talk) ---

@public_api.websocket("/talk")
async def talk_socket(ws: WebSocket):
    await ws.accept()  # accept first: a refused handshake hides the reason from the browser
    who, problem = talk_caller(ws)
    if problem:
        await talk_refuse(ws, *problem)
        return
    try:
        message = await asyncio.wait_for(ws.receive(), config.TALK_START_TIMEOUT)
    except TimeoutError:
        await talk_refuse(ws, "bad_request", "No start message within 10 seconds")
        return
    if message["type"] == "websocket.disconnect":
        return
    try:
        fmt, chime, volume = parse_talk_start(message)
    except ValueError as e:
        await talk_refuse(ws, "bad_request", str(e))
        return
    if not livetalk.talk_available():
        await talk_refuse(ws, "unavailable", "Live talk needs ffmpeg on the server, and it isn't installed")
        return
    if livetalk._talk is not None:
        await talk_refuse(ws, "busy", f"{livetalk._talk.who.actor} is talking right now")
        return
    talk_id = secrets.token_urlsafe(9)
    livetalk._talk = TalkSession(talk_id, who, chime, volume, livetalk.talk_transcoder(fmt),
                                 media_url(f"/talk/{talk_id}/live"))
    await run_talk(ws, livetalk._talk, TalkSender(ws))


@operator_api.get("/talk/status")
async def talk_status():
    """Whether live talk works on this server (ffmpeg installed) and who is talking."""
    active = livetalk._talk and {"by": livetalk._talk.who.actor, "id": livetalk._talk.id}
    return {"available": livetalk.talk_available(), "max_seconds": config.settings.talk_max_seconds, "active": active}
