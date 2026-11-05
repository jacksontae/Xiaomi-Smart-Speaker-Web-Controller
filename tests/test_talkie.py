"""Talkie: the /talkie WebSocket (presence, one talker at a time, live stream, clips) with the fake transcoder."""
import asyncio
import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anyio.from_thread
import pytest
from conftest import make_user, session_client
from test_talk import WEBM, FakeTranscoder, refused

import store


@pytest.fixture
def talkie(app, monkeypatch):
    """Fake transcoder, short timers; talks of any length keep a clip unless a test says otherwise."""
    made = []
    monkeypatch.setattr(app, "talk_transcoder", lambda fmt: FakeTranscoder(fmt, made))
    monkeypatch.setattr(app, "talk_available", lambda: True)
    monkeypatch.setattr(app, "TALK_TICK", 0.02)
    monkeypatch.setattr(app, "TALKIE_MIN_SECONDS", 0)
    return SimpleNamespace(made=made)


@pytest.fixture
def room(talkie):
    """member(username, role) -> a signed-in client whose sockets share one event loop with the others' (the
    TestClient otherwise runs each connection on a loop of its own, and broadcasts cross between them)."""
    with anyio.from_thread.start_blocking_portal() as portal:
        def member(username, role="operator"):
            user = make_user(username, role)
            c = session_client(user)
            c.portal, c.user_id = portal, user["id"]
            return c

        yield member


def hello(ws):
    msg = ws.receive_json()
    assert msg["type"] == "hello"
    return msg


def until(ws, kind):
    while (msg := ws.receive_json())["type"] != kind:
        pass
    return msg


def pong(ws):
    """Nothing else is waiting for this socket: the next frame answers a ping."""
    ws.send_json({"type": "ping"})
    assert ws.receive_json() == {"type": "pong"}


def names(online):
    return [m["name"] for m in online]


def test_presence_counts_a_member_once(room):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a:
        first = hello(a)
        assert first["me"] == alice.user_id and names(first["online"]) == ["Alice"]
        assert first["live"] is None and first["clips"] == []
        with bob.websocket_connect("/talkie") as b:
            assert names(hello(b)["online"]) == ["Alice", "Bob"]
            assert names(until(a, "online")["online"]) == ["Alice", "Bob"]
            with alice.websocket_connect("/talkie") as a2:  # a second tab: nobody is told
                assert names(hello(a2)["online"]) == ["Alice", "Bob"]
                a2.close()
                pong(b)
            b.close()  # inside the block: leaving it would cancel the server's side before it tells the others
            assert names(until(a, "online")["online"]) == ["Alice"]


