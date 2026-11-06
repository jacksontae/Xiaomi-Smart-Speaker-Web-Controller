"""Music sources: URL checks, internet radio (radio-browser.info) and podcast feeds."""
import asyncio
import email.utils
import html
import re
import time
import urllib.parse
from datetime import datetime
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException

from server import config, core, outbound
from server.config import (
    EPISODES_MAX,
    FEED_CACHE_TTL,
    FEED_CHECK_TIMEOUT,
    FEED_FAIL_TTL,
    FEED_REDIRECTS,
    ITUNES_NS,
    RADIO_API,
    RADIO_CODECS,
    STATION_UUID_RE,
    USER_AGENT,
    utc_iso,
)
from server.outbound import check_public_url
from server.playback import guess_audio_type
from server.schemas import clean_text

# --- Music sources: shared helpers ---

def http_url(value, field):
    value = (value or "").strip()
    if urllib.parse.urlsplit(value).scheme not in ("http", "https") or len(value) > 2000:
        raise HTTPException(400, f"{field} must be an http(s) URL")
    return value


def optional_http_url(value):
    """A picture URL from a directory or a feed: kept when it is http(s), dropped otherwise."""
    value = (value or "").strip()
    return value if urllib.parse.urlsplit(value).scheme in ("http", "https") and len(value) <= 2000 else None


def audio_type(value):
    value = (value or "").strip().lower()[:100]
    return value if value.startswith("audio/") or value in ("application/x-mpegurl", "application/vnd.apple.mpegurl") \
        else None


