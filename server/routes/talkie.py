"""Talkie endpoints: the /talkie WebSocket, live audio and kept clips."""
import time
from pathlib import Path

from fastapi import HTTPException, WebSocket
from fastapi.responses import FileResponse, StreamingResponse

from server import config, core, talk, talkie
from server.access import Who, public_api, record, viewer_api
from server.accounts import account_of
from server.livetalk import TalkSender, talk_refuse
from server.talkie import (
    TalkieConn,
    _talkie_conns,
    talkie_broadcast,
    talkie_caller,
    talkie_clips,
    talkie_cutoff,
    talkie_end,
    talkie_live_view,
    talkie_loop,
    talkie_online,
    talkie_presence,
)

# --- Talkie (WebSocket /talkie): a walkie-talkie between the members of this server ---

@public_api.websocket("/talkie")
async def talkie_socket(ws: WebSocket):
    await ws.accept()
    who, problem = talkie_caller(ws)
    if problem:
        await talk_refuse(ws, *problem)
        return
    conn = TalkieConn(ws, who, TalkSender(ws), room={"0": False, "1": True}.get(ws.query_params.get("room")))
    before = talkie_online()
    hello = {"type": "hello", "me": conn.user_id, "live": talkie_live_view(conn), "clips": talkie_clips()}
    _talkie_conns.append(conn)
    # no await between joining and this send: it takes the sender's lock first, so broadcasts queue behind it
    sent = conn.send(hello | {"online": talkie_online()})
    try:
        await sent
        await talkie_presence(before, skip=conn)
        await talkie_loop(conn)
    finally:
        before = talkie_online()
        _talkie_conns.remove(conn)
        if conn.talk is not None:
            await talkie_end(conn.talk, "disconnected")
        await talkie_presence(before)


@viewer_api.get("/talkie/live/{talk_id}")
async def talkie_live(talk_id: str, who: Who):
    """A Talkie talk's MP3 from its start, as one response that ends when the talk does (a plain <audio> plays it).
    Only for a member in the room, from any of their tabs."""
    session = talkie._talkie if talkie._talkie is not None and talkie._talkie.id == talk_id else talkie._talkie_last
    recent = session is not None and (session.ended_at is None
                                      or time.monotonic() - session.ended_at < config.TALK_GRACE)
    if not recent or session.id != talk_id:
        raise HTTPException(404, "No such live talk")
    if who.user is None or not any(c.user_id == who.user["id"] and c.in_room for c in _talkie_conns):
        raise HTTPException(403, "Open the Walkie to listen")
    return StreamingResponse(session.stream.follow(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@viewer_api.get("/talkie/clips")
async def list_talkie_clips():
    """The last day's Talkie clips, newest first."""
    return talkie_clips()


@viewer_api.get("/talkie/clips/{clip_id}.mp3")
async def talkie_clip_file(clip_id: str):
    clip = core.db.get_clip(clip_id)
    path = config.TALKIE_DIR / Path(clip["file"]).name if clip else None
    if clip is None or clip["created_at"] < talkie_cutoff() or not path.is_file():
        raise HTTPException(404, "No such clip")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


@viewer_api.delete("/talkie/clips/{clip_id}", status_code=204)
async def delete_talkie_clip(clip_id: str, who: Who):
    """Delete a Talkie message of your own (only its author may: not even the owner deletes others')."""
    user = account_of(who)
    clip = core.db.get_clip(clip_id)
    if clip is None or clip["created_at"] < talkie_cutoff():
        raise HTTPException(404, "No such clip")
    if clip["user_id"] != user["id"]:
        raise HTTPException(403, "Only the member who recorded a message may delete it")
    if not core.db.delete_clip(clip_id):
        raise HTTPException(404, "No such clip")  # deleted meanwhile
    (config.TALKIE_DIR / Path(clip["file"]).name).unlink(missing_ok=True)
    await talkie_broadcast({"type": "clip_deleted", "id": clip_id})
    record(who, "message delete", f"Talkie message of {talk.format_seconds(clip['seconds'])}")
