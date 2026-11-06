"""Quick phrases and scheduled announcements."""
from datetime import UTC, datetime

from fastapi import HTTPException

from server import config, core
from server.access import Who, operator_api, record, viewer_api
from server.config import TTS_TEXT_MAX, utc_iso
from server.schedules import run_schedule, schedule_or_404, validate_schedule
from server.schemas import PhraseBody, ScheduleBody, clean_text

# --- Quick phrases ---

@viewer_api.get("/phrases")
async def list_phrases():
    return core.db.list_phrases()


@operator_api.post("/phrases")
async def add_phrase(body: PhraseBody, who: Who):
    text = clean_text(body.text, "text", TTS_TEXT_MAX)
    return core.db.add_phrase(text, (body.lang or config.settings.tts_lang).strip()[:16], who.user and who.user["id"])


@operator_api.delete("/phrases/{phrase_id}", status_code=204)
async def delete_phrase(phrase_id: int):
    if not core.db.delete_phrase(phrase_id):
        raise HTTPException(404, "No such phrase")


# --- Scheduled announcements ---

@viewer_api.get("/schedules")
async def list_schedules():
    return {"timezone": config.ZONE.key, "now": utc_iso(datetime.now(UTC)), "items": core.db.list_schedules()}


@operator_api.post("/schedules")
async def create_schedule(body: ScheduleBody, who: Who):
    fields = validate_schedule(body.model_dump(), datetime.now(UTC), who)
    schedule = core.db.create_schedule(fields, who.user and who.user["id"])
    record(who, "schedule create", schedule["name"])
    return schedule


@operator_api.patch("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, body: ScheduleBody, who: Who):
    current = schedule_or_404(core.db.get_schedule(schedule_id))
    changes = body.model_dump(exclude_unset=True)
    picked = changes.get("playlist_id", current["playlist_id"]) != current["playlist_id"]
    fields = validate_schedule(current | changes, datetime.now(UTC), who if picked else None)
    schedule = schedule_or_404(core.db.update_schedule(schedule_id, fields))
    record(who, "schedule update", schedule["name"])
    return schedule


@operator_api.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, who: Who):
    schedule = schedule_or_404(core.db.get_schedule(schedule_id))
    core.db.delete_schedule(schedule_id)
    record(who, "schedule delete", schedule["name"])


@operator_api.post("/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: int, who: Who):
    """Test-play regardless of time or enabled; next_run stays as it is."""
    schedule = schedule_or_404(core.db.get_schedule(schedule_id))
    core.db.update_schedule(schedule_id, {"last_run": utc_iso(datetime.now(UTC))})
    error = await run_schedule(schedule, who)
    if error is not None:
        raise error
    return {"ok": True}
