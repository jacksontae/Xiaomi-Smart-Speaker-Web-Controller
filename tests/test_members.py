from conftest import PASSWORD, make_user, session_client


def test_create_and_list_members(client):
    body = {"username": "Bob.S", "display_name": "Bob", "password": PASSWORD, "role": "operator"}
    r = client.post("/users", json=body)
    assert r.status_code == 200
    bob = r.json()
    assert bob["username"] == "bob.s" and bob["role"] == "operator" and bob["last_login_at"] is None
    assert [u["username"] for u in client.get("/users").json()] == ["bob.s"]
    assert "password_hash" not in bob


def test_create_member_validation(client):
    body = {"username": "bob", "display_name": "Bob", "password": PASSWORD, "role": "operator"}
    assert client.post("/users", json=body).status_code == 200
    assert client.post("/users", json=body | {"username": "BOB"}).status_code == 409
    assert client.post("/users", json=body | {"username": "x"}).status_code == 400
    assert client.post("/users", json=body | {"username": "a" * 33}).status_code == 400
    assert client.post("/users", json=body | {"username": "bad/name"}).status_code == 400
    assert client.post("/users", json=body | {"username": "carl", "password": "1234567"}).status_code == 400
    assert client.post("/users", json=body | {"username": "carl", "role": "root"}).status_code == 422


def test_patch_member(client, app):
    bob = make_user("bob", "viewer")
    r = client.patch(f"/users/{bob['id']}", json={"display_name": "Bobby", "role": "operator"})
    assert r.status_code == 200 and r.json()["display_name"] == "Bobby" and r.json()["role"] == "operator"
    assert client.patch("/users/999", json={"role": "viewer"}).status_code == 404


def test_disable_or_password_change_ends_sessions(client, app):
    bob = make_user("bob", "operator")
    browser = session_client(bob)
    assert client.patch(f"/users/{bob['id']}", json={"password": "brand new pass"}).status_code == 200
    assert browser.get("/status").status_code == 401
    browser = session_client(bob)
    assert client.patch(f"/users/{bob['id']}", json={"disabled": True}).status_code == 200
    assert browser.get("/status").status_code == 401
    assert client.patch(f"/users/{bob['id']}", json={"disabled": False}).json()["disabled"] is False


def test_role_change_applies_to_live_session(client):
    bob = make_user("bob", "operator")
    browser = session_client(bob)
    assert browser.post("/volume", json={"level": 0.5}).status_code == 200
    client.patch(f"/users/{bob['id']}", json={"role": "viewer"})
    assert browser.post("/volume", json={"level": 0.5}).status_code == 403


def test_delete_member(client):
    bob = make_user("bob", "viewer")
    browser = session_client(bob)
    r = client.delete(f"/users/{bob['id']}")
    assert r.status_code == 204 and r.content == b""
    assert browser.get("/status").status_code == 401
    assert client.delete(f"/users/{bob['id']}").status_code == 404


def test_cannot_delete_disable_or_demote_yourself(app):
    me = make_user("alice", "admin")
    make_user("other-admin", "admin")
    browser = session_client(me)
    assert browser.delete(f"/users/{me['id']}").status_code == 409
    assert browser.patch(f"/users/{me['id']}", json={"disabled": True}).status_code == 409
    assert browser.patch(f"/users/{me['id']}", json={"role": "operator"}).status_code == 409
    r = browser.patch(f"/users/{me['id']}", json={"display_name": "Al", "role": "admin"})
    assert r.status_code == 200 and r.json()["display_name"] == "Al"


def test_changing_own_password_via_members_keeps_this_session(app):
    me = make_user("alice", "admin")
    browser, elsewhere = session_client(me), session_client(me)
    assert browser.patch(f"/users/{me['id']}", json={"password": "another pass"}).status_code == 200
    assert browser.get("/users").status_code == 200
    assert elsewhere.get("/users").status_code == 401


def test_last_enabled_admin_is_protected(client, app):
    only = make_user("alice", "admin")
    assert client.patch(f"/users/{only['id']}", json={"role": "viewer"}).status_code == 409
    assert client.patch(f"/users/{only['id']}", json={"disabled": True}).status_code == 409
    assert client.delete(f"/users/{only['id']}").status_code == 409
    assert app.db.get_user(only["id"])["role"] == "admin"

    second = make_user("bob", "admin", disabled=True)  # a disabled admin doesn't count
    assert client.delete(f"/users/{only['id']}").status_code == 409
    client.patch(f"/users/{second['id']}", json={"disabled": False})
    assert client.patch(f"/users/{only['id']}", json={"role": "operator"}).status_code == 200
    assert client.delete(f"/users/{second['id']}").status_code == 409  # now bob is the last one


def test_disabled_admin_can_be_removed(client):
    make_user("alice", "admin")
    ghost = make_user("ghost", "admin", disabled=True)
    assert client.delete(f"/users/{ghost['id']}").status_code == 204


def test_operator_cannot_manage_members(as_role):
    op = as_role("operator")
    assert op.get("/users").status_code == 403
    assert op.post("/users", json={"username": "x1x", "password": PASSWORD, "role": "admin"}).status_code == 403
