from unittest import mock

from conftest import PASSWORD, TOKEN, make_user, session_client
from fastapi.testclient import TestClient


def web(app):
    """A browser before sign-in: no token, sends the web UI's header."""
    return TestClient(app.app, headers={"X-Requested-With": "speaker-web"})


def setup_body(**overrides):
    return {"api_token": TOKEN, "username": "Admin", "display_name": "The Admin", "password": PASSWORD} | overrides


def test_state_needs_setup_until_first_user(anon, app):
    assert anon.get("/auth/state").json() == {"needs_setup": True, "user": None}
    make_user()
    assert anon.get("/auth/state").json() == {"needs_setup": False, "user": None}


def test_setup_checks_api_token(app):
    c = web(app)
    r = c.post("/auth/setup", json=setup_body(api_token="wrong"))
    assert r.status_code == 401 and isinstance(r.json()["detail"], str)
    assert app.db.user_count() == 0


def test_setup_creates_admin_and_signs_in(app):
    c = web(app)
    r = c.post("/auth/setup", json=setup_body())
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["username"] == "admin" and user["role"] == "admin" and user["display_name"] == "The Admin"
    assert user["last_login_at"] is not None and user["disabled"] is False
    assert set(user) == {"id", "username", "display_name", "role", "disabled", "created_at", "last_login_at"}
    state = c.get("/auth/state").json()
    assert state["needs_setup"] is False and state["user"]["id"] == user["id"]
    assert c.get("/users").status_code == 200  # the cookie works as admin


def test_setup_only_once(app):
    make_user()
    r = web(app).post("/auth/setup", json=setup_body(username="intruder"))
    assert r.status_code == 409
    assert [u["username"] for u in app.db.list_users()] == ["alice"]


def test_setup_validates_username_and_password(app):
    c = web(app)
    assert c.post("/auth/setup", json=setup_body(username="no spaces")).status_code == 400
    assert c.post("/auth/setup", json=setup_body(username="ab")).status_code == 400
    assert c.post("/auth/setup", json=setup_body(password="short")).status_code == 400
    assert app.db.user_count() == 0


