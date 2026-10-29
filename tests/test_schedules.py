"""Scheduled announcements: validation, next_run, the runner (driven directly, no sleeping) and storage."""
import asyncio
import sqlite3
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import BASE, make_user, session_client

import store

BKK = ZoneInfo("Asia/Bangkok")
EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]


@pytest.fixture(autouse=True)
def bangkok(app, monkeypatch):
    monkeypatch.setattr(app, "ZONE", BKK)


def bkk(*args):
    return datetime(*args, tzinfo=BKK)


def say_body(**over):
    return {"name": "Lunch", "action": "say", "text": "กินข้าว", "time": "12:00", "days": EVERY_DAY} | over


def create(client, **over):
    r = client.post("/schedules", json=say_body(**over))
    assert r.status_code == 200, r.text
    return r.json()


def set_due(app, schedule_id, when):
    app.db.update_schedule(schedule_id, {"next_run": app.utc_iso(when)})


def run_due(app, now):
    asyncio.run(app.run_due_schedules(now))


def actions(client):
    return [(e["actor"], e["action"], e["detail"]) for e in client.get("/activity").json()]


def tts_playlist(app, *texts, name="Morning"):
    pl = app.db.create_playlist(name)
    for text in texts:
        app.db.add_item(pl["id"], {"kind": "tts", "source": text, "title": text, "lang": "en"}, 10)
    return pl["id"]


# --- API and validation ---

def test_create_say_schedule(client, app):
    s = create(client)
    assert set(s) == {"id", "name", "enabled", "action", "text", "lang", "playlist_id", "shuffle", "volume", "time",
                      "days", "date", "next_run", "last_run", "last_result", "created_by"}
    assert s["enabled"] is True and s["lang"] == "th" and s["playlist_id"] is None and s["shuffle"] is False
    assert s["volume"] is None and s["date"] is None and s["last_run"] is None and s["last_result"] is None
    assert s["created_by"] is None  # API token
    following = datetime.fromisoformat(s["next_run"])
    assert following > datetime.now(UTC) and following.astimezone(BKK).strftime("%H:%M") == "12:00"
    alice = session_client(make_user("alice", "operator", "Alice"))
    assert create(alice, name="By Alice")["created_by"] == "Alice"


def test_days_normalized_and_date_dropped(client):
    s = create(client, days=[4, 0, 0], date="2099-01-01", text="  hi  ", lang="en", shuffle=True, playlist_id=5)
    assert s["days"] == [0, 4] and s["date"] is None and s["text"] == "hi" and s["lang"] == "en"
    assert s["shuffle"] is False and s["playlist_id"] is None  # playlist fields don't apply to say


@pytest.mark.parametrize("over", [
    {"name": "  "}, {"name": "x" * 81}, {"action": "youtube"}, {"action": None}, {"text": " "}, {"text": "x" * 1001},
    {"time": "24:00"}, {"time": "7:00"}, {"time": "12:60"}, {"time": None}, {"days": [7]}, {"days": [-1]},
    {"days": []}, {"days": [], "date": "2099-13-01"}, {"days": [], "date": "01/01/2099"},
    {"days": [], "date": "2020-01-01"}, {"volume": 1.5}, {"volume": -0.1},
    {"action": "playlist"}, {"action": "playlist", "playlist_id": 999},
], ids=str)
def test_validation_errors(client, over):
    r = client.post("/schedules", json=say_body(**over))
    assert r.status_code == 400, r.text
    assert isinstance(r.json()["detail"], str)


def test_one_off_earlier_today_is_in_the_past(client):
    today = datetime.now(BKK)
    if today.hour == 0 and today.minute == 0:
        pytest.skip("no earlier minute today")
    r = client.post("/schedules", json=say_body(days=[], date=today.date().isoformat(), time="00:00"))
    assert r.status_code == 400 and "past" in r.json()["detail"]


def test_disabled_one_off_may_be_in_the_past(client):
    s = create(client, days=[], date="2020-01-01", enabled=False)
    assert s["enabled"] is False and s["next_run"] is None and s["date"] == "2020-01-01"


def test_one_off_next_run(client):
    s = create(client, days=[], date="2099-01-01", time="08:30")
    assert s["next_run"] == "2099-01-01T01:30:00+00:00"


