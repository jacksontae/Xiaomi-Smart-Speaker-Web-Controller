"""Personal playlists and files: owner_id NULL = shared; else only the owner and admins see or change it.
Viewers make personal items, skip through the speaker's queue and search music sources; they never edit shared."""
import sqlite3

import pytest
from conftest import make_user, session_client
from test_queue import downloads  # noqa: F401 - fixture
from test_sources import MP3, upload

import store

A, B = "aaaaaaaaaaa", "bbbbbbbbbbb"
EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]


@pytest.fixture
def people(app):
    """Signed-in browsers: two viewers, an operator and an admin (each knows its user row as `.user`)."""
    out = {}
    for name, role in (("ann", "viewer"), ("ben", "viewer"), ("ops", "operator"), ("root", "admin")):
        user = make_user(name, role, name.title())
        out[name] = session_client(user)
        out[name].user = user
    return out


def new_playlist(c, name="Mine", **body):
    r = c.post("/playlists", json={"name": name, **body})
    assert r.status_code == 200, r.text
    return r.json()


def tts(c, pid, text="hello"):
    return c.post(f"/playlists/{pid}/items", json={"kind": "tts", "source": text})


def names(c):
    return [p["name"] for p in c.get("/playlists").json()]


def file_ids(c):
    return [f["id"] for f in c.get("/files").json()["items"]]


# --- Playlists ---

def test_who_owns_a_new_playlist(people, client):
    ann, ops, root = people["ann"], people["ops"], people["root"]
    pl = new_playlist(ann, personal=False)  # a viewer can't make a shared one, whatever they ask
    assert pl["owner_id"] == ann.user["id"] and pl["owner_name"] == "Ann" and pl["mine"] and pl["can_edit"]
    shared = new_playlist(ops, "Shop")
    assert shared["owner_id"] is None and shared["owner_name"] is None and not shared["mine"]
    own = new_playlist(ops, "Ops own", personal=True)
    assert own["owner_id"] == ops.user["id"] and own["mine"]
    assert new_playlist(root, "Root own", personal=True)["owner_id"] == root.user["id"]
    assert new_playlist(client, "By token")["owner_id"] is None
    r = client.post("/playlists", json={"name": "x", "personal": True})
    assert r.status_code == 400 and "token" in r.json()["detail"]


def test_personal_playlist_visibility(people):
    ann, ben, ops, root = people["ann"], people["ben"], people["ops"], people["root"]
    mine = new_playlist(ann, "Ann's")
    new_playlist(ops, "Shared")
    new_playlist(ops, "Ops own", personal=True)
    assert names(ann) == ["Ann's", "Shared"]
    assert names(ben) == ["Shared"]
    assert names(ops) == ["Ops own", "Shared"]  # operators don't see other members' personal playlists
    listed = {p["name"]: p for p in root.get("/playlists").json()}
    assert set(listed) == {"Ann's", "Shared", "Ops own"}  # admins see everything, with the owner's name
    assert listed["Ann's"]["owner_name"] == "Ann" and not listed["Ann's"]["mine"] and listed["Ann's"]["can_edit"]
    assert listed["Ops own"]["owner_name"] == "Ops"
    pid = mine["id"]
    for c in (ben, ops):  # someone else's personal playlist looks missing, whatever they try
        assert c.get(f"/playlists/{pid}").status_code == 404
        assert c.patch(f"/playlists/{pid}", json={"name": "x"}).status_code == 404
        assert tts(c, pid).status_code == 404
        assert c.put(f"/playlists/{pid}/order", json={"item_ids": []}).status_code == 404
        assert c.delete(f"/playlists/{pid}/items/1").status_code == 404
        assert c.delete(f"/playlists/{pid}").status_code == 404
    assert ops.post(f"/playlists/{pid}/play", json={}).status_code == 404
    assert ann.get(f"/playlists/{pid}").json()["mine"] is True
    assert root.get(f"/playlists/{pid}").json()["owner_name"] == "Ann"


