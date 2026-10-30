"""Passkeys: real WebAuthn ceremonies against a software authenticator (P-256, "none" attestation), no browser."""
import base64
import hashlib
import json
import secrets
import sqlite3

import cbor2
import pytest
from conftest import make_user, session_client
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import passkeys
import store

BASE_URL = "https://speaker.example.com"
RP_ID, ORIGIN = "speaker.example.com", "https://speaker.example.com"
UP, UV, AT = 0x01, 0x04, 0x40


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class SoftKey:
    """A minimal platform authenticator: makes and uses one discoverable credential."""

    def __init__(self, rp_id=RP_ID, origin=ORIGIN):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(16)
        self.rp_id, self.origin = rp_id, origin
        self.sign_count = 0
        self.user_handle = None

    def _cose_key(self):
        nums = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})

    def _auth_data(self, flags, attested=False):
        data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + self.sign_count.to_bytes(4, "big")
        if attested:
            cid = self.credential_id
            data += b"\0" * 16 + len(cid).to_bytes(2, "big") + cid + self._cose_key()
        return data

    def _client_data(self, kind, challenge, origin):
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin or self.origin}).encode()

    def create(self, options, origin=None):
        """navigator.credentials.create() -> the JSON the frontend posts to /me/passkeys."""
        pk = options["publicKey"]
        self.user_handle = pk["user"]["id"]
        client_data = self._client_data("webauthn.create", pk["challenge"], origin)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": self._auth_data(UP | UV | AT, True)})
        return {
            "id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64(client_data), "attestationObject": b64(attestation),
                         "transports": ["internal", "hybrid"]},
            "clientExtensionResults": {},
        }

    def get(self, options, origin=None, step=1):
        """navigator.credentials.get() -> the JSON the frontend posts to /auth/passkey/verify."""
        self.sign_count += step
        client_data = self._client_data("webauthn.get", options["publicKey"]["challenge"], origin)
        auth_data = self._auth_data(UP | UV)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64(client_data), "authenticatorData": b64(auth_data),
                         "signature": b64(signature), "userHandle": self.user_handle},
            "clientExtensionResults": {},
        }


@pytest.fixture
def https(app):
    """Serve on an HTTPS origin, the only kind (besides localhost) where browsers offer passkeys."""
    app.settings.public_base_url = BASE_URL
    app.passkey_challenges = passkeys.Challenges()
    return app


def web(app):
    return TestClient(app.app, headers={"X-Requested-With": "speaker-web"})


def register(c, key=None, name=None):
    key = key or SoftKey()
    options = c.post("/me/passkeys/options").json()
    r = c.post("/me/passkeys", json={"credential": key.create(options)} | ({"name": name} if name else {}))
    assert r.status_code == 200, r.text
    return key, r.json()


def sign_in(app, key, **kwargs):
    browser = web(app)
    options = browser.post("/auth/passkey/options").json()
    r = browser.post("/auth/passkey/verify", json={"credential": key.get(options, **kwargs)})
    return browser, r


# --- Relying party ---

@pytest.mark.parametrize(("url", "expected"), [
    ("https://speaker.example.com", ("speaker.example.com", "https://speaker.example.com")),
    ("https://Speaker.Example.com:8443", ("speaker.example.com", "https://speaker.example.com:8443")),
    ("http://localhost:8103", ("localhost", "http://localhost:8103")),
    ("http://speaker.example.com", None),  # browsers refuse passkeys on plain http
    ("https://192.0.2.20", None),  # RP IDs are domain names
    ("http://192.0.2.20:8090", None),
    (None, None),
])
def test_relying_party_comes_from_public_base_url(url, expected):
    rp = passkeys.relying_party(url, "Speaker")
    assert (rp and (rp.id, rp.origin)) == expected