def test_playlist_schedule(client, app):
    pid = tts_playlist(app, "one")
    s = create(client, action="playlist", playlist_id=pid, shuffle=True, volume=0.4, text="ignored")
    assert s["action"] == "playlist" and s["playlist_id"] == pid and s["shuffle"] is True and s["volume"] == 0.4
    assert s["text"] is None and s["lang"] is None


def test_patch_revalidates_whole_schedule(client, app):
    s = create(client, volume=0.5)
    r = client.patch(f"/schedules/{s['id']}", json={"name": "Dinner"})
    assert r.status_code == 200
    patched = r.json()
    assert patched["name"] == "Dinner" and patched["text"] == s["text"] and patched["volume"] == 0.5
    assert patched["next_run"] == s["next_run"]
    assert client.patch(f"/schedules/{s['id']}", json={"volume": None}).json()["volume"] is None
    assert client.patch(f"/schedules/{s['id']}", json={"action": "playlist"}).status_code == 400
    assert client.patch(f"/schedules/{s['id']}", json={"days": []}).status_code == 400  # one-off needs a date
    off = client.patch(f"/schedules/{s['id']}", json={"enabled": False}).json()
    assert off["enabled"] is False and off["next_run"] is None
    on = client.patch(f"/schedules/{s['id']}", json={"enabled": True, "time": "06:15"}).json()
    assert datetime.fromisoformat(on["next_run"]).astimezone(BKK).strftime("%H:%M") == "06:15"
    assert client.patch("/schedules/999", json={"name": "x"}).status_code == 404


def test_reenabling_a_finished_one_off_needs_a_new_date(client, app):
    s = create(client, days=[], date="2099-01-01")
    app.db.update_schedule(s["id"], {"date": "2020-01-01", "enabled": False, "next_run": None})
    assert client.patch(f"/schedules/{s['id']}", json={"name": "Renamed"}).status_code == 200
    assert client.patch(f"/schedules/{s['id']}", json={"enabled": True}).status_code == 400
    r = client.patch(f"/schedules/{s['id']}", json={"enabled": True, "date": "2099-02-01"})
    assert r.status_code == 200 and r.json()["next_run"].startswith("2099-02-01")


def test_delete(client):
    s = create(client)
    assert client.delete(f"/schedules/{s['id']}").status_code == 204
    assert client.delete(f"/schedules/{s['id']}").status_code == 404
    assert client.get("/schedules").json()["items"] == []


def test_list_envelope_sorted_by_next_run(client, app):
    late = create(client, name="Late", time="23:00")
    off = create(client, name="Off", enabled=False)
    early = create(client, name="Early", time="01:00")
    set_due(app, late["id"], bkk(2099, 1, 2, 23, 0))
    set_due(app, early["id"], bkk(2099, 1, 1, 1, 0))
    body = client.get("/schedules").json()
    assert body["timezone"] == "Asia/Bangkok"
    assert datetime.fromisoformat(body["now"]).tzinfo is not None
    assert [s["id"] for s in body["items"]] == [early["id"], late["id"], off["id"]]


def test_roles(as_role):
    viewer, operator = as_role("viewer"), as_role("operator")
    s = create(operator)
    assert viewer.get("/schedules").json()["items"][0]["id"] == s["id"]
    assert viewer.post("/schedules", json=say_body()).status_code == 403
    assert viewer.patch(f"/schedules/{s['id']}", json={"name": "x"}).status_code == 403
    assert viewer.post(f"/schedules/{s['id']}/run").status_code == 403
    assert viewer.delete(f"/schedules/{s['id']}").status_code == 403
    assert operator.patch(f"/schedules/{s['id']}", json={"name": "x"}).status_code == 200
    assert operator.delete(f"/schedules/{s['id']}").status_code == 204


def test_activity_for_create_update_delete(client):
    alice = session_client(make_user("alice", "operator", "Alice"))
    s = create(alice)
    alice.patch(f"/schedules/{s['id']}", json={"name": "Dinner"})
    alice.delete(f"/schedules/{s['id']}")
    assert actions(client)[:3] == [
        ("Alice", "schedule delete", "Dinner"), ("Alice", "schedule update", "Dinner"),
        ("Alice", "schedule create", "Lunch"),
    ]


# --- next_run ---