def test_owner_edits_own_playlist(people):
    ann = people["ann"]
    pid = new_playlist(ann)["id"]
    first, second = tts(ann, pid, "one").json(), tts(ann, pid, "two").json()
    assert ann.patch(f"/playlists/{pid}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    order = ann.put(f"/playlists/{pid}/order", json={"item_ids": [second["id"], first["id"]]}).json()
    assert [i["source"] for i in order["items"]] == ["two", "one"] and order["mine"]
    assert ann.delete(f"/playlists/{pid}/items/{first['id']}").status_code == 204
    assert ann.delete(f"/playlists/{pid}").status_code == 204
    assert ann.get(f"/playlists/{pid}").status_code == 404


def test_admin_edits_anyones_personal_playlist(people):
    ann, root = people["ann"], people["root"]
    pid = new_playlist(ann)["id"]
    assert tts(root, pid).status_code == 200
    assert root.patch(f"/playlists/{pid}", json={"name": "By admin"}).status_code == 200
    assert ann.get(f"/playlists/{pid}").json()["name"] == "By admin"
    assert root.delete(f"/playlists/{pid}").status_code == 204


def test_viewer_cannot_edit_shared_playlist(people):
    ann, ops = people["ann"], people["ops"]
    shared = new_playlist(ops, "Shop")
    pid, item = shared["id"], tts(ops, shared["id"]).json()
    got = ann.get(f"/playlists/{pid}").json()
    assert got["can_edit"] is False and got["mine"] is False and len(got["items"]) == 1
    assert ann.patch(f"/playlists/{pid}", json={"name": "x"}).status_code == 403
    assert tts(ann, pid).status_code == 403
    assert ann.put(f"/playlists/{pid}/order", json={"item_ids": [item["id"]]}).status_code == 403
    assert ann.delete(f"/playlists/{pid}/items/{item['id']}").status_code == 403
    assert ann.delete(f"/playlists/{pid}").status_code == 403
    assert ann.post(f"/playlists/{pid}/play", json={}).status_code == 403  # the speaker stays operator+
    assert ops.get(f"/playlists/{pid}").json()["items"] == got["items"]  # nothing changed


def test_another_operator_edits_shared_playlist(people, app):
    pid = new_playlist(people["ops"], "Shop")["id"]
    other = session_client(make_user("ola", "operator"))
    assert tts(other, pid).status_code == 200
    assert other.delete(f"/playlists/{pid}").status_code == 204


def test_admin_plays_personal_playlist_on_speaker(people, app, fake_speaker):
    ann, root = people["ann"], people["root"]
    pid = new_playlist(ann)["id"]
    tts(ann, pid)
    assert root.post(f"/playlists/{pid}/play", json={}).status_code == 200
    assert len(fake_speaker.media_controller.loads) == 1
    own = new_playlist(people["ops"], "Ops own", personal=True)["id"]
    tts(people["ops"], own)
    assert people["ops"].post(f"/playlists/{own}/play", json={}).status_code == 200


# --- File items in playlists follow the playlist owner's view ---

def test_file_items_respect_visibility(people):
    ann, ben, ops, root = people["ann"], people["ben"], people["ops"], people["root"]
    anns, bens, shared = upload(ann).json(), upload(ben).json(), upload(ops).json()
    roots = upload(root, personal=1).json()

    def add_file(c, pid, f):
        return c.post(f"/playlists/{pid}/items", json={"kind": "file", "source": str(f["id"])})

    ann_pl = new_playlist(ann)["id"]
    assert add_file(ann, ann_pl, anns).status_code == 200
    assert add_file(ann, ann_pl, shared).status_code == 200
    assert add_file(ann, ann_pl, bens).status_code == 400  # not hers: as if it didn't exist
    assert add_file(root, ann_pl, roots).status_code == 400  # the admin sees it, but Ann (the owner) wouldn't
    assert add_file(root, ann_pl, anns).status_code == 200  # an admin may add the owner's own file
    shop = new_playlist(ops, "Shop")["id"]
    assert add_file(ops, shop, shared).status_code == 200
    assert add_file(ops, shop, anns).status_code == 400
    assert add_file(root, shop, anns).status_code == 400  # a shared playlist holds shared files only
    assert add_file(root, shop, roots).status_code == 400


# --- Files ---

def test_upload_ownership(people, client):
    ann, ops, root = people["ann"], people["ops"], people["root"]
    f = upload(ann).json()
    assert f["owner_id"] == ann.user["id"] and f["owner_name"] == "Ann" and f["mine"] and f["can_edit"]
    assert f["uploader"] == "Ann" and f["uploader_id"] == ann.user["id"]
    shared = upload(ops).json()
    assert shared["owner_id"] is None and shared["owner_name"] is None and shared["uploader"] == "Ops"
    assert upload(ops, personal=1).json()["owner_id"] == ops.user["id"]
    assert upload(root, personal="true").json()["owner_id"] == root.user["id"]
    assert upload(client).json()["owner_id"] is None
    r = upload(client, personal=1)
    assert r.status_code == 400 and "token" in r.json()["detail"]


def test_personal_file_visibility(people, app):
    ann, ben, ops, root = people["ann"], people["ben"], people["ops"], people["root"]
    anns, shared = upload(ann).json(), upload(ops).json()
    assert file_ids(ann) == [shared["id"], anns["id"]]
    assert file_ids(ben) == [shared["id"]]
    assert file_ids(ops) == [shared["id"]]
    listing = {f["id"]: f for f in root.get("/files").json()["items"]}
    assert set(listing) == {anns["id"], shared["id"]}
    assert listing[anns["id"]]["owner_name"] == "Ann" and listing[anns["id"]]["can_edit"]
    assert ben.get("/files").json()["used"] == 2 * len(MP3)  # the quota stays one shared pool
    fid = anns["id"]
    for c in (ben, ops):
        assert c.patch(f"/files/{fid}", json={"title": "x"}).status_code == 404
        assert c.delete(f"/files/{fid}").status_code == 404
    assert ops.post(f"/files/{fid}/play", json={}).status_code == 404
    assert ann.patch(f"/files/{fid}", json={"title": "Ann's song"}).json()["title"] == "Ann's song"
    assert root.patch(f"/files/{fid}", json={"title": "Fixed"}).status_code == 200
    stored = app.db.get_file(fid)["stored_name"]
    assert ann.delete(f"/files/{fid}").status_code == 204 and not (app.MEDIA_DIR / stored).exists()


def test_viewer_cannot_edit_shared_file(people):
    ann, ops = people["ann"], people["ops"]
    shared = upload(ops).json()
    assert [f["can_edit"] for f in ann.get("/files").json()["items"]] == [False]
    assert ann.patch(f"/files/{shared['id']}", json={"title": "x"}).status_code == 403
    assert ann.delete(f"/files/{shared['id']}").status_code == 403
    assert ann.post(f"/files/{shared['id']}/play", json={}).status_code == 403


def test_admin_deletes_personal_file_and_its_items(people, app):
    ann, root = people["ann"], people["root"]
    f = upload(ann).json()
    pid = new_playlist(ann)["id"]
    ann.post(f"/playlists/{pid}/items", json={"kind": "file", "source": str(f["id"])})
    assert root.delete(f"/files/{f['id']}").status_code == 204
    assert ann.get(f"/playlists/{pid}").json()["items"] == []


# --- Deleting a member removes their personal things ---

def test_deleting_member_removes_personal_items(people, app, client):
    ann, ops, root = people["ann"], people["ops"], people["root"]
    mine, shared_file = upload(ann).json(), upload(ops).json()
    pid = new_playlist(ann)["id"]
    ann.post(f"/playlists/{pid}/items", json={"kind": "file", "source": str(mine["id"])})
    shop = new_playlist(ops, "Shop")["id"]
    tts(ops, shop)
    stored = app.db.get_file(mine["id"])["stored_name"]
    sched = root.post("/schedules", json={"name": "Shop", "action": "playlist", "playlist_id": shop,
                                          "time": "12:00", "days": EVERY_DAY})
    assert sched.status_code == 200, sched.text
    with app.db.tx() as db:  # schedules only take shared playlists now; one from before points at Ann's
        db.execute("UPDATE schedules SET playlist_id = ? WHERE id = ?", (pid, sched.json()["id"]))

    assert root.delete(f"/users/{ann.user['id']}").status_code == 204
    assert app.db.get_playlist(pid) is None and app.db.get_file(mine["id"]) is None
    assert not (app.MEDIA_DIR / stored).exists()
    assert [p["name"] for p in root.get("/playlists").json()] == ["Shop"]
    assert [f["id"] for f in root.get("/files").json()["items"]] == [shared_file["id"]]
    s = app.db.get_schedule(sched.json()["id"])
    assert s["enabled"] is False and s["playlist_id"] is None and s["next_run"] is None
    with app.db.tx() as db:
        assert db.execute("SELECT COUNT(*) FROM playlist_items WHERE playlist_id = ?", (pid,)).fetchone()[0] == 0


def test_deleting_member_keeps_their_shared_uploads(people, app):
    ops, root = people["ops"], people["root"]
    f = upload(ops).json()
    assert root.delete(f"/users/{ops.user['id']}").status_code == 204
    left = root.get("/files").json()["items"]
    assert [x["id"] for x in left] == [f["id"]] and left[0]["uploader"] is None and left[0]["owner_id"] is None
    assert (app.MEDIA_DIR / app.db.get_file(f["id"])["stored_name"]).exists()


def test_store_delete_user_returns_files(app):
    user = make_user("gone", "viewer")
    app.db.add_file("x.mp3", "X", "x.mp3", "audio/mpeg", 3, None, user["id"], user["id"])
    app.db.add_file("y.mp3", "Y", "y.mp3", "audio/mpeg", 3, None, user["id"])  # shared: stays
    assert app.db.delete_user(user["id"]) == ["x.mp3"]
    assert app.db.delete_user(user["id"]) is None
    assert [f["title"] for f in app.db.list_files()] == ["Y"]


# --- Schedules can't reach someone else's personal playlist ---

def test_schedules_take_shared_playlists_only(people):
    ann, ops, root = people["ann"], people["ops"], people["root"]
    pid = new_playlist(ann)["id"]
    body = {"name": "x", "action": "playlist", "playlist_id": pid, "time": "12:00", "days": EVERY_DAY}
    r = ops.post("/schedules", json=body)
    assert r.status_code == 400 and r.json()["detail"] == "Unknown playlist"
    r = root.post("/schedules", json=body)  # an owner sees it, but a member's playlist can't be scheduled
    assert r.status_code == 400 and r.json()["detail"] == "Schedules play shared playlists only"
    shared = new_playlist(ops, "Shop")["id"]
    made = root.post("/schedules", json=body | {"playlist_id": shared})
    assert made.status_code == 200
    sid = made.json()["id"]
    assert ops.patch(f"/schedules/{sid}", json={"name": "Renamed"}).status_code == 200
    assert root.patch(f"/schedules/{sid}", json={"playlist_id": pid}).status_code == 400


# --- Viewers and the speaker's queue ---

def test_viewer_skips_through_the_speaker_queue(people, app, fake_speaker, downloads):  # noqa: F811
    ann, ops, root = people["ann"], people["ops"], people["root"]
    pid = new_playlist(ops, "Shop")["id"]
    for vid in (A, B):
        app.db.add_item(pid, {"kind": "youtube", "source": vid, "title": f"Song {vid[0]}"}, 100)
    assert ops.post(f"/playlists/{pid}/play", json={}).status_code == 200
    assert ann.post("/queue/next").json()["index"] == 1
    assert f"/yt/{B}.m4a?" in fake_speaker.media_controller.loads[-1]["url"]
    assert ann.post("/queue/prev").json()["index"] == 0
    assert ann.post("/queue/jump", json={"index": 1}).json()["index"] == 1
    log = [(e["actor"], e["action"], e["detail"]) for e in root.get("/activity").json()]
    assert ("Ann", "queue skip", "next: Song b") in log and ("Ann", "queue skip", "jump: Song b") in log
    for path, body in (("/queue/clear", None), ("/stop", None), ("/volume", {"level": 0.5}),
                       ("/pause", None), ("/say", {"text": "hi"})):
        assert ann.post(path, json=body).status_code == 403, path
    assert ann.patch("/queue", json={"shuffle": True}).status_code == 403


def test_viewer_searches_music_sources(people, app, monkeypatch):
    monkeypatch.setattr(app, "yt_search", lambda q, limit: [{"video_id": A, "title": q}])
    r = people["ann"].get("/youtube/search", params={"q": "piano"})
    assert r.status_code == 200 and r.json() == [{"video_id": A, "title": "piano"}]


# --- Migration ---

def test_migration_from_5_keeps_rows_shared(tmp_path):
    path = tmp_path / "v5.db"
    db = sqlite3.connect(path)
    for statement in store.SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    for version in range(2, 6):
        for statement in store.MIGRATIONS[version]:
            db.execute(statement)
    db.execute("INSERT INTO users (id, username, display_name, role, password_hash, created_at)"
               " VALUES (3, 'op', 'Op', 'operator', 'x', 'x')")
    db.execute("INSERT INTO playlists (id, name, created_at, updated_at) VALUES (1, 'Old', 'x', 'x')")
    db.execute("INSERT INTO media_files (id, stored_name, title, original_name, content_type, size, owner_id,"
               " created_at) VALUES (5, 's.mp3', 'Song', 's.mp3', 'audio/mpeg', 10, 3, 'x')")
    db.execute("PRAGMA user_version = 5")
    db.commit()
    db.close()

    upgraded = store.Store(path)
    assert upgraded.schema_version() == store.SCHEMA_VERSION
    pl = upgraded.get_playlist(1)
    assert pl["owner_id"] is None and pl["owner_name"] is None
    f = upgraded.get_file(5)
    assert f["owner_id"] is None and f["uploader_id"] == 3 and f["uploader"] == "Op"  # the uploader is kept
    assert upgraded.delete_user(3) == []  # their old uploads were shared, so they stay
    assert upgraded.get_file(5)["uploader_id"] is None and upgraded.get_playlist(1) is not None
    assert store.Store(path).schema_version() == store.SCHEMA_VERSION  # reopening doesn't migrate again