async def get_json(url, params, what):
    """GET a JSON API we trust (radio-browser, iTunes); 502 with a readable reason on any failure."""
    try:
        r = await outbound.http.get(url, params=params, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"{what} is unreachable ({type(e).__name__})") from e
    if r.status_code != 200:
        raise HTTPException(502, f"{what} failed: HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise HTTPException(502, f"{what} sent an unreadable answer") from e


# --- Internet radio (radio-browser.info) ---

def station_from_api(s):
    url = optional_http_url(s.get("url_resolved")) or optional_http_url(s.get("url"))
    if not url or not STATION_UUID_RE.fullmatch(s.get("stationuuid") or ""):
        return None
    codec = (s.get("codec") or "").upper()
    return {
        "uuid": s["stationuuid"],
        "name": (s.get("name") or "").strip()[:200] or "Radio",
        "url": url,
        "content_type": "application/x-mpegurl" if s.get("hls") else RADIO_CODECS.get(codec, "audio/mpeg"),
        "favicon": optional_http_url(s.get("favicon")),
        "country": (s.get("countrycode") or s.get("country") or "")[:64] or None,
        "tags": (s.get("tags") or "")[:200] or None,
        "bitrate": s.get("bitrate") if isinstance(s.get("bitrate"), int) and s["bitrate"] > 0 else None,
    }


async def radio_search(name, country, tag, limit):
    params = {"limit": limit, "hidebroken": "true", "order": "clickcount", "reverse": "true"}
    if name:
        params["name"] = name
    if country:
        params["countrycode"] = country
    if tag:
        params["tag"] = tag
    found = await get_json(f"{RADIO_API}/json/stations/search", params, "Radio directory")
    stations = [station_from_api(s) for s in found if isinstance(s, dict)] if isinstance(found, list) else []
    return [s for s in stations if s]


async def radio_station(uuid):
    found = await get_json(f"{RADIO_API}/json/stations/byuuid", {"uuids": uuid}, "Radio directory")
    stations = [station_from_api(s) for s in found if isinstance(s, dict)] if isinstance(found, list) else []
    if not any(stations):
        raise HTTPException(404, "No such radio station")
    return next(s for s in stations if s)


def custom_station(body):
    """A stream URL the user typed in, instead of a directory station."""
    url = http_url(body.url, "url")
    name = clean_text(body.name or "", "name", 200)
    return {"uuid": None, "name": name, "url": url,
            "content_type": audio_type(body.content_type) or guess_audio_type(url),
            "favicon": optional_http_url(body.favicon), "country": None, "tags": None, "bitrate": None}


async def resolve_station(body):
    if getattr(body, "favorite_id", None) is not None:
        favorite = core.db.get_favorite(body.favorite_id)
        if favorite is None:
            raise HTTPException(404, "No such favourite")
        return favorite
    if body.uuid:
        if not STATION_UUID_RE.fullmatch(body.uuid.strip()):
            raise HTTPException(400, "uuid is not a radio-browser station id")
        return await radio_station(body.uuid.strip())
    if body.url:
        return custom_station(body)
    raise HTTPException(400, "Give a station uuid, a favorite_id, or a url and name")


# --- Podcasts (iTunes Search API + the show's RSS feed) ---

async def fetch_feed(url):
    """The feed's bytes, following redirects by hand (each hop checked) and reading at most FEED_MAX."""
    for _ in range(FEED_REDIRECTS + 1):
        url = http_url(url, "feed")
        await asyncio.to_thread(check_public_url, url)
        try:
            async with outbound.feed_http.stream("GET", url, headers={"User-Agent": USER_AGENT}) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = urllib.parse.urljoin(url, r.headers["location"])
                    continue
                if r.status_code != 200:
                    raise HTTPException(502, f"Podcast feed failed: HTTP {r.status_code}")
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > config.FEED_MAX:
                        raise HTTPException(502, "Podcast feed is too large")
                return bytes(body)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Podcast feed is unreachable ({type(e).__name__})") from e
    raise HTTPException(502, "Podcast feed redirects too many times")


def parse_duration(value):
    """itunes:duration is seconds, MM:SS or HH:MM:SS."""
    try:
        seconds = 0.0
        for part in (value or "").strip().split(":"):
            seconds = seconds * 60 + float(part)
        return seconds or None
    except ValueError:
        return None


def parse_date(value):
    try:
        return utc_iso(email.utils.parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def plain_text(value, limit):
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(text.split())[:limit] or None


def parse_feed(data, limit):
    """Show details and the newest `limit` audio episodes of an RSS podcast feed."""
    if b"<!ENTITY" in data:
        raise HTTPException(502, "Podcast feed declares XML entities; refusing to parse it")
    try:
        channel = ElementTree.fromstring(data).find("channel")
    except ElementTree.ParseError as e:
        raise HTTPException(502, "Not a podcast feed (invalid XML)") from e
    if channel is None:
        raise HTTPException(502, "Not a podcast feed (no RSS channel)")
    image = channel.find(f"{ITUNES_NS}image")
    artwork = optional_http_url(image.get("href") if image is not None else channel.findtext("image/url"))
    episodes = []
    for item in channel.iter("item"):
        enclosure = item.find("enclosure")
        url = optional_http_url(enclosure.get("url") if enclosure is not None else None)
        kind = (enclosure.get("type") or "").lower() if enclosure is not None else ""
        if not url or (kind and not audio_type(kind)):
            continue  # no audio (video episodes too: the speaker can't show them)
        picture = item.find(f"{ITUNES_NS}image")
        episodes.append({
            "guid": (item.findtext("guid") or url).strip()[:500],
            "title": (item.findtext("title") or "").strip()[:200] or "Untitled episode",
            "published": parse_date(item.findtext("pubDate")),
            "duration": parse_duration(item.findtext(f"{ITUNES_NS}duration")),
            "url": url,
            "content_type": audio_type(kind) or guess_audio_type(url),
            "thumbnail": optional_http_url(picture.get("href") if picture is not None else None) or artwork,
            "description": plain_text(item.findtext(f"{ITUNES_NS}summary") or item.findtext("description"), 300),
        })
        if len(episodes) >= limit:
            break
    return {
        "title": (channel.findtext("title") or "").strip()[:200] or None,
        "author": (channel.findtext(f"{ITUNES_NS}author") or "").strip()[:200] or None,
        "artwork": artwork,
        "description": plain_text(channel.findtext("description"), 500),
        "episodes": episodes,
    }


# --- Podcast subscriptions: personal, each member follows their own shows ---

_feed_cache = {}  # feed URL -> (monotonic time, parsed show or None when it failed)


async def cached_feed(url, gate):
    """The parsed feed, read again only after FEED_CACHE_TTL; None when it can't be read (no count shown)."""
    at, show = _feed_cache.get(url, (None, None))
    if at is not None and time.monotonic() - at < (FEED_CACHE_TTL if show else FEED_FAIL_TTL):
        return show
    async with gate:
        try:
            show = parse_feed(await asyncio.wait_for(fetch_feed(url), FEED_CHECK_TIMEOUT), EPISODES_MAX)
        except (HTTPException, TimeoutError):
            show = None
    _feed_cache[url] = (time.monotonic(), show)
    return show


def newest_episode(show):
    return max((ep["published"] for ep in show["episodes"] if ep["published"]), default=None,
               key=datetime.fromisoformat)


def refresh_latest(sub, show):
    """The subscription with latest_at moved up to the feed's newest episode (stored, so it shows when the feed
    is down later)."""
    latest = newest_episode(show)
    if latest and (not sub["latest_at"] or datetime.fromisoformat(latest) > datetime.fromisoformat(sub["latest_at"])):
        core.db.set_sub_latest(sub["id"], latest)
        sub = sub | {"latest_at": latest}
    return sub


def with_new_count(sub, show):
    """The row plus `new_count`: episodes published after the member last opened the show (None: feed unreadable)."""
    if show is None:
        return sub | {"new_count": None}
    seen = datetime.fromisoformat(sub["seen_at"])
    fresh = sum(1 for ep in show["episodes"] if ep["published"] and datetime.fromisoformat(ep["published"]) > seen)
    return refresh_latest(sub, show) | {"new_count": fresh}