def test_next_run_daily(app):
    s = {"time": "07:00", "days": EVERY_DAY, "date": None}
    assert app.next_run_after(s, bkk(2026, 11, 2, 6, 59)) == bkk(2026, 11, 2, 7, 0)
    assert app.next_run_after(s, bkk(2026, 11, 2, 7, 0)) == bkk(2026, 11, 3, 7, 0)  # strictly after
    # Zone-aware: 07:00 in Bangkok is midnight UTC, whatever zone `after` is in.
    assert app.utc_iso(app.next_run_after(s, datetime(2026, 11, 2, 1, 0, tzinfo=UTC))) == "2026-11-03T00:00:00+00:00"


def test_next_run_weekdays_and_weekend(app):
    weekdays = {"time": "08:00", "days": [0, 1, 2, 3, 4], "date": None}
    friday_after = bkk(2026, 10, 30, 9, 0)
    assert app.next_run_after(weekdays, friday_after) == bkk(2026, 11, 2, 8, 0)  # Monday
    weekend = {"time": "08:00", "days": [5, 6], "date": None}
    assert app.next_run_after(weekend, friday_after) == bkk(2026, 10, 31, 8, 0)
    assert app.next_run_after(weekend, bkk(2026, 11, 1, 8, 0)) == bkk(2026, 11, 7, 8, 0)  # Sunday done -> Saturday
    only_monday = {"time": "08:00", "days": [0], "date": None}
    assert app.next_run_after(only_monday, bkk(2026, 11, 2, 8, 1)) == bkk(2026, 11, 9, 8, 0)


def test_next_run_one_off(app):
    s = {"time": "08:30", "days": [], "date": "2026-11-05"}
    assert app.next_run_after(s, bkk(2026, 11, 5, 8, 29)) == bkk(2026, 11, 5, 8, 30)
    assert app.next_run_after(s, bkk(2026, 11, 5, 8, 30)) is None


def test_next_run_keeps_wall_time_across_dst(app, monkeypatch):
    ny = ZoneInfo("America/New_York")
    monkeypatch.setattr(app, "ZONE", ny)
    s = {"time": "07:00", "days": EVERY_DAY, "date": None}
    before = app.next_run_after(s, datetime(2026, 3, 6, 13, 0, tzinfo=UTC))
    after = app.next_run_after(s, datetime(2026, 3, 7, 13, 0, tzinfo=UTC))
    assert app.utc_iso(before) == "2026-03-07T12:00:00+00:00"  # EST
    assert app.utc_iso(after) == "2026-03-08T11:00:00+00:00"  # EDT, still 07:00 local
    assert after.astimezone(ny).hour == 7


