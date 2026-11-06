"""Playlists: shared and personal lists, their items, and playing one."""
import asyncio

from fastapi import HTTPException

from server import config, core
from server.access import Who, operator_api, viewer_api
from server.accounts import can_see, owns, personal_owner, with_rights
from server.auth import ROLE_RANK
from server.config import STATION_UUID_RE, TTS_TEXT_MAX
from server.media import yt_info
from server.playback import guess_audio_type, start_playlist
from server.schemas import ItemBody, NewPlaylistBody, OrderBody, PlaylistBody, PlayPlaylistBody, StationBody, clean_text
from server.sources import audio_type, custom_station, http_url, optional_http_url, radio_station
from server.store import Conflict

# --- Playlists ---

def playlist_or_404(playlist):
    if playlist is None:
        raise HTTPException(404, "No such playlist")
    return playlist


def can_edit_playlist(playlist, who):
    if playlist["owner_id"] is None:
        return ROLE_RANK[who.role] >= ROLE_RANK["operator"]
    return who.role == "admin" or owns(playlist, who)


def visible_playlist(playlist_id, who):
    """The playlist if the caller may see it, else 404 (someone else's personal one looks missing)."""
    playlist = core.db.get_playlist(playlist_id)
    if playlist is None or not can_see(playlist, who):
        raise HTTPException(404, "No such playlist")
    return playlist


def editable_playlist(playlist_id, who):
    playlist = visible_playlist(playlist_id, who)
    if not can_edit_playlist(playlist, who):
        raise HTTPException(403, "Shared playlists need the operator role to change")
    return playlist


def playlist_view(playlist, who):
    return with_rights(playlist_or_404(playlist), who, can_edit_playlist)


@viewer_api.get("/playlists")
async def list_playlists(who: Who):
    return [playlist_view(p, who) for p in core.db.list_playlists() if can_see(p, who)]


@viewer_api.post("/playlists")
async def create_playlist(body: NewPlaylistBody, who: Who):
    name = clean_text(body.name, "name", 100)
    return playlist_view(core.db.create_playlist(name, personal_owner(who, body.personal)), who)


@viewer_api.get("/playlists/{playlist_id}")
async def get_playlist(playlist_id: int, who: Who):
    return playlist_view(visible_playlist(playlist_id, who), who)


@viewer_api.patch("/playlists/{playlist_id}")
async def rename_playlist(playlist_id: int, body: PlaylistBody, who: Who):
    editable_playlist(playlist_id, who)
    return playlist_view(core.db.rename_playlist(playlist_id, clean_text(body.name, "name", 100)), who)


@viewer_api.delete("/playlists/{playlist_id}", status_code=204)
async def delete_playlist(playlist_id: int, who: Who):
    editable_playlist(playlist_id, who)
    if not core.db.delete_playlist(playlist_id):
        raise HTTPException(404, "No such playlist")


async def build_item(body, owner_id=None):
    """A playlist item from the request; a `file` item must be a file the playlist's owner (None: everyone) sees."""
    title = body.title.strip()[:200] if body.title and body.title.strip() else None
    if body.kind == "youtube":
        meta = await asyncio.to_thread(yt_info, clean_text(body.source, "source", 500))
        return {"kind": "youtube", "source": meta["video_id"], "title": title or meta["title"],
                "duration": meta["duration"], "thumbnail": meta["thumbnail"], "lang": None}
    if body.kind == "url":
        source = http_url(body.source, "source")
        if not title:
            raise HTTPException(400, "title is required for a url item")
        return {"kind": "url", "source": source, "title": title, "duration": None, "thumbnail": None, "lang": None}
    if body.kind == "radio":
        source = body.source.strip()
        station = await radio_station(source) if STATION_UUID_RE.fullmatch(source) else custom_station(
            StationBody(url=source, name=title, content_type=body.content_type, favicon=body.thumbnail))
        return {"kind": "radio", "source": station["url"], "title": title or station["name"], "duration": None,
                "thumbnail": station["favicon"], "lang": None, "content_type": station["content_type"]}
    if body.kind == "podcast":
        source = http_url(body.source, "source")
        if not title:
            raise HTTPException(400, "title is required for a podcast item")
        return {"kind": "podcast", "source": source, "title": title, "duration": body.duration,
                "thumbnail": optional_http_url(body.thumbnail), "lang": None,
                "content_type": audio_type(body.content_type) or guess_audio_type(source)}
    if body.kind == "file":
        row = core.db.get_file(int(body.source)) if body.source.strip().isdigit() else None
        if row is None or row["owner_id"] not in (None, owner_id):
            raise HTTPException(400, "source must be the id of an uploaded file")
        return {"kind": "file", "source": str(row["id"]), "title": title or row["title"], "duration": row["duration"],
                "thumbnail": None, "lang": None, "content_type": row["content_type"]}
    text = clean_text(body.source, "source", TTS_TEXT_MAX)
    lang = (body.lang or config.settings.tts_lang).strip()[:16]
    return {"kind": "tts", "source": text, "title": title or text[:60], "duration": None, "thumbnail": None,
            "lang": lang}


@viewer_api.post("/playlists/{playlist_id}/items")
async def add_item(playlist_id: int, body: ItemBody, who: Who):
    playlist = editable_playlist(playlist_id, who)
    item = await build_item(body, playlist["owner_id"])
    try:
        return playlist_or_404(core.db.add_item(playlist_id, item, config.MAX_PLAYLIST_ITEMS))
    except Conflict as e:
        raise HTTPException(409, str(e)) from e


@viewer_api.delete("/playlists/{playlist_id}/items/{item_id}", status_code=204)
async def delete_item(playlist_id: int, item_id: int, who: Who):
    editable_playlist(playlist_id, who)
    if not core.db.delete_item(playlist_id, item_id):
        raise HTTPException(404, "No such item in this playlist")


@viewer_api.put("/playlists/{playlist_id}/order")
async def reorder_playlist(playlist_id: int, body: OrderBody, who: Who):
    editable_playlist(playlist_id, who)
    try:
        return playlist_view(core.db.reorder(playlist_id, body.item_ids), who)
    except Conflict as e:
        raise HTTPException(409, str(e)) from e


@operator_api.post("/playlists/{playlist_id}/play")
async def play_playlist(playlist_id: int, body: PlayPlaylistBody, who: Who):
    return await start_playlist(visible_playlist(playlist_id, who), body.start_index, body.shuffle, body.repeat,
                                who)
