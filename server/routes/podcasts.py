"""Podcasts: search, episodes, each member's followed shows, and playing an episode."""
import asyncio
import time
from typing import Annotated

from fastapi import HTTPException, Query

from server import core, sources
from server.access import SignedIn, Who, operator_api, viewer_api
from server.accounts import account_of
from server.config import EPISODES_MAX, FEED_CHECKS, PODCAST_SEARCH
from server.outbound import check_public_url
from server.playback import guess_audio_type, play_source
from server.schemas import EpisodePlayBody, SubBody, clean_text
from server.sources import (
    _feed_cache,
    audio_type,
    cached_feed,
    fetch_feed,
    http_url,
    newest_episode,
    optional_http_url,
    parse_feed,
    refresh_latest,
    with_new_count,
)

# --- Podcasts (iTunes Search API + the show's RSS feed) ---

@viewer_api.get("/podcasts/search")
async def search_podcasts(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    country: Annotated[str, Query(pattern=r"^([A-Za-z]{2})?$")] = "",
    limit: int = Query(20, ge=1, le=50),
):
    """Shows matching the words, from Apple's podcast directory; `country` picks its store (e.g. TH)."""
    params = {"media": "podcast", "entity": "podcast", "term": q.strip(), "limit": limit}
    if country:
        params["country"] = country.upper()
    found = await sources.get_json(PODCAST_SEARCH, params, "Podcast search")
    shows = []
    for r in found.get("results") or [] if isinstance(found, dict) else []:
        feed = optional_http_url(r.get("feedUrl")) if isinstance(r, dict) else None
        if feed:
            shows.append({
                "id": r.get("collectionId"),
                "title": (r.get("collectionName") or "").strip()[:200] or "Untitled show",
                "author": (r.get("artistName") or "").strip()[:200] or None,
                "feed_url": feed,
                "artwork": optional_http_url(r.get("artworkUrl600") or r.get("artworkUrl100")),
                "genre": r.get("primaryGenreName"),
                "episode_count": r.get("trackCount"),
            })
    return shows


@viewer_api.get("/podcasts/episodes")
async def podcast_episodes(
    who: Who,
    feed: Annotated[str, Query(min_length=1, max_length=2000)], limit: int = Query(50, ge=1, le=EPISODES_MAX),
):
    """The show and its episodes; `subscription` is the caller's (with the seen_at to mark new episodes by) or null."""
    url = http_url(feed, "feed")
    show = parse_feed(await fetch_feed(url), EPISODES_MAX)
    sub = core.db.get_sub(who.user["id"], feed_url=url) if who.user else None
    if sub:
        _feed_cache[url] = (time.monotonic(), show)  # fresh for the Following list too
        sub = refresh_latest(sub, show)
    return {**show, "episodes": show["episodes"][:limit], "subscription": sub}


# --- Podcast subscriptions: personal, each member follows their own shows ---

def sub_or_404(who, sub_id):
    sub = core.db.get_sub(account_of(who)["id"], sub_id)
    if sub is None:
        raise HTTPException(404, "No such subscription")
    return sub


@viewer_api.get("/podcasts/subs")
async def list_subs(who: SignedIn):
    """The caller's followed shows, each with `new_count` (feeds read a few at a time, cached FEED_CACHE_TTL)."""
    subs = core.db.list_subs(account_of(who)["id"])
    gate = asyncio.Semaphore(FEED_CHECKS)
    shows = await asyncio.gather(*(cached_feed(s["feed_url"], gate) for s in subs))
    return [with_new_count(s, show) for s, show in zip(subs, shows, strict=True)]


@viewer_api.post("/podcasts/subs")
async def follow_show(body: SubBody, who: SignedIn):
    """Follow a show (following it again is fine: the same row comes back). Episodes from now on count as new."""
    user = account_of(who)
    url = http_url(body.feed_url, "feed_url")
    await asyncio.to_thread(check_public_url, url, "feed_url")
    title = body.title.strip()[:200] if body.title and body.title.strip() else None
    author, artwork, latest = (body.author or "").strip()[:200] or None, optional_http_url(body.artwork), None
    if title is None:
        show = parse_feed(await fetch_feed(url), EPISODES_MAX)
        _feed_cache[url] = (time.monotonic(), show)
        title, author, artwork = show["title"] or url[:200], show["author"], show["artwork"]
        latest = newest_episode(show)
    return core.db.add_sub(user["id"], url, title, author, artwork, latest) | {"new_count": 0}


@viewer_api.post("/podcasts/subs/{sub_id}/seen")
async def mark_seen(sub_id: int, who: SignedIn):
    """The member opened the show: its episodes so far stop counting as new."""
    sub_or_404(who, sub_id)
    return core.db.mark_sub_seen(who.user["id"], sub_id) | {"new_count": 0}


@viewer_api.delete("/podcasts/subs/{sub_id}", status_code=204)
async def unfollow_show(sub_id: int, who: SignedIn):
    sub_or_404(who, sub_id)
    core.db.delete_sub(who.user["id"], sub_id)


@operator_api.post("/podcasts/play")
async def play_episode(body: EpisodePlayBody, who: Who):
    url = http_url(body.url, "url")
    title = clean_text(body.title, "title", 200)
    content_type = audio_type(body.content_type) or guess_audio_type(url)
    return await play_source(url, content_type, title, body.volume, who, "podcast",
                             thumbnail=optional_http_url(body.thumbnail))