def test_local_zone_from_tz_env(app, monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    assert app.local_zone().key == "Europe/Berlin"
    monkeypatch.setenv("TZ", "Not/AZone")
    assert app.local_zone().key == "UTC"


# --- Runner ---

def test_due_say_fires_through_say_path(client, app, fake_speaker):
    s = create(client, text="ประชุม", volume=0.7)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    now = bkk(2026, 11, 2, 12, 0, 10)
    run_due(app, now)
    load = fake_speaker.media_controller.loads[-1]
    assert load["url"].startswith(f"{BASE}/tts.mp3?") and "lang=th" in load["url"]
    assert load["title"] == "Announcement" and fake_speaker.volume == 0.7
    done = app.db.get_schedule(s["id"])
    assert done["last_result"] == "ok" and done["last_run"] == app.utc_iso(now) and done["enabled"] is True
    assert done["next_run"] == app.utc_iso(bkk(2026, 11, 3, 12, 0))
    log = actions(client)
    assert log[0] == ("system", "schedule run", "Lunch: ok")
    assert log[1] == ("system", "say", "ประชุม")


def test_say_schedule_resumes_interrupted_track(client, app, fake_speaker):
    mc = fake_speaker.media_controller
    mc.play_media(f"{BASE}/yt/aaaaaaaaaaa.m4a", "audio/mp4", title="Song")
    mc.status.adjusted_current_time = 30.0
    s = create(client)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    run_due(app, bkk(2026, 11, 2, 12, 0))
    assert app._resume["title"] == "Song"


def test_not_due_or_disabled_does_not_fire(client, app, fake_speaker):
    s = create(client)
    off = create(client, name="Off", enabled=False)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    app.db.update_schedule(off["id"], {"next_run": app.utc_iso(bkk(2026, 11, 2, 11, 0))})  # stale, but disabled
    run_due(app, bkk(2026, 11, 2, 11, 59, 59))
    assert fake_speaker.media_controller.loads == []
    assert app.db.get_schedule(s["id"])["last_result"] is None
    assert app.db.get_schedule(off["id"])["last_result"] is None


def test_one_off_disables_after_firing(client, app, fake_speaker):
    s = create(client, days=[], date="2099-01-01")
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    run_due(app, bkk(2026, 11, 2, 12, 0, 5))
    done = app.db.get_schedule(s["id"])
    assert done["enabled"] is False and done["next_run"] is None and done["last_result"] == "ok"
    assert len(fake_speaker.media_controller.loads) == 1
    run_due(app, bkk(2026, 11, 2, 12, 1))
    assert len(fake_speaker.media_controller.loads) == 1


def test_overdue_within_grace_still_fires(client, app, fake_speaker):
    s = create(client)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    run_due(app, bkk(2026, 11, 2, 12, 5))
    assert app.db.get_schedule(s["id"])["last_result"] == "ok"
    assert len(fake_speaker.media_controller.loads) == 1


def test_missed_beyond_grace_is_skipped(client, app, fake_speaker):
    s = create(client)
    one_off = create(client, name="Once", days=[], date="2099-01-01")
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    set_due(app, one_off["id"], bkk(2026, 11, 2, 9, 0))
    now = bkk(2026, 11, 2, 12, 5, 1)
    run_due(app, now)
    assert fake_speaker.media_controller.loads == []
    missed = app.db.get_schedule(s["id"])
    assert missed["last_result"] == "missed" and missed["last_run"] is None and missed["enabled"] is True
    assert missed["next_run"] == app.utc_iso(bkk(2026, 11, 3, 12, 0))
    gone = app.db.get_schedule(one_off["id"])
    assert gone["last_result"] == "missed" and gone["enabled"] is False and gone["next_run"] is None
    log = actions(client)
    assert ("system", "schedule missed", "Lunch (due 2026-11-02 12:00)") in log
    assert ("system", "schedule missed", "Once (due 2026-11-02 09:00)") in log


def test_speaker_error_recorded_and_runner_continues(client, app, monkeypatch):
    first = create(client, name="First")
    second = create(client, name="Second")
    for s in (first, second):
        set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))

    def unreachable():
        raise OSError("no route to host")

    monkeypatch.setattr(app, "get_cast", unreachable)
    run_due(app, bkk(2026, 11, 2, 12, 0))
    for s in (first, second):
        done = app.db.get_schedule(s["id"])
        assert "not responding" in done["last_result"]
        assert done["next_run"] == app.utc_iso(bkk(2026, 11, 3, 12, 0))
    assert any(a == "schedule run" and d.startswith("Second: Speaker") for _, a, d in actions(client))


def test_failure_does_not_stop_later_schedules(client, app, fake_speaker):
    empty = tts_playlist(app, name="Empty")
    broken = create(client, name="Broken", action="playlist", playlist_id=empty)
    fine = create(client, name="Fine")
    set_due(app, broken["id"], bkk(2026, 11, 2, 11, 59))
    set_due(app, fine["id"], bkk(2026, 11, 2, 12, 0))
    run_due(app, bkk(2026, 11, 2, 12, 0))
    assert app.db.get_schedule(broken["id"])["last_result"] == "The playlist is empty"
    assert app.db.get_schedule(fine["id"])["last_result"] == "ok"


def test_unexpected_error_is_recorded(client, app, monkeypatch):
    s = create(client)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))

    async def boom(text, lang, volume, who):
        raise RuntimeError("bug")

    monkeypatch.setattr(app, "announce", boom)
    run_due(app, bkk(2026, 11, 2, 12, 0))
    assert app.db.get_schedule(s["id"])["last_result"] == "RuntimeError: bug"


def test_playlist_schedule_starts_queue(client, app, fake_speaker, fresh_state):
    pid = tts_playlist(app, "one", "two")
    s = create(client, name="Music", action="playlist", playlist_id=pid, volume=0.6)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    run_due(app, bkk(2026, 11, 2, 12, 0))
    q = app._queue
    assert q is not None and q.playlist_id == pid and q.repeat == "off" and q.current["source"] == "one"
    assert "text=one" in fake_speaker.media_controller.loads[-1]["url"]
    assert fake_speaker.volume == 0.6 and fresh_state.watchers == 1
    assert app.db.get_schedule(s["id"])["last_result"] == "ok"
    assert actions(client)[:2] == [("system", "schedule run", "Music: ok"), ("system", "playlist play", "Morning")]


