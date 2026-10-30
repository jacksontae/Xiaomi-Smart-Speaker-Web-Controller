"""Sign in with Google: ID token checks against a locally generated key, linking, sign-in and the owner's switch."""
import time

import jwt
import pytest
from conftest import make_user, session_client
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import google_signin

CLIENT_ID = "1234-test.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk(key, kid):
    return jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": kid, "use": "sig",
                                                                                 "alg": "RS256"}


def token(key=KEY, kid="k1", **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1000001", "email": "alice@example.com",
        "email_verified": True, "iat": now, "exp": now + 3600, "jti": f"jti-{time.monotonic_ns()}",
    } | overrides
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def keys(app, monkeypatch):
    """Google's key set as served to the verifier (no network); `.fetches` counts downloads."""
    verifier = google_signin.GoogleVerifier(jwks_url="https://keys.invalid/certs")
    state = type("Keys", (), {"fetches": 0, "set": {"keys": [jwk(KEY, "k1")]}})()

    def fetch():
        state.fetches += 1
        return state.set

    monkeypatch.setattr(verifier.jwks, "fetch_data", fetch)
    monkeypatch.setattr(app, "google_verifier", verifier)
    state.verifier = verifier
    return state


@pytest.fixture
def google_on(app, keys):
    app.settings.google_client_id = CLIENT_ID
    app.settings.google_signin = True
    return keys


def web(app):
    return TestClient(app.app, headers={"X-Requested-With": "speaker-web"})


# --- Token verification ---

def test_verifies_signature_audience_issuer_and_expiry(keys):
    v = keys.verifier
    assert v.verify(token(), CLIENT_ID)["sub"] == "1000001"
    assert v.verify(token(iss="accounts.google.com"), CLIENT_ID)["email"] == "alice@example.com"
    bad = [
        token(key=OTHER_KEY),  # signed by someone else under Google's key id
        token(aud="someone-else.apps.googleusercontent.com"),
        token(iss="https://evil.example.com"),
        token(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200),
        token(email_verified=False),
        token(email_verified=None),
        token(sub=None),
        "not-a-jwt",
    ]
    for credential in bad:
        with pytest.raises(google_signin.InvalidToken):
            v.verify(credential, CLIENT_ID)


def test_rejects_unsigned_and_hmac_tokens(keys):
    claims = jwt.decode(token(), options={"verify_signature": False})
    for credential in (
        jwt.encode(claims, None, algorithm="none", headers={"kid": "k1"}),
        jwt.encode(claims, "x" * 32, algorithm="HS256", headers={"kid": "k1"}),
    ):
        with pytest.raises(google_signin.InvalidToken):
            keys.verifier.verify(credential, CLIENT_ID)


def test_keys_are_cached_and_refetched_for_a_new_key_id(keys):
    v = keys.verifier
    v.verify(token(), CLIENT_ID)
    v.verify(token(), CLIENT_ID)
    assert keys.fetches == 1
    keys.set = {"keys": [jwk(KEY, "k1"), jwk(OTHER_KEY, "k2")]}  # Google rotated in a new key
    v.jwks.cooldown_duration = 0
    assert v.verify(token(key=OTHER_KEY, kid="k2"), CLIENT_ID)["sub"] == "1000001"
    assert keys.fetches == 2


def test_a_token_is_accepted_only_once(keys):
    credential = token()
    keys.verifier.verify(credential, CLIENT_ID)
    with pytest.raises(google_signin.InvalidToken, match="already used"):
        keys.verifier.verify(credential, CLIENT_ID)


def test_unreachable_keys_are_reported_separately(app, monkeypatch):
    verifier = google_signin.GoogleVerifier(jwks_url="https://keys.invalid/certs")

    def down():
        raise jwt.PyJWKClientConnectionError("offline")

    monkeypatch.setattr(verifier.jwks, "fetch_data", down)
    with pytest.raises(google_signin.KeysUnavailable):
        verifier.verify(token(), CLIENT_ID)


# --- Settings and /auth/state ---

def test_state_offers_google_only_when_switched_on(anon, app, client):
    make_user()
    assert anon.get("/auth/state").json()["methods"] == {"password": True, "google": False}
    assert client.post("/settings", json={"google_signin": True}).status_code == 422  # needs a client id
    assert client.post("/settings", json={"google_client_id": "not a client id"}).status_code == 422
    r = client.post("/settings", json={"google_client_id": CLIENT_ID})
    assert r.status_code == 200 and r.json()["settings"]["google_signin"] is False
    assert "google_client_id" not in anon.get("/auth/state").json()
    assert client.post("/settings", json={"google_signin": True}).status_code == 200
    state = anon.get("/auth/state").json()
    assert state["methods"]["google"] is True and state["google_client_id"] == CLIENT_ID
    assert app.load_settings().google_signin is True  # persisted to config.json


def test_switch_is_owner_only(as_role):
    r = as_role("operator").post("/settings", json={"google_signin": False})
    assert r.status_code == 403


# --- Linking ---