def test_state_offers_passkeys_only_where_usable(anon, app, client):
    assert anon.get("/auth/state").json()["methods"] == {"password": True, "passkey": False}  # http base URL
    assert anon.post("/auth/passkey/options").status_code == 409
    client.post("/settings", json={"public_base_url": BASE_URL})
    assert anon.get("/auth/state").json()["methods"]["passkey"] is True
    client.post("/settings", json={"passkey_signin": False})
    assert anon.get("/auth/state").json()["methods"]["passkey"] is False
    assert anon.post("/auth/passkey/options").status_code == 409


def test_options_shape(https):
    alice = make_user("alice", "operator")
    c = session_client(alice)
    key, _ = register(c)
    create = c.post("/me/passkeys/options").json()["publicKey"]
    assert create["rp"] == {"id": RP_ID, "name": https.settings.speaker_name}
    assert create["user"]["name"] == "alice" and create["user"]["id"] == key.user_handle  # same handle every time
    assert create["authenticatorSelection"]["residentKey"] == "required"
    assert create["authenticatorSelection"]["userVerification"] == "preferred"
    assert [d["id"] for d in create["excludeCredentials"]] == [b64(key.credential_id)]
    get = web(https).post("/auth/passkey/options").json()["publicKey"]
    assert get["rpId"] == RP_ID and get["userVerification"] == "preferred" and get["allowCredentials"] == []
    assert get["challenge"] != create["challenge"]


# --- Registration ---

def test_register_list_and_member_flag(https, client):
    alice = make_user("alice", "viewer")
    c = session_client(alice)
    assert c.get("/auth/state").json()["user"]["has_passkey"] is False
    _, passkey = register(c, name="  Alice's phone ")
    assert passkey["name"] == "Alice's phone" and passkey["last_used_at"] is None
    assert set(passkey) == {"id", "name", "backed_up", "created_at", "last_used_at"}  # no key material
    assert c.get("/me/passkeys").json() == [passkey]
    assert c.get("/auth/state").json()["user"]["has_passkey"] is True
    assert [u["has_passkey"] for u in client.get("/users").json()] == [True]
    assert https.db.activity()[0]["action"] == "passkey add"
    _, second = register(c)
    assert second["name"] == "Passkey"


def test_registration_challenge_is_bound_to_the_member(https):
    alice, bob = make_user("alice"), make_user("bob", "viewer")
    options = session_client(alice).post("/me/passkeys/options").json()
    r = session_client(bob).post("/me/passkeys", json={"credential": SoftKey().create(options)})
    assert r.status_code == 400
    assert https.db.list_passkeys(bob["id"]) == []


def test_registration_checks_origin_and_challenge(https):
    c = session_client(make_user("alice"))
    options = c.post("/me/passkeys/options").json()
    assert c.post("/me/passkeys", json={"credential": SoftKey().create(options, "https://evil.example.com")}
                  ).status_code == 400
    options = c.post("/me/passkeys/options").json()
    credential = SoftKey().create(options)
    assert c.post("/me/passkeys", json={"credential": credential}).status_code == 200
    assert c.post("/me/passkeys", json={"credential": credential}).status_code == 400  # challenge used up
    assert c.post("/me/passkeys", json={"credential": {"response": "junk"}}).status_code == 400


def test_same_credential_cannot_be_registered_twice(https):
    c = session_client(make_user("alice"))
    key, _ = register(c)
    options = c.post("/me/passkeys/options").json()
    assert c.post("/me/passkeys", json={"credential": key.create(options)}).status_code == 409


def test_api_token_has_no_passkeys(client, https):
    assert client.get("/me/passkeys").status_code == 400


# --- Sign-in ---

def test_sign_in_with_a_passkey(https):
    alice = make_user("alice", "operator")
    key, passkey = register(session_client(alice))
    browser, r = sign_in(https, key)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == alice["id"]
    assert browser.get("/auth/state").json()["user"]["username"] == "alice"
    assert browser.post("/queue/clear").status_code == 204  # a real operator session
    stored = https.db.passkey_by_credential(b64(key.credential_id))
    assert stored["sign_count"] == 1 and stored["last_used_at"]
    assert any(a["action"] == "login ok" and a["detail"].startswith("with a passkey") for a in https.db.activity())
    assert sign_in(https, key)[1].status_code == 200
    assert https.db.passkey_by_credential(b64(key.credential_id))["sign_count"] == 2


