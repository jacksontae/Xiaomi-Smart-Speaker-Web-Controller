"""Talkie: the /talkie WebSocket (presence and the room, walkie talks one at a time, messages, live stream, clips)
with the fake transcoder."""
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

from server import store


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


def rooms(online):
    return {m["name"]: m["in_room"] for m in online}


def drain(ws):
    """The types of the frames that came before the answer to a ping (what this socket was told meanwhile)."""
    ws.send_json({"type": "ping"})
    kinds = []
    while (msg := ws.receive_json())["type"] != "pong":
        kinds.append(msg["type"])
    return kinds


def start(ws, mode="walkie", mime=WEBM):
    ws.send_json({"type": "start", "mime": mime, "mode": mode})


def record(ws, mode, audio=b"audio"):
    """Start a talk in `mode`, send `audio`, stop; the talker's "ended"."""
    start(ws, mode)
    until(ws, "ready")
    ws.send_bytes(audio)
    ws.send_json({"type": "stop"})
    return until(ws, "ended")


def test_presence_counts_a_member_once(room):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a:
        first = hello(a)
        assert first["me"] == alice.user_id and first["online"] == [{"id": alice.user_id, "name": "Alice",
                                                                     "in_room": True}]
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


def test_walkie_goes_live_to_the_room(room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        until(a, "online")
        start(a)
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
        assert ended["id"] == ready["id"] and ended["reason"] == "stopped" and ended["clip"] is None
        assert app._talkie is None and talkie.made[0].fmt == "webm" and talkie.made[0].finished
        assert bob.get(live["url"]).content == b"MP3:oneMP3:two"  # the live stream, for a slow listener
    assert not any(e["action"] == "talk" for e in app.db.activity())  # chat isn't logged


def test_message_is_kept_for_everyone(room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie?room=0") as b:
        hello(a), hello(b)
        until(a, "online")
        clip = record(a, "message", b"hello")["clip"]
        assert clip["name"] == "Alice" and clip["url"] == f"/talkie/clips/{clip['id']}.mp3"
        assert until(a, "clip") == until(b, "clip") == {"type": "clip", "clip": clip}  # also outside the room
        with bob.websocket_connect("/talkie") as b2:  # a tab opened later sees the clip
            assert hello(b2)["clips"] == [clip]
    assert bob.get("/talkie/clips").json() == [clip]
    played = bob.get(clip["url"])
    assert played.content == b"MP3:hello" and played.headers["content-type"] == "audio/mpeg"
    assert (app.TALKIE_DIR / f"{clip['id']}.mp3").read_bytes() == b"MP3:hello"


def test_start_must_say_its_mode(room, talkie):
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        for mode in ({}, {"mode": None}, {"mode": "shout"}, {"mode": ["walkie"]}):
            a.send_json({"type": "start", "mime": WEBM} | mode)
            error = a.receive_json()
            assert error["code"] == "bad_request" and "Missing or unknown mode" in error["detail"]
        pong(a)
    assert talkie.made == []


def test_live_stream_follows_the_talk(room, app, talkie):
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        start(a, mime="audio/mp4")
        talk_id = a.receive_json()["id"]
        a.send_bytes(b"x")
        pong(a)
        assert app._talkie.id == talk_id and talkie.made[0].fmt == "mp4"
        a.send_json({"type": "stop"})
        until(a, "ended")
        assert alice.get(f"/talkie/live/{talk_id}").content == b"MP3:x"
        assert alice.get("/talkie/live/other").status_code == 404
    assert alice.get(f"/talkie/live/{talk_id}").status_code == 403  # no longer in the room (nor connected)


def test_one_talker_at_a_time(room, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        start(a)
        until(a, "ready")
        until(b, "live")
        start(b)
        assert b.receive_json() == {"type": "error", "code": "busy", "detail": "Alice is talking right now"}
        pong(b)  # the socket stays open
        a.send_json({"type": "stop"})
        until(b, "ended")
        start(b)
        assert b.receive_json()["type"] == "ready"
        b.send_json({"type": "stop"})
        until(b, "ended")
    assert len(talkie.made) == 2


def test_walkie_is_live_and_keeps_no_clip(room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        ended = record(a, "walkie", b"hi")
        assert ended["clip"] is None and ended["reason"] == "stopped"
        assert drain(b) == ["live", "ended"]  # no "clip"
        assert bob.get(f"/talkie/live/{ended['id']}").content == b"MP3:hi"
        assert "clip" not in drain(a)
    assert alice.get("/talkie/clips").json() == [] and not any(app.TALKIE_DIR.glob("*"))


def test_messages_are_never_live_and_take_no_lock(room, app, talkie):
    alice, bob, carol = room("alice"), room("bob", "viewer"), room("carol", "viewer")
    with (alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b,
          carol.websocket_connect("/talkie?room=0") as c):
        hello(a), hello(b), hello(c)
        drain(a), drain(b)
        a.send_json({"type": "start", "mime": WEBM, "mode": "message"})
        b.send_json({"type": "start", "mime": WEBM, "mode": "message"})
        assert a.receive_json()["type"] == b.receive_json()["type"] == "ready"  # both at once
        assert app._talkie is None
        with carol.websocket_connect("/talkie") as c2:  # nor does a walkie talk wait for them
            hello(c2)
            assert record(c2, "walkie")["clip"] is None
            assert drain(a)[-1] == drain(b)[-1] == "ended"
        drain(c)
        a.send_bytes(b"from alice")
        b.send_bytes(b"from bob")
        a.send_json({"type": "stop"})
        b.send_json({"type": "stop"})
        mine = until(a, "ended")["clip"]
        assert mine["name"] == "Alice" and until(b, "ended")["clip"]["name"] == "Bob"
        assert drain(c) == ["clip", "clip"]  # nobody else hears of a message until it is kept
        assert "live" not in drain(a) + drain(b)
    assert {c["name"] for c in alice.get("/talkie/clips").json()} == {"Alice", "Bob"}
    assert alice.get(mine["url"]).content == b"MP3:from alice"
    assert alice.get(f"/talkie/live/{mine['id']}").status_code == 404  # never live


def test_message_shorter_than_the_minimum_is_dropped(room, app, talkie, monkeypatch):
    monkeypatch.setattr(app, "TALKIE_MIN_SECONDS", 0.5)
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        assert record(a, "message", b"blip")["clip"] is None
        assert "clip" not in drain(a)
    assert alice.get("/talkie/clips").json() == []


def test_live_audio_goes_only_to_the_room(room, app, talkie):
    alice, bob, carol = room("alice"), room("bob", "viewer"), room("carol", "viewer")
    with alice.websocket_connect("/talkie?room=1") as a, bob.websocket_connect("/talkie?room=0") as b:
        hello(a)
        assert rooms(hello(b)["online"]) == {"Alice": True, "Bob": False}
        drain(a)
        with carol.websocket_connect("/talkie") as c:  # never says: in the room, as the app before the room
            hello(c)
            assert rooms(until(a, "online")["online"]) == {"Alice": True, "Bob": False, "Carol": True}
            a.send_json({"type": "start", "mime": WEBM, "mode": "walkie"})
            talk_id = until(a, "ready")["id"]
            outside, inside = until(b, "live"), until(c, "live")
            assert "url" not in outside and outside["name"] == "Alice"  # who talks, for "Join"
            assert inside["url"] == f"/talkie/live/{talk_id}"
            with bob.websocket_connect("/talkie?room=0") as b2:  # a tab opening mid-talk: who, no audio
                assert hello(b2)["live"] == {"id": talk_id, "user_id": alice.user_id, "name": "Alice"}
            assert bob.get(f"/talkie/live/{talk_id}").status_code == 403
            b.send_json({"type": "room", "in": True})  # Join: the audio comes now
            assert until(b, "live")["url"] == f"/talkie/live/{talk_id}"
            assert rooms(until(a, "online")["online"])["Bob"] is True
            a.send_bytes(b"x")
            a.send_json({"type": "stop"})
            until(b, "ended")
            assert bob.get(f"/talkie/live/{talk_id}").content == b"MP3:x"
            b.send_json({"type": "room", "in": False})
            assert rooms(until(a, "online")["online"])["Bob"] is False
            b.send_json({"type": "room", "in": False})  # no change: nobody is told
            assert drain(a) == []


def test_member_in_the_room_from_any_tab(room, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie?room=0") as a, bob.websocket_connect("/talkie?room=0") as b:
        hello(a), hello(b)
        until(a, "online")
        with bob.websocket_connect("/talkie?room=1") as b2:
            hello(b2)
            assert rooms(until(a, "online")["online"]) == {"Alice": False, "Bob": True}
            b2.close()
            assert rooms(until(a, "online")["online"]) == {"Alice": False, "Bob": False}


def test_walkie_only_from_the_room(room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with alice.websocket_connect("/talkie?room=0") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        a.send_json({"type": "start", "mime": WEBM, "mode": "walkie"})
        assert until(a, "error") == {"type": "error", "code": "not_in_room", "detail": "Open the Walkie to talk live"}
        assert record(a, "message")["clip"]["name"] == "Alice"  # a message needs no room
        a.send_json({"type": "room", "in": True})
        a.send_json({"type": "start", "mime": WEBM, "mode": "walkie"})
        assert until(a, "ready")["type"] == "ready"
        until(b, "live")
        a.send_json({"type": "room", "in": False})  # leaving the Walkie ends the talk
        assert until(b, "ended")["reason"] == "left_room"
        assert app._talkie is None
    assert len(talkie.made) == 2


def test_speaker_talk_is_separate(room, app, talkie, fake_speaker):
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        start(a)
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
        start(a, "message")
        a.receive_json()
        a.send_bytes(b"blip")
        a.send_json({"type": "stop"})
        assert until(a, "ended")["clip"] is None
    assert alice.get("/talkie/clips").json() == [] and not any(app.TALKIE_DIR.glob("*"))


@pytest.mark.parametrize("mode", ["walkie", "message"])
def test_hanging_up_ends_the_talk(mode, room, app, talkie):
    alice, bob = room("alice"), room("bob", "viewer")
    with bob.websocket_connect("/talkie") as b:
        hello(b)
        with alice.websocket_connect("/talkie") as a:
            hello(a)
            start(a, mode)
            a.receive_json()
            a.send_bytes(b"hi")
            pong(a)
            a.close()
            if mode == "walkie":
                ended = until(b, "ended")
                assert ended["reason"] == "disconnected" and ended["clip"] is None
            else:  # what was said is kept
                assert until(b, "clip")["clip"]["name"] == "Alice"
            assert names(until(b, "online")["online"]) == ["Bob"]
    assert app._talkie is None and talkie.made[0].finished


@pytest.mark.parametrize(("limit", "reason"), [("TALKIE_MAX_SECONDS", "max_length"), ("TALK_IDLE_TIMEOUT", "idle")])
def test_timers_end_the_talk(limit, reason, room, app, talkie, monkeypatch):
    monkeypatch.setattr(app, limit, 0.2)
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        start(a)
        a.receive_json()
        assert until(a, "ended")["reason"] == reason
        pong(a)  # a member stays connected after their talk


def test_too_much_audio(room, app, talkie, monkeypatch):
    monkeypatch.setattr(app, "TALK_MAX_RATE", 1)  # 60 bytes for a 60 s talk
    alice = room("alice")
    with alice.websocket_connect("/talkie") as a:
        hello(a)
        start(a)
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
        start(ws)
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "stop"})
        until(ws, "ended")


def test_bad_start(app, as_role, talkie, monkeypatch):
    with as_role("viewer").websocket_connect("/talkie") as ws:
        hello(ws)
        start(ws, mime="audio/wav")
        error = ws.receive_json()
        assert error["code"] == "bad_request" and "Unsupported recording format" in error["detail"]
        monkeypatch.setattr(app, "talk_available", lambda: False)
        start(ws)
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
        return record(ws, "message")["clip"]


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


def test_only_the_author_deletes_a_message(room, app, client, talkie):
    alice, bob, owner = room("alice", "viewer"), room("bob"), room("olivia", "admin")
    with alice.websocket_connect("/talkie") as a, bob.websocket_connect("/talkie") as b:
        hello(a), hello(b)
        clip = record(a, "message")["clip"]
        path = app.TALKIE_DIR / f"{clip['id']}.mp3"
        assert bob.delete(f"/talkie/clips/{clip['id']}").status_code == 403
        assert owner.delete(f"/talkie/clips/{clip['id']}").status_code == 403  # not even the owner
        assert client.delete(f"/talkie/clips/{clip['id']}").status_code == 400  # the API token is no member
        assert path.exists()
        assert alice.delete(f"/talkie/clips/{clip['id']}").status_code == 204
        assert until(a, "clip_deleted") == until(b, "clip_deleted") == {"type": "clip_deleted", "id": clip["id"]}
        assert not path.exists() and app.db.get_clip(clip["id"]) is None
        assert alice.get("/talkie/clips").json() == [] and alice.get(clip["url"]).status_code == 404
        assert alice.delete(f"/talkie/clips/{clip['id']}").status_code == 404
        assert alice.delete("/talkie/clips/nothing").status_code == 404
    logged = [e for e in app.db.activity() if e["action"] == "message delete"]
    assert len(logged) == 1 and logged[0]["actor"] == "Alice"


def test_expired_message_cannot_be_deleted(app, as_role, talkie):
    viewer = as_role("viewer")
    clip = saved_clip(app, viewer)
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat(timespec="seconds")
    with app.db.tx() as db:
        db.execute("UPDATE talkie_clips SET created_at = ?", (old,))
    assert viewer.delete(f"/talkie/clips/{clip['id']}").status_code == 404


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