def test_link_then_sign_in(app, google_on):
    alice = make_user("alice", "operator")
    c = session_client(alice)
    r = c.post("/me/google", json={"credential": token()})
    assert r.status_code == 200 and r.json()["google_email"] == "alice@example.com"
    assert c.get("/auth/state").json()["user"]["google_email"] == "alice@example.com"

    browser = web(app)
    r = browser.post("/auth/google", json={"credential": token(email="alice.new@example.com")})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == alice["id"] and r.json()["user"]["last_login_at"]
    assert browser.get("/auth/state").json()["user"]["username"] == "alice"
    assert browser.get("/queue").status_code == 200  # a real session
    assert app.db.get_user(alice["id"])["google_email"] == "alice.new@example.com"
    actions = [(a["actor"], a["action"], a["detail"]) for a in app.db.activity()]
    assert ("Alice", "google link", "alice@example.com") in actions
    assert any(a[:2] == ("Alice", "login ok") and a[2].startswith("with Google") for a in actions)


def test_unlinked_google_account_cannot_sign_in(app, google_on):
    make_user("alice")
    r = web(app).post("/auth/google", json={"credential": token()})
    assert r.status_code == 401 and "isn't linked" in r.json()["detail"]
    assert app.db.user_count() == 1  # no self-sign-up
    assert app.db.activity()[0]["action"] == "login failed"


def test_bad_token_cannot_sign_in(app, google_on):
    alice = make_user("alice")
    app.db.link_google(alice["id"], "1000001", "alice@example.com")
    for credential in (token(aud="other.apps.googleusercontent.com"), token(key=OTHER_KEY)):
        r = web(app).post("/auth/google", json={"credential": credential})
        assert r.status_code == 401
        assert "sid" not in r.cookies


def test_failed_google_attempts_are_throttled(app, google_on):
    c = web(app)
    for _ in range(5):
        assert c.post("/auth/google", json={"credential": "garbage"}).status_code == 401
    r = c.post("/auth/google", json={"credential": token()})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_disabled_member_cannot_sign_in_with_google(app, google_on):
    bob = make_user("bob", "viewer", disabled=True)
    app.db.link_google(bob["id"], "1000001", "alice@example.com")
    r = web(app).post("/auth/google", json={"credential": token()})
    assert r.status_code == 401 and "disabled" in r.json()["detail"]


def test_google_account_links_to_one_member(app, google_on):
    alice, bob = make_user("alice"), make_user("bob", "viewer")
    assert session_client(alice).post("/me/google", json={"credential": token()}).status_code == 200
    r = session_client(bob).post("/me/google", json={"credential": token()})
    assert r.status_code == 409
    assert app.db.get_user(bob["id"])["google_email"] is None


def test_switched_off_refuses_sign_in_and_linking(app, keys):
    alice = make_user("alice")
    app.db.link_google(alice["id"], "1000001", "alice@example.com")
    assert web(app).post("/auth/google", json={"credential": token()}).status_code == 409
    assert session_client(alice).post("/me/google", json={"credential": token()}).status_code == 409
    assert keys.fetches == 0


def test_google_unreachable_is_503(app, google_on, monkeypatch):
    def down():
        raise jwt.PyJWKClientConnectionError("offline")

    monkeypatch.setattr(google_on.verifier.jwks, "fetch_data", down)
    r = web(app).post("/auth/google", json={"credential": token()})
    assert r.status_code == 503


def test_api_token_has_no_account_to_link(client, google_on):
    assert client.post("/me/google", json={"credential": token()}).status_code == 400


# --- Unlinking and the last-method guard ---

def test_unlink(app, google_on):
    alice = make_user("alice")
    c = session_client(alice)
    assert c.delete("/me/google").status_code == 404
    c.post("/me/google", json={"credential": token()})
    r = c.delete("/me/google")
    assert r.status_code == 200 and r.json()["google_email"] is None
    assert web(app).post("/auth/google", json={"credential": token()}).status_code == 401
    assert app.db.activity()[1]["action"] == "google unlink"


def test_cannot_unlink_the_only_sign_in_method(app, google_on):
    alice = make_user("alice")
    app.db.link_google(alice["id"], "1000001", "alice@example.com")
    with app.db.tx() as db:  # a member with no password (Google only)
        db.execute("UPDATE users SET password_hash = '' WHERE id = ?", (alice["id"],))
    r = session_client(alice).delete("/me/google")
    assert r.status_code == 409 and "only way" in r.json()["detail"]
    assert app.db.get_user(alice["id"])["google_email"] == "alice@example.com"


def test_unlink_is_allowed_while_google_is_switched_off(app, google_on):
    alice = make_user("alice")
    app.db.link_google(alice["id"], "1000001", "alice@example.com")
    app.settings.google_signin = False
    assert session_client(alice).delete("/me/google").status_code == 200


# --- Storage ---

def test_member_list_shows_linked_email(client, app):
    alice = make_user("alice")
    app.db.link_google(alice["id"], "1000001", "alice@example.com")
    assert [u["google_email"] for u in client.get("/users").json()] == ["alice@example.com"]


def test_migrates_version_2_database_in_place(tmp_path):
    import sqlite3

    import store

    path = tmp_path / "v2.db"
    db = sqlite3.connect(path)
    for statement in store.SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    for statement in store.MIGRATIONS[2]:
        db.execute(statement)
    db.execute("INSERT INTO users (username, display_name, role, password_hash, created_at)"
               " VALUES ('kept', 'Kept', 'admin', 'x', 'x')")
    db.execute("PRAGMA user_version = 2")
    db.commit()
    db.close()

    upgraded = store.Store(path)
    assert upgraded.schema_version() == 3
    user = upgraded.list_users()[0]
    assert user["username"] == "kept" and user["google_email"] is None
    upgraded.link_google(user["id"], "42", "kept@example.com")
    assert store.Store(path).user_by_google("42")["username"] == "kept"