def test_assertion_is_single_use(https):
    key, _ = register(session_client(make_user("alice")))
    browser = web(https)
    credential = key.get(browser.post("/auth/passkey/options").json())
    assert browser.post("/auth/passkey/verify", json={"credential": credential}).status_code == 200
    r = web(https).post("/auth/passkey/verify", json={"credential": credential})
    assert r.status_code == 401 and "expired or was already used" in r.json()["detail"]


def test_expired_challenge_is_refused(https):
    key, _ = register(session_client(make_user("alice")))
    https.passkey_challenges.ttl = -1
    assert sign_in(https, key)[1].status_code == 401


def test_cloned_authenticator_is_refused(https):
    key, _ = register(session_client(make_user("alice")))
    assert sign_in(https, key)[1].status_code == 200
    _, r = sign_in(https, key, step=0)  # counter didn't move: a copy of the key
    assert r.status_code == 401 and "sign count" in r.json()["detail"].lower() and "sid" not in r.cookies


def test_wrong_origin_or_unknown_passkey_is_refused(https):
    key, _ = register(session_client(make_user("alice")))
    _, r = sign_in(https, key, origin="https://evil.example.com")
    assert r.status_code == 401 and "origin" in r.json()["detail"]
    _, r = sign_in(https, SoftKey())
    assert r.status_code == 401 and "isn't registered" in r.json()["detail"]
    assert https.db.user_count() == 1


def test_forged_signature_is_refused(https):
    key, _ = register(session_client(make_user("alice")))
    key.key = ec.generate_private_key(ec.SECP256R1())  # same credential id, someone else's key
    _, r = sign_in(https, key)
    assert r.status_code == 401 and "signature" in r.json()["detail"].lower()


def test_user_handle_must_match(https):
    key, _ = register(session_client(make_user("alice")))
    key.user_handle = b64(b"someone else")
    assert sign_in(https, key)[1].status_code == 401


def test_disabled_member_cannot_sign_in(https):
    alice, admin = make_user("alice", "viewer"), make_user("boss")
    key, _ = register(session_client(alice))
    https.db.update_user(alice["id"], {"disabled": True})
    _, r = sign_in(https, key)
    assert r.status_code == 401 and "disabled" in r.json()["detail"]
    assert admin  # the last enabled admin stays


def test_failed_passkey_attempts_are_throttled(https):
    browser = web(https)
    for _ in range(5):
        assert browser.post("/auth/passkey/verify", json={"credential": {}}).status_code == 401
    assert browser.post("/auth/passkey/verify", json={"credential": {}}).status_code == 429


# --- Rename / remove and the last-method guard ---

def test_rename_and_remove(https):
    alice, bob = make_user("alice"), make_user("bob", "viewer")
    c = session_client(alice)
    _, passkey = register(c)
    assert session_client(bob).patch(f"/me/passkeys/{passkey['id']}", json={"name": "mine"}).status_code == 404
    assert session_client(bob).delete(f"/me/passkeys/{passkey['id']}").status_code == 404
    r = c.patch(f"/me/passkeys/{passkey['id']}", json={"name": "Laptop"})
    assert r.status_code == 200 and r.json()["name"] == "Laptop"
    assert c.patch(f"/me/passkeys/{passkey['id']}", json={"name": "  "}).status_code == 400
    assert c.delete(f"/me/passkeys/{passkey['id']}").status_code == 204
    assert c.get("/me/passkeys").json() == []
    assert c.delete(f"/me/passkeys/{passkey['id']}").status_code == 404
    actions = [a["action"] for a in https.db.activity()][:3]
    assert actions == ["passkey remove", "passkey rename", "passkey add"]


