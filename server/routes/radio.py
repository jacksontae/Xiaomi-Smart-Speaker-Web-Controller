"""Internet radio: directory search, favourites and playing a station."""
from typing import Annotated

from fastapi import HTTPException, Query

from server import core, sources
from server.access import Who, operator_api, record, viewer_api
from server.playback import play_source
from server.schemas import RadioPlayBody, StationBody
from server.sources import resolve_station
from server.store import Conflict

# --- Internet radio (radio-browser.info) ---

@viewer_api.get("/radio/search")
async def search_radio(
    q: Annotated[str, Query(max_length=100)] = "",
    country: Annotated[str, Query(pattern=r"^([A-Za-z]{2})?$")] = "",
    tag: Annotated[str, Query(max_length=50)] = "",
    limit: int = Query(20, ge=1, le=50),
):
    """Most-listened stations matching a name, a two-letter country code and/or a tag (all optional)."""
    return await sources.radio_search(q.strip(), country.upper(), tag.strip(), limit)


@viewer_api.get("/radio/favorites")
async def list_favorites():
    return core.db.list_favorites()


@operator_api.post("/radio/favorites")
async def add_favorite(body: StationBody, who: Who):
    station = await resolve_station(body)
    try:
        favorite = core.db.add_favorite(station, who.user and who.user["id"])
    except Conflict as e:
        raise HTTPException(409, str(e)) from e
    record(who, "radio favourite", station["name"])
    return favorite


@operator_api.delete("/radio/favorites/{favorite_id}", status_code=204)
async def delete_favorite(favorite_id: int, who: Who):
    favorite = core.db.get_favorite(favorite_id)
    if favorite is None or not core.db.delete_favorite(favorite_id):
        raise HTTPException(404, "No such favourite")
    record(who, "radio unfavourite", favorite["name"])


@operator_api.post("/radio/play")
async def play_radio(body: RadioPlayBody, who: Who):
    station = await resolve_station(body)
    return await play_source(station["url"], station["content_type"], station["name"], body.volume, who, "radio",
                             live=True, thumbnail=station["favicon"])
