import pytest
from conftest import PASSWORD, make_user, session_client


def actions(client):
    return [(e["actor"], e["action"], e["detail"]) for e in client.get("/activity").json()]


# --- Quick phrases ---

def test_phrases_crud(app):
    alice = make_user("alice", "operator", "Alice")
    op = session_client(alice)
    r = op.post("/phrases", json={"text": "  ข้าวพร้อมแล้ว  "})
    assert r.status_code == 200
    phrase = r.json()
    assert phrase == {"id": phrase["id"], "text": "ข้าวพร้อมแล้ว", "lang": "th", "created_by": "Alice"}
    assert op.post("/phrases", json={"text": "Dinner", "lang": "en"}).json()["lang"] == "en"
    assert op.post("/phrases", json={"text": " "}).status_code == 400
    assert op.post("/phrases", json={"text": "x" * 1001}).status_code == 400
    viewer = session_client(make_user("vic", "viewer"))
    assert [p["text"] for p in viewer.get("/phrases").json()] == ["ข้าวพร้อมแล้ว", "Dinner"]
    assert viewer.delete(f"/phrases/{phrase['id']}").status_code == 403
    assert op.delete(f"/phrases/{phrase['id']}").status_code == 204
    assert op.delete(f"/phrases/{phrase['id']}").status_code == 404
    assert len(op.get("/phrases").json()) == 1


def test_phrase_by_token_or_deleted_user_has_no_author(client, app):
    assert client.post("/phrases", json={"text": "from curl"}).json()["created_by"] is None
    bob = make_user("bob", "operator")
    session_client(bob).post("/phrases", json={"text": "from bob"})
    client.delete(f"/users/{bob['id']}")
    assert [p["created_by"] for p in client.get("/phrases").json()] == [None, None]


# --- Activity log ---

def test_records_actions_with_actor(client, app, fake_speaker):
    alice = make_user("alice", "admin", "Alice")
    web = session_client(alice)
    web.post("/say", json={"text": "x" * 100})
    client.post("/stop")
    client.post("/play", json={"url": "http://x/a.mp3"})
    web.post("/settings", json={"cache_keep": 5})
    log = actions(client)
    assert ("Alice", "say", "x" * 80) in log
    assert ("api-token", "stop", None) in log
    assert ("api-token", "play", "http://x/a.mp3") in log
    assert ("Alice", "settings change", "cache_keep=5") in log


def test_records_login_logout_and_password(app):
    make_user("bob", "viewer", "Bob")
    from fastapi.testclient import TestClient

    c = TestClient(app.app, headers={"X-Requested-With": "speaker-web"})
    c.post("/auth/login", json={"username": "bob", "password": "wrong-password"})
    c.post("/auth/login", json={"username": "bob", "password": PASSWORD})
    c.post("/auth/password", json={"current": PASSWORD, "new": "new password 1"})
    c.post("/auth/logout")
    log = [(e["actor"], e["action"]) for e in app.db.activity()]
    assert log == [("Bob", "logout"), ("Bob", "password change"), ("Bob", "login ok"), ("system", "login failed")]
    assert "bob" in app.db.activity()[-1]["detail"]


def test_unknown_username_failures_are_coalesced(app):
    from fastapi.testclient import TestClient

    c = TestClient(app.app)
    for name in ("ghost1", "ghost2", "ghost3"):
        c.post("/auth/login", json={"username": name, "password": "whatever-1"})
    rows = app.db.activity()
    assert len(rows) == 1 and rows[0]["detail"].startswith("ghost3")


def test_records_member_changes(client):
    r = client.post("/users", json={"username": "bob", "display_name": "Bob", "password": PASSWORD,
                                    "role": "viewer"})
    bob = r.json()
    client.patch(f"/users/{bob['id']}", json={"role": "operator", "password": "another pass"})
    client.delete(f"/users/{bob['id']}")
    log = actions(client)[:3]
    assert log[2] == ("api-token", "member create", "bob (viewer)")
    assert log[1] == ("api-token", "member update", "bob: role=operator, password")
    assert log[0] == ("api-token", "member delete", "bob")
    assert all(PASSWORD not in (d or "") and "another pass" not in (d or "") for _, _, d in actions(client))


def test_records_playlist_play_and_queue_skip(client, app, fake_speaker):
    pl = app.db.create_playlist("Party")
    for text in ("one", "two"):
        app.db.add_item(pl["id"], {"kind": "tts", "source": text, "title": text, "lang": "en"}, 10)
    client.post(f"/playlists/{pl['id']}/play", json={})
    client.post("/queue/next")
    log = actions(client)
    assert log[0] == ("api-token", "queue skip", "next: two")
    assert log[1] == ("api-token", "playlist play", "Party")


def test_volume_coalesced_per_actor_within_10s(client, app, monkeypatch):
    import store

    now = [5_000.0]
    monkeypatch.setattr(store.time, "time", lambda: now[0])
    alice = session_client(make_user("alice", "operator", "Alice"))
    for level in (0.1, 0.2, 0.3):
        client.post("/volume", json={"level": level})
        now[0] += 3
    alice.post("/volume", json={"level": 0.9})
    log = [e for e in actions(client) if e[1] == "volume"]
    assert log == [("Alice", "volume", "90%"), ("api-token", "volume", "30%")]
    now[0] += 10
    client.post("/volume", json={"level": 0.5})
    log = [e for e in actions(client) if e[1] == "volume"]
    assert log[0] == ("api-token", "volume", "50%") and len(log) == 3


def test_activity_paging(client, app):
    for i in range(7):
        app.db.log("system", "test", str(i))
    page = client.get("/activity", params={"limit": 3}).json()
    assert [e["detail"] for e in page] == ["6", "5", "4"]
    assert set(page[0]) == {"id", "at", "actor", "action", "detail"}
    older = client.get("/activity", params={"limit": 3, "before_id": page[-1]["id"]}).json()
    assert [e["detail"] for e in older] == ["3", "2", "1"]
    assert client.get("/activity", params={"limit": 0}).status_code == 422


def test_activity_capped(app, monkeypatch):
    import store

    monkeypatch.setattr(store, "ACTIVITY_KEEP", 5)
    for i in range(12):
        app.db.log("system", "test", str(i))
    rows = app.db.activity(limit=100)
    assert [r["detail"] for r in rows] == ["11", "10", "9", "8", "7"]


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_activity_is_admin_only(as_role, role):
    assert as_role(role).get("/activity").status_code == 403


def test_schema_version_and_tables(app):
    assert app.db.schema_version() == 3
    with app.db.tx() as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"users", "sessions", "playlists", "playlist_items", "phrases", "activity", "schedules",
            "radio_favorites", "media_files"} <= tables