def test_cannot_remove_the_only_sign_in_method(https):
    alice = make_user("alice")
    c = session_client(alice)
    _, first = register(c)
    with https.db.tx() as db:  # a passkey-only member
        db.execute("UPDATE users SET password_hash = '' WHERE id = ?", (alice["id"],))
    r = c.delete(f"/me/passkeys/{first['id']}")
    assert r.status_code == 409 and "only way" in r.json()["detail"]
    _, second = register(c)
    assert c.delete(f"/me/passkeys/{first['id']}").status_code == 204  # another passkey remains
    assert c.delete(f"/me/passkeys/{second['id']}").status_code == 409


def test_deleting_a_member_removes_their_passkeys(https, client):
    alice = make_user("alice", "viewer")
    key, _ = register(session_client(alice))
    assert client.delete(f"/users/{alice['id']}").status_code == 204
    assert https.db.passkey_by_credential(b64(key.credential_id)) is None


# --- "Require a passkey for admins" ---

def test_require_for_admins_needs_every_admin_to_have_one(https, client):
    boss, other = make_user("boss"), make_user("other")
    r = client.post("/settings", json={"passkey_required_for_admins": True})
    assert r.status_code == 409 and "boss, other" in r.json()["detail"]
    register(session_client(boss))
    register(session_client(other))
    assert client.post("/settings", json={"passkey_required_for_admins": True}).status_code == 200


def test_require_for_admins_needs_usable_passkeys(app, client):
    make_user("boss")
    r = client.post("/settings", json={"passkey_required_for_admins": True})  # http base URL
    assert r.status_code == 409 and "https" in r.json()["detail"]


def test_required_admin_must_use_the_passkey(https, client):
    from conftest import PASSWORD

    boss, op = make_user("boss"), make_user("op", "operator")
    c = session_client(boss)
    key, passkey = register(c)
    assert client.post("/settings", json={"passkey_required_for_admins": True}).status_code == 200

    r = web(https).post("/auth/login", json={"username": "boss", "password": PASSWORD})
    assert r.status_code == 403 and "passkey" in r.json()["detail"] and "sid" not in r.cookies
    assert web(https).post("/auth/login", json={"username": "op", "password": PASSWORD}).status_code == 200
    assert sign_in(https, key)[1].status_code == 200
    assert c.delete(f"/me/passkeys/{passkey['id']}").status_code == 409  # owners keep one

    # A newly promoted admin without a passkey may still sign in, and is asked to add one.
    client.patch(f"/users/{op['id']}", json={"role": "admin"})
    browser = web(https)
    assert browser.post("/auth/login", json={"username": "op", "password": PASSWORD}).status_code == 200
    assert browser.get("/auth/state").json()["passkey_required"] is True
    assert "passkey_required" not in c.get("/auth/state").json()

    # If passkeys become unusable the rule stops applying, so nobody is locked out.
    https.settings.public_base_url = "http://speaker.example.com"
    assert web(https).post("/auth/login", json={"username": "boss", "password": PASSWORD}).status_code == 200


def test_settings_switches_are_owner_only(as_role):
    assert as_role("operator").post("/settings", json={"passkey_signin": False}).status_code == 403


# --- Challenges and storage ---

def test_challenges_are_capped_and_bound():
    ch = passkeys.Challenges(limit=3)
    first = ch.issue("login")
    for _ in range(3):
        ch.issue("login")
    with pytest.raises(passkeys.PasskeyError):
        ch.take(first, "login")  # pushed out by newer ones
    c = ch.issue("register", 7, "handle")
    with pytest.raises(passkeys.PasskeyError):
        ch.take(c, "login")
    c = ch.issue("register", 7, "handle")
    assert ch.take(c, "register", 7) == "handle"


def test_migrates_version_2_database_in_place(tmp_path):
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
    assert user["username"] == "kept" and user["has_passkey"] is False
    cred = {"credential_id": "abc", "public_key": b"k", "sign_count": 0, "backed_up": False, "transports": []}
    upgraded.add_passkey(user["id"], "handle", "Phone", cred)
    reopened = store.Store(path)
    assert reopened.schema_version() == 3 and reopened.get_user(user["id"])["has_passkey"] is True
