"""Scheduled announcements: next run times, validation and the background runner."""
import asyncio
import random
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException

from server import config, core, playback
from server.access import record
from server.accounts import can_see
from server.config import DATE_RE, SCHEDULE_GRACE, SCHEDULE_NAME_MAX, SCHEDULE_POLL, TIME_RE, TTS_TEXT_MAX, utc_iso
from server.playback import start_playlist
from server.schemas import clean_text
from server.talkie import talkie_sweep

# --- Scheduled announcements ---

def next_run_after(schedule, after):
    """The first run strictly after `after` (aware), from the local wall time; None once a one-off has passed."""
    hour, minute = map(int, schedule["time"].split(":"))
    if not schedule["days"]:
        day = date.fromisoformat(schedule["date"])
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=config.ZONE)
        return candidate if candidate > after else None
    today = after.astimezone(config.ZONE).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if day.weekday() in schedule["days"]:
            candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=config.ZONE)
            if candidate > after:
                return candidate
    return None  # unreachable with at least one day


def validate_schedule(fields, now, who=None):
    """Normalize a whole schedule (after merging a PATCH) and work out next_run. 400 on anything invalid.
    With `who`, the playlist must be one they can see (someone else's personal one counts as unknown)."""
    out = {"name": clean_text(fields.get("name") or "", "name", SCHEDULE_NAME_MAX)}
    out["enabled"] = True if fields.get("enabled") is None else fields["enabled"]
    action = fields.get("action")
    if action not in ("say", "playlist"):
        raise HTTPException(400, "action must be 'say' or 'playlist'")
    out["action"] = action
    if action == "say":
        out["text"] = clean_text(fields.get("text") or "", "text", TTS_TEXT_MAX)
        out["lang"] = (fields.get("lang") or config.settings.tts_lang).strip()[:16] or config.settings.tts_lang
        out["playlist_id"], out["shuffle"] = None, False
    else:
        if fields.get("playlist_id") is None:
            raise HTTPException(400, "playlist_id is required for a playlist schedule")
        playlist = core.db.get_playlist(fields["playlist_id"])
        if playlist is None or (who is not None and not can_see(playlist, who)):
            raise HTTPException(400, "Unknown playlist")
        if playlist["owner_id"] is not None:  # it would go, and the schedule stop, when its member is deleted
            raise HTTPException(400, "Schedules play shared playlists only")
        out["playlist_id"], out["shuffle"] = fields["playlist_id"], bool(fields.get("shuffle"))
        out["text"] = out["lang"] = None
    volume = fields.get("volume")
    if volume is not None and not 0 <= volume <= 1:
        raise HTTPException(400, "volume must be between 0 and 1")
    out["volume"] = volume
    if not TIME_RE.fullmatch(fields.get("time") or ""):
        raise HTTPException(400, "time must be HH:MM (24-hour)")
    out["time"] = fields["time"]
    days = fields.get("days") or []
    if any(not 0 <= d <= 6 for d in days):
        raise HTTPException(400, "days must be numbers 0 (Monday) to 6 (Sunday)")
    out["days"] = sorted(set(days))
    out["date"] = None
    if not days:
        raw = fields.get("date") or ""
        try:
            if not DATE_RE.fullmatch(raw):
                raise ValueError
            date.fromisoformat(raw)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD when days is empty (one-off)") from None
        out["date"] = raw
    following = next_run_after(out, now) if out["enabled"] else None
    if out["enabled"] and following is None:
        raise HTTPException(400, "The date and time of a one-off schedule must not be in the past")
    out["next_run"] = following and utc_iso(following)
    return out


def schedule_or_404(schedule):
    if schedule is None:
        raise HTTPException(404, "No such schedule")
    return schedule


async def fire_schedule(schedule, who):
    """Play a schedule now through the same path as POST /say or /playlists/{id}/play; raises HTTPException."""
    if schedule["action"] == "say":
        await playback.announce(schedule["text"], schedule["lang"], schedule["volume"], who)
        return
    playlist = core.db.get_playlist(schedule["playlist_id"]) if schedule["playlist_id"] is not None else None
    if playlist is None:
        raise HTTPException(400, "The schedule's playlist no longer exists")
    count = len(playlist["items"])
    start = random.randrange(count) if schedule["shuffle"] and count else 0  # shuffle keeps the start item first
    await start_playlist(playlist, start, schedule["shuffle"], "off", who, schedule["volume"])


async def run_schedule(schedule, who):
    """Fire and record the outcome ("ok" or the error) in last_result and the activity log.

    Returns the HTTPException it failed with, or None.
    """
    error = None
    try:
        await fire_schedule(schedule, who)
        result = "ok"
    except HTTPException as e:
        error, result = e, str(e.detail)
    except Exception as e:  # one broken schedule mustn't stop the runner
        result = f"{type(e).__name__}: {e}"
        error = HTTPException(500, result)
    core.db.update_schedule(schedule["id"], {"last_result": result})
    record(who, "schedule run", f"{schedule['name']}: {result}"[:200])
    return error


async def run_due_schedules(now):
    """Fire every enabled schedule whose next_run <= now (aware datetime); skip ones overdue past the grace."""
    for schedule in core.db.due_schedules(utc_iso(now)):
        due = datetime.fromisoformat(schedule["next_run"])
        following = next_run_after(schedule, now) if schedule["days"] else None
        moved = {"next_run": following and utc_iso(following)}
        if not schedule["days"]:
            moved["enabled"] = False  # one-off: done either way
        if now - due > SCHEDULE_GRACE:
            core.db.update_schedule(schedule["id"], moved | {"last_result": "missed"})
            core.db.log("system", "schedule missed",
                        f"{schedule['name']} (due {due.astimezone(config.ZONE):%Y-%m-%d %H:%M})")
            continue
        # Move next_run on before playing, so a slow download can't make the next poll fire it again.
        core.db.update_schedule(schedule["id"], moved | {"last_run": utc_iso(now)})
        await run_schedule(schedule, None)


async def schedule_loop():
    while True:
        try:
            await run_due_schedules(datetime.now(UTC))
            talkie_sweep()
            core.db.prune(force=False)  # expired sessions and old activity, hourly
        except Exception as e:  # keep the runner alive
            print(f"schedule runner error: {type(e).__name__}: {e}")
        await asyncio.sleep(SCHEDULE_POLL)