def test_setup_token_guessing_is_throttled(app):
    c = web(app)
    for _ in range(5):
        assert c.post("/auth/setup", json=setup_body(api_token="guess")).status_code == 401
    r = c.post("/auth/setup", json=setup_body())
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_login_sets_strict_httponly_cookie(app):
    make_user("bob", "operator", "Bob")
    c = web(app)
    r = c.post("/auth/login", json={"username": "BOB", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["username"] == "bob"
    cookie = r.headers["set-cookie"]
    attrs = {part.strip().split("=")[0].lower(): part for part in cookie.split(";")}
    assert cookie.startswith("sid=")
    assert "httponly" in attrs and "secure" not in attrs
    assert attrs["samesite"].split("=")[1].strip().lower() == "strict"
    assert attrs["path"].split("=")[1].strip() == "/"
    assert int(attrs["max-age"].split("=")[1]) == 30 * 24 * 3600
    sid = cookie.split(";")[0].removeprefix("sid=")
    assert len(sid) >= 43  # 32 random bytes, urlsafe base64
    assert c.get("/auth/state").json()["user"]["username"] == "bob"


def test_cookie_is_secure_over_https(app):
    make_user("bob")
    c = TestClient(app.app, base_url="https://testserver")
    r = c.post("/auth/login", json={"username": "bob", "password": PASSWORD})
    assert "secure" in r.headers["set-cookie"].lower()


def test_session_stored_only_as_hash(app):
    make_user("bob")
    c = web(app)
    c.post("/auth/login", json={"username": "bob", "password": PASSWORD})
    sid = c.cookies["sid"]
    with app.db.tx() as db:
        stored = [r[0] for r in db.execute("SELECT token_hash FROM sessions")]
    assert sid not in stored and len(stored) == 1 and len(stored[0]) == 64


def test_login_failures(app):
    make_user("bob")
    make_user("dora", disabled=True)
    c = web(app)
    assert c.post("/auth/login", json={"username": "bob", "password": "wrong-password"}).status_code == 401
    assert c.post("/auth/login", json={"username": "nobody", "password": PASSWORD}).status_code == 401
    r = c.post("/auth/login", json={"username": "dora", "password": PASSWORD})
    assert r.status_code == 401 and "disabled" in r.json()["detail"]
    assert "sid" not in c.cookies


def test_login_throttled_per_ip_and_username(app):
    make_user("bob")
    make_user("carol")
    c = web(app)
    for _ in range(5):
        assert c.post("/auth/login", json={"username": "bob", "password": "nope-nope"}).status_code == 401
    r = c.post("/auth/login", json={"username": "bob", "password": PASSWORD})
    assert r.status_code == 429
    assert 0 < int(r.headers["retry-after"]) <= 300
    assert isinstance(r.json()["detail"], str)
    # Other usernames from the same address are unaffected.
    assert c.post("/auth/login", json={"username": "carol", "password": PASSWORD}).status_code == 200


def test_login_throttle_expires(app, monkeypatch):
    make_user("bob")
    c = web(app)
    now = [1_000_000.0]
    import auth

    monkeypatch.setattr(auth.time, "time", lambda: now[0])
    for _ in range(5):
        c.post("/auth/login", json={"username": "bob", "password": "nope-nope"})
    assert c.post("/auth/login", json={"username": "bob", "password": PASSWORD}).status_code == 429
    now[0] += 301
    assert c.post("/auth/login", json={"username": "bob", "password": PASSWORD}).status_code == 200


def test_successful_login_resets_failures(app):
    make_user("bob")
    c = web(app)
    for _ in range(4):
        c.post("/auth/login", json={"username": "bob", "password": "nope-nope"})
    assert c.post("/auth/login", json={"username": "bob", "password": PASSWORD}).status_code == 200
    for _ in range(4):
        assert c.post("/auth/login", json={"username": "bob", "password": "nope-nope"}).status_code == 401


def test_cookie_state_change_requires_header(app, fake_speaker):
    c = session_client(make_user("op", "operator"), csrf=False)
    assert c.get("/status").status_code == 200  # reads don't need it
    r = c.post("/volume", json={"level": 0.5})
    assert r.status_code == 403 and "X-Requested-With" in r.json()["detail"]
    assert c.post("/volume", json={"level": 0.5}, headers={"X-Requested-With": "other"}).status_code == 403
    assert fake_speaker.volume == 0.2
    assert c.post("/volume", json={"level": 0.5}, headers={"X-Requested-With": "speaker-web"}).status_code == 200


def test_bearer_token_needs_no_header(client):
    assert client.post("/volume", json={"level": 0.3}).status_code == 200


def test_bad_cookie_is_not_signed_in(app):
    c = web(app)
    c.cookies.set("sid", "forged")
    assert c.get("/status").status_code == 401
    assert c.get("/auth/state").json()["user"] is None


def test_logout_ends_only_this_session(app):
    user = make_user("bob", "viewer")
    first, second = session_client(user), session_client(user)
    r = first.post("/auth/logout")
    assert r.status_code == 200
    assert 'sid=""' in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"].lower()
    first.cookies.set("sid", first.sid)
    assert first.get("/status").status_code == 401
    assert second.get("/queue").status_code == 200


def test_logout_all_ends_every_session(app):
    user = make_user("bob", "viewer")
    first, second = session_client(user), session_client(user)
    assert first.post("/auth/logout-all").status_code == 200
    assert second.get("/queue").status_code == 401


def test_logout_requires_sign_in(anon):
    assert anon.post("/auth/logout").status_code == 401


def test_change_password_ends_other_sessions(app):
    user = make_user("bob", "viewer")
    me, other = session_client(user), session_client(user)
    r = me.post("/auth/password", json={"current": PASSWORD, "new": "new password 1"})
    assert r.status_code == 200
    assert me.get("/queue").status_code == 200
    assert other.get("/queue").status_code == 401
    assert web(app).post("/auth/login", json={"username": "bob", "password": PASSWORD}).status_code == 401
    assert web(app).post("/auth/login", json={"username": "bob", "password": "new password 1"}).status_code == 200


def test_change_password_checks_current_and_length(app):
    me = session_client(make_user("bob", "viewer"))
    assert me.post("/auth/password", json={"current": "wrong-one", "new": "new password 1"}).status_code == 401
    assert me.post("/auth/password", json={"current": PASSWORD, "new": "short"}).status_code == 400
    assert me.get("/queue").status_code == 200


def test_change_password_not_for_api_token(client):
    assert client.post("/auth/password", json={"current": "x", "new": "yyyyyyyy"}).status_code == 400


def test_disabled_user_loses_access_immediately(app):
    user = make_user("bob", "operator")
    c = session_client(user)
    app.db.update_user(user["id"], {"disabled": True})
    assert c.get("/status").status_code == 401


def backdated(seconds):
    """Pretend the code inside ran `seconds` ago."""
    import store

    real = store.time.time
    return mock.patch.object(store.time, "time", lambda: real() - seconds)


def test_session_slides_forward(app):
    user = make_user("bob", "viewer")
    c = session_client(user)
    with backdated(2 * 24 * 3600):  # signed in two days ago
        old = session_client(user)
    r = old.get("/queue")
    assert r.status_code == 200 and "sid=" in r.headers.get("set-cookie", "")
    assert "set-cookie" not in c.get("/queue").headers  # fresh sessions aren't rewritten every request


def test_expired_session_rejected(app):
    user = make_user("bob", "viewer")
    with backdated(31 * 24 * 3600):
        c = session_client(user)
    assert c.get("/queue").status_code == 401


def test_password_hash_format(app):
    import auth

    stored = auth.hash_password("hunter2hunter2")
    scheme, n, r, p, salt, digest = stored.split("$")
    assert (scheme, n, r, p) == ("scrypt", str(2**14), "8", "1")
    import base64

    assert len(base64.b64decode(salt)) == 16 and len(base64.b64decode(digest)) == 32
    assert auth.verify_password("hunter2hunter2", stored)
    assert not auth.verify_password("hunter2hunter3", stored)
    assert not auth.verify_password("x", "garbage")


def test_validation_errors_are_strings(client):
    r = client.post("/volume", json={"level": "loud"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and "level" in r.json()["detail"]