def test_talk_goes_live_and_is_kept(room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        until(a, "online")
        a.send_json({"type": "start", "mime": WEBM})
        ready = a.receive_json()
        assert ready == {"type": "ready", "id": ready["id"], "max_seconds": 60}
        live = until(b, "live")
        assert live == {"type": "live", "id": ready["id"], "user_id": alice.user_id, "name": "Alice",
                        "url": f"/talkie/live/{ready['id']}"}
        a.send_bytes(b"one")
        a.send_bytes(b"two")
        a.send_json({"type": "stop"})
        ended = until(a, "ended")
        assert until(b, "ended") == ended
        assert ended["id"] == ready["id"] and ended["reason"] == "stopped"
        clip = ended["clip"]
        assert clip["id"] == ready["id"] and clip["name"] == "Alice"
        assert clip["url"] == f"/talkie/clips/{clip['id']}.mp3"
        assert app._talkie is None and talkie.made[0].fmt == "webm" and talkie.made[0].finished
        with bob.websocket_connect("/talkie") as b2:  # a tab opened later sees the clip
            assert hello(b2)["clips"] == [clip]
    assert bob.get("/talkie/clips").json() == [clip]
    played = bob.get(clip["url"])
    assert played.content == b"MP3:oneMP3:two" and played.headers["content-type"] == "audio/mpeg"
    assert bob.get(live["url"]).content == b"MP3:oneMP3:two"  # the live stream, for a slow listener
    assert (app.TALKIE_DIR / f"{clip['id']}.mp3").read_bytes() == b"MP3:oneMP3:two"
    assert not any(e["action"] == "talk" for e in app.db.activity())  # chat isn't logged


def test_live_stream_follows_the_talk(room, app, talkie):
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        a.send_json({"type": "start", "mime": "audio/mp4"})
        talk_id = a.receive_json()["id"]
        a.send_bytes(b"x")
        pong(a)
        assert app._talkie.id == talk_id and talkie.made[0].fmt == "mp4"
        a.send_json({"type": "stop"})
        until(a, "ended")
    assert alice.get(f"/talkie/live/{talk_id}").content == b"MP3:x"
    assert alice.get("/talkie/live/other").status_code == 404


def test_one_talker_at_a_time(room, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        a.send_json({"type": "start", "mime": WEBM})
        until(a, "ready")
        until(b, "live")
        b.send_json({"type": "start", "mime": WEBM})
        assert b.receive_json() == {"type": "error", "code": "busy", "detail": "Alice is talking right now"}
        pong(b)  # the socket stays open
        a.send_json({"type": "stop"})
        until(b, "ended")
        b.send_json({"type": "start", "mime": WEBM})
        assert b.receive_json()["type"] == "ready"
        b.send_json({"type": "stop"})
        until(b, "ended")
    assert len(talkie.made) == 2


def test_speaker_talk_is_separate(room, app, talkie, fake_speaker):
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        a.send_json({"type": "start", "mime": WEBM})
        assert a.receive_json()["type"] == "ready"
        with alice.websocket_connect("/talk") as t:
            t.send_json({"type": "start", "mime": WEBM})
            assert t.receive_json()["type"] == "ready"
            t.send_json({"type": "stop"})
            until(t, "ended")
        a.send_json({"type": "stop"})
        until(a, "ended")


def test_short_talk_keeps_no_clip(room, app, talkie, monkeypatch):
    monkeypatch.setattr(app, "TALKIE_MIN_SECONDS", 0.5)
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        a.send_json({"type": "start", "mime": WEBM})
        a.receive_json()
        a.send_bytes(b"blip")
        a.send_json({"type": "stop"})
        assert until(a, "ended")["clip"] is None
    assert alice.get("/talkie/clips").json() == [] and not any(app.TALKIE_DIR.glob("*"))


def test_hanging_up_ends_the_talk(room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with bob.websocket_connect("/talkie") as b:
        hello(b)
        with alice.websocket_connect("/talkie") as a:
            hello(a)
            a.send_json({"type": "start", "mime": WEBM})
            a.receive_json()
            a.send_bytes(b"hi")
            pong(a)
            a.close()
            ended = until(b, "ended")
            assert ended["reason"] == "disconnected" and ended["clip"]["name"] == "Alice"
            assert names(until(b, "online")["online"]) == ["Bob"]
    assert app._talkie is None and talkie.made[0].finished


@pytest.mark.parametrize(("limit", "reason"), [("TALKIE_MAX_SECONDS", "max_length"), ("TALK_IDLE_TIMEOUT", "idle")])
def test_timers_end_the_talk(limit, reason, room, app, talkie, monkeypatch):
    monkeypatch.setattr(app, limit, 0.2)
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        a.send_json({"type": "start", "mime": WEBM})
        a.receive_json()
        assert until(a, "ended")["reason"] == reason
        pong(a)  # a member stays connected after their talk


def test_too_much_audio(room, app, talkie, monkeypatch):
    monkeypatch.setattr(app, "TALK_MAX_RATE", 1)  # 60 bytes for a 60 s talk
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        a.send_json({"type": "start", "mime": WEBM})
        a.receive_json()
        a.send_bytes(b"x" * 100)
        assert until(a, "ended")["reason"] == "too_large"


@pytest.mark.parametrize(("who", "headers", "code", "close"), [
    ("anon", {}, "unauthorized", 4401),
    ("token", {"authorization": "Bearer test-token"}, "forbidden", 4403),
    ("operator", {"origin": "https://evil.example.com"}, "forbidden", 4403),
])
def test_refused_callers(who, headers, code, close, anon, as_role, talkie):
    c = as_role(who) if who == "operator" else anon
    with c.websocket_connect("/talkie", headers=headers) as ws:
        error, closed = refused(ws)
    assert error["type"] == "error" and error["code"] == code and closed == close


def test_viewers_may_talk(as_role, talkie):
    with as_role("viewer").websocket_connect("/talkie", headers={"origin": "http://testserver"}) as ws:
        hello(ws)
        ws.send_json({"type": "start", "mime": WEBM})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "stop"})
        until(ws, "ended")


def test_bad_start(app, as_role, talkie, monkeypatch):
    with as_role("viewer").websocket_connect("/talkie") as ws:
        hello(ws)
        ws.send_json({"type": "start", "mime": "audio/wav"})
        error = ws.receive_json()
        assert error["code"] == "bad_request" and "Unsupported recording format" in error["detail"]
        monkeypatch.setattr(app, "talk_available", lambda: False)
        ws.send_json({"type": "start", "mime": WEBM})
        error = ws.receive_json()
        assert error["code"] == "unavailable" and "ffmpeg" in error["detail"]
        ws.send_bytes(b"stray audio")  # ignored: not talking
        pong(ws)
    assert talkie.made == []


def test_signed_out_member_is_dropped(app, talkie):
    user = make_user("ann", "viewer")
    c = session_client(user)
    with c.websocket_connect("/talkie") as ws:
        hello(ws)
        app.db.delete_sessions(user["id"])
        ws.send_json({"type": "ping"})
        error, closed = refused(ws)
    assert error["code"] == "unauthorized" and closed == 4401


def saved_clip(app, client):
    with client.websocket_connect("/talkie") as ws:
        hello(ws)
        ws.send_json({"type": "start", "mime": WEBM})
        ws.receive_json()
        ws.send_bytes(b"audio")
        ws.send_json({"type": "stop"})
        return until(ws, "ended")["clip"]


def test_clips_expire_after_a_day(app, as_role, anon, talkie):
    viewer = as_role("viewer")
    clip = saved_clip(app, viewer)
    path = app.TALKIE_DIR / f"{clip['id']}.mp3"
    assert anon.get(clip["url"]).status_code == 401 and viewer.get(clip["url"]).status_code == 200
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat(timespec="seconds")
    with app.db.tx() as db:
        db.execute("UPDATE talkie_clips SET created_at = ?", (old,))
    assert viewer.get(clip["url"]).status_code == 404  # out of the list and unplayable right away
    assert viewer.get("/talkie/clips").json() == []
    orphan = app.TALKIE_DIR / "gone.mp3"
    orphan.write_bytes(b"x")
    os.utime(orphan, (time.time() - 90000,) * 2)
    app.talkie_sweep(force=True)
    assert not path.exists() and not orphan.exists() and app.db.get_clip(clip["id"]) is None


def test_sweep_runs_at_most_hourly(app, talkie, monkeypatch):
    calls = []
    monkeypatch.setattr(app.db, "expire_clips", lambda before: calls.append(before) or [])
    app.talkie_sweep()
    app.talkie_sweep()
    assert len(calls) == 1


def test_deleting_a_member_deletes_their_clips(app, client, talkie):
    user = make_user("ann", "viewer")
    clip = saved_clip(app, session_client(user))
    path = app.TALKIE_DIR / f"{clip['id']}.mp3"
    assert path.exists()
    assert client.delete(f"/users/{user['id']}").status_code == 204
    assert not path.exists() and client.get("/talkie/clips").json() == []


def test_shutdown_kills_a_running_talkie(app, monkeypatch):
    from fastapi.testclient import TestClient

    killed = []
    monkeypatch.setattr(app, "_talkie", SimpleNamespace(transcoder=SimpleNamespace(kill=lambda: killed.append(1))))
    monkeypatch.setattr(app, "schedule_loop", asyncio.Event().wait)
    with TestClient(app.app):
        pass
    assert killed == [1]


def test_migration_from_7_adds_clips(tmp_path):
    path = tmp_path / "v7.db"
    db = sqlite3.connect(path)
    for statement in store.SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    for version in range(2, 8):
        for statement in store.MIGRATIONS[version]:
            db.execute(statement)
    db.execute("INSERT INTO users (id, username, display_name, role, password_hash, created_at)"
               " VALUES (3, 'vee', 'Vee', 'viewer', 'x', 'x')")
    db.execute("PRAGMA user_version = 7")
    db.commit()
    db.close()

    upgraded = store.Store(path)
    assert upgraded.schema_version() == store.SCHEMA_VERSION == 8
    clip = upgraded.add_clip("abc", 3, 2.5, "abc.mp3")
    assert clip["name"] == "Vee" and upgraded.list_clips("2000-01-01") == [clip]
    assert upgraded.user_clip_files(3) == ["abc.mp3"]
