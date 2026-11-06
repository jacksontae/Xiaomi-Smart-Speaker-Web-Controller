"""Members download their own data (GET /me/export) and delete their own account (DELETE /me)."""
import pytest
from conftest import make_user, session_client
from test_sources import upload

from server import config, core

FEED = "https://feeds.example.com/show.xml"


@pytest.fixture
def people(app):
    """Signed-in browsers for a viewer, another viewer and an owner, each with personal things."""
    out = {}
    for name, role in (("ann", "viewer"), ("ben", "viewer"), ("root", "admin")):
        user = make_user(name, role, name.title())
        out[name] = session_client(user)
        out[name].user = user
    return out


def give_things(app, c, tag):
    """A personal playlist, file, podcast subscription and Talkie clip for the member behind `c`."""
    uid = c.user["id"]
    pl = c.post("/playlists", json={"name": f"{tag} list"}).json()
    c.post(f"/playlists/{pl['id']}/items", json={"kind": "tts", "source": f"{tag} says hi"})
    f = upload(c, name=f"{tag}.mp3").json()
    core.db.add_sub(uid, f"{FEED}?{tag}", f"{tag} show")
    config.TALKIE_DIR.mkdir(parents=True, exist_ok=True)
    (config.TALKIE_DIR / f"{tag}.mp3").write_bytes(b"clip")
    core.db.add_clip(f"clip-{tag}", uid, 3.5, f"{tag}.mp3")
    return pl, f


def delete_me(c, confirm):
    return c.request("DELETE", "/me", json={"confirm": confirm})


# --- Export ---

def test_export_has_my_data_and_nothing_of_others(people, app):
    ann, ben = people["ann"], people["ben"]
    give_things(app, ann, "ann")
    give_things(app, ben, "ben")
    ann.patch("/me", json={"display_name": "Annie"})
    ben.patch("/me", json={"display_name": "Benny"})
    core.db.log("Annie", "say", "hello from Annie")
    core.db.log("Benny", "say", "hello from Benny")

    r = ann.get("/me/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    disposition = r.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="speaker-my-data-') and disposition.endswith('.json"')
    data = r.json()
    assert data["profile"] == {"username": "ann", "display_name": "Annie", "role": "viewer",
                               "created_at": ann.user["created_at"], "last_login_at": None, "google_email": None}
    assert [p["name"] for p in data["playlists"]] == ["ann list"]
    assert data["playlists"][0]["items"][0]["source"] == "ann says hi"
    assert [(f["original_name"], f["size"], f["personal"]) for f in data["files"]] == [("ann.mp3", 210, True)]
    assert [s["title"] for s in data["podcast_subscriptions"]] == ["ann show"]
    assert [c["id"] for c in data["talkie_clips"]] == ["clip-ann"]
    assert [s["current"] for s in data["sessions"]] == [True]
    assert set(data["sessions"][0]) == {"created_at", "last_seen_at", "expires_at", "current"}
    assert data["passkeys"] == []
    # rows under her current name (`actor` is a name, not an id: the rename itself was logged as "Ann")
    assert [(a["action"], a["detail"]) for a in data["activity"]] == [("say", "hello from Annie")]

    text = r.text
    for secret in ("password_hash", "token_hash", "public_key", "credential_id", "stored_name", ann.sid):
        assert secret not in text
    assert "ben" not in text.lower()  # Ben's playlist, file, show, clip and activity stay out
    # the download itself is logged, as the member
    last = core.db.activity(1)[0]
    assert (last["actor"], last["action"], last["detail"]) == ("Annie", "data export", None)


def test_export_lists_passkeys_without_key_material(people, app):
    ann = people["ann"]
    cred = {"credential_id": "cred-1", "public_key": b"\x01\x02", "sign_count": 0, "transports": ["internal"],
            "backed_up": True}
    core.db.add_passkey(ann.user["id"], "handle-1", "Ann's phone", cred)
    [passkey] = ann.get("/me/export").json()["passkeys"]
    assert passkey == {"name": "Ann's phone", "backed_up": True, "created_at": passkey["created_at"],
                       "last_used_at": None}


def test_export_skips_activity_when_another_member_has_the_same_name(people, app):
    ann = people["ann"]
    make_user("ann2", "viewer", "Ann")
    core.db.log("Ann", "say", "not necessarily mine")
    assert ann.get("/me/export").json()["activity"] == []


def test_export_needs_a_signed_in_member(people, client, anon):
    assert anon.get("/me/export").status_code == 401
    r = client.get("/me/export")
    assert r.status_code == 400 and r.json()["detail"] == "The API token is not a user account"


# --- Delete my account ---

def test_delete_me_removes_everything_personal(people, app):
    ann, ben, root = people["ann"], people["ben"], people["root"]
    pl, f = give_things(app, ann, "ann")
    give_things(app, ben, "ben")
    stored = core.db.get_file(f["id"])["stored_name"]
    elsewhere = session_client(ann.user)
    uid = ann.user["id"]

    r = delete_me(ann, " ANN ")  # case and spaces don't matter
    assert r.status_code == 204 and r.content == b""
    assert 'sid=""' in r.headers["set-cookie"] and "Max-Age=0" in r.headers["set-cookie"]
    assert core.db.get_user(uid) is None
    assert ann.get("/status").status_code == 401 and elsewhere.get("/status").status_code == 401
    assert core.db.get_playlist(pl["id"]) is None and core.db.get_file(f["id"]) is None
    assert not (config.MEDIA_DIR / stored).exists() and not (config.TALKIE_DIR / "ann.mp3").exists()
    assert core.db.list_subs(uid) == [] and core.db.get_clip("clip-ann") is None
    with core.db.tx() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (uid,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM passkeys WHERE user_id = ?", (uid,)).fetchone()[0] == 0
    # other members keep theirs
    assert [p["name"] for p in ben.get("/playlists").json()] == ["ben list"]
    assert core.db.get_clip("clip-ben") is not None and (config.TALKIE_DIR / "ben.mp3").exists()
    assert len(core.db.list_subs(ben.user["id"])) == 1
    entry = root.get("/activity").json()[0]
    assert (entry["actor"], entry["action"], entry["detail"]) == ("Ann", "member delete", "ann (own account)")


def test_delete_me_needs_the_right_username(people, app):
    ann = people["ann"]
    r = delete_me(ann, "ben")
    assert r.status_code == 400 and r.json()["detail"] == "Type your username to confirm"
    assert delete_me(ann, "").status_code == 400
    assert ann.request("DELETE", "/me", json={}).status_code == 422
    assert core.db.get_user(ann.user["id"]) is not None
    assert ann.get("/status").status_code == 200


def test_last_owner_cannot_delete_themselves(people, app):
    root = people["root"]
    r = delete_me(root, "root")
    assert r.status_code == 409
    assert r.json()["detail"] == "You're the only owner; make another member an owner first"
    assert root.get("/users").status_code == 200
    make_user("boss", "admin", disabled=True)  # a disabled owner doesn't count
    assert delete_me(root, "root").status_code == 409
    make_user("boss2", "admin")
    assert delete_me(root, "root").status_code == 204


def test_delete_me_needs_a_signed_in_member(people, client, anon, app):
    assert anon.request("DELETE", "/me", json={"confirm": "ann"}).status_code == 401
    r = client.request("DELETE", "/me", json={"confirm": "api-token"})
    assert r.status_code == 400 and r.json()["detail"] == "The API token is not a user account"
    no_csrf = session_client(people["ann"].user, csrf=False)
    assert delete_me(no_csrf, "ann").status_code == 403
    assert core.db.get_user(people["ann"].user["id"]) is not None