def test_playlist_schedule_without_volume_uses_default(client, app, fake_speaker):
    app.settings.default_volume = 0.3
    pid = tts_playlist(app, "one")
    s = create(client, action="playlist", playlist_id=pid, shuffle=True)
    set_due(app, s["id"], bkk(2026, 11, 2, 12, 0))
    run_due(app, bkk(2026, 11, 2, 12, 0))
    assert fake_speaker.volume == 0.3 and app._queue.shuffle is True


def test_deleting_playlist_disables_its_schedules(client, app):
    pid = tts_playlist(app, "one")
    s = create(client, action="playlist", playlist_id=pid)
    other = create(client, name="Other")
    assert client.delete(f"/playlists/{pid}").status_code == 204
    gone = app.db.get_schedule(s["id"])
    assert gone["enabled"] is False and gone["playlist_id"] is None and gone["next_run"] is None
    assert app.db.get_schedule(other["id"])["enabled"] is True
    assert client.patch(f"/schedules/{s['id']}", json={"enabled": True}).status_code == 400
    r = client.post(f"/schedules/{s['id']}/run")
    assert r.status_code == 400 and "no longer exists" in r.json()["detail"]


# --- Run now ---

def test_run_now_ignores_time_and_enabled(client, app, fake_speaker):
    alice = session_client(make_user("alice", "operator", "Alice"))
    s = create(alice, enabled=False)
    r = alice.post(f"/schedules/{s['id']}/run")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(fake_speaker.media_controller.loads) == 1
    done = app.db.get_schedule(s["id"])
    assert done["next_run"] is None and done["enabled"] is False and done["last_result"] == "ok"
    assert done["last_run"] is not None
    assert actions(client)[0] == ("Alice", "schedule run", "Lunch: ok")
    assert actions(client)[1] == ("Alice", "say", "กินข้าว")


def test_run_now_keeps_next_run(client, app):
    s = create(client)
    client.post(f"/schedules/{s['id']}/run")
    assert app.db.get_schedule(s["id"])["next_run"] == s["next_run"]
    assert client.post("/schedules/999/run").status_code == 404


def test_run_now_speaker_error_is_503(client, app, monkeypatch):
    s = create(client)

    def unreachable():
        raise OSError("down")

    monkeypatch.setattr(app, "get_cast", unreachable)
    r = client.post(f"/schedules/{s['id']}/run")
    assert r.status_code == 503 and "not responding" in r.json()["detail"]
    assert "not responding" in app.db.get_schedule(s["id"])["last_result"]


# --- Storage ---

def test_migrates_version_1_database_in_place(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    for statement in store.SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    db.execute("INSERT INTO playlists (name, created_at, updated_at) VALUES ('Kept', 'x', 'x')")
    db.execute("PRAGMA user_version = 1")
    db.commit()
    db.close()

    upgraded = store.Store(path)
    assert upgraded.schema_version() == store.SCHEMA_VERSION == 2
    assert [p["name"] for p in upgraded.list_playlists()] == ["Kept"]
    fields = {"name": "n", "enabled": True, "action": "say", "text": "t", "lang": "th", "playlist_id": None,
              "shuffle": False, "volume": None, "time": "07:00", "days": [0], "date": None, "next_run": None}
    created = upgraded.create_schedule(fields, None)
    assert created["days"] == [0] and created["enabled"] is True
    reopened = store.Store(path)  # already current: nothing to do, nothing lost
    assert reopened.schema_version() == 2 and len(reopened.list_schedules()) == 1


def test_fresh_database_is_current(tmp_path):
    fresh = store.Store(tmp_path / "new.db")
    assert fresh.schema_version() == 2 and fresh.list_schedules() == []


def test_runner_starts_and_stops_with_the_app(app, monkeypatch):
    from fastapi.testclient import TestClient

    events = []

    async def fake_loop():
        events.append("started")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            events.append("stopped")
            raise

    monkeypatch.setattr(app, "schedule_loop", fake_loop)
    with TestClient(app.app):
        pass
    assert events == ["started", "stopped"]
