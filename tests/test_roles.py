"""Every route's required role, checked both from the route table and over HTTP."""
import pytest
from conftest import session_client
from fastapi.routing import APIRoute

# (method, path) -> minimum role; None = public. Adding a route without listing it here fails the suite.
ROLE_TABLE = {
    ("GET", "/auth/state"): None,
    ("POST", "/auth/setup"): None,
    ("POST", "/auth/login"): None,
    ("POST", "/auth/logout"): "viewer",
    ("POST", "/auth/logout-all"): "viewer",
    ("POST", "/auth/password"): "viewer",
    ("GET", "/users"): "admin",
    ("POST", "/users"): "admin",
    ("PATCH", "/users/{user_id}"): "admin",
    ("DELETE", "/users/{user_id}"): "admin",
    ("GET", "/status"): "viewer",
    ("POST", "/say"): "operator",
    ("POST", "/play"): "operator",
    ("POST", "/youtube"): "operator",
    ("GET", "/youtube/search"): "operator",
    ("POST", "/volume"): "operator",
    ("POST", "/pause"): "operator",
    ("POST", "/resume"): "operator",
    ("POST", "/stop"): "operator",
    ("GET", "/settings"): "admin",
    ("POST", "/settings"): "admin",
    ("GET", "/speakers"): "admin",
    ("GET", "/activity"): "admin",
    ("GET", "/playlists"): "viewer",
    ("POST", "/playlists"): "operator",
    ("GET", "/playlists/{playlist_id}"): "viewer",
    ("PATCH", "/playlists/{playlist_id}"): "operator",
    ("DELETE", "/playlists/{playlist_id}"): "operator",
    ("POST", "/playlists/{playlist_id}/items"): "operator",
    ("DELETE", "/playlists/{playlist_id}/items/{item_id}"): "operator",
    ("PUT", "/playlists/{playlist_id}/order"): "operator",
    ("POST", "/playlists/{playlist_id}/play"): "operator",
    ("GET", "/queue"): "viewer",
    ("POST", "/queue/next"): "operator",
    ("POST", "/queue/prev"): "operator",
    ("POST", "/queue/jump"): "operator",
    ("PATCH", "/queue"): "operator",
    ("POST", "/queue/clear"): "operator",
    ("GET", "/phrases"): "viewer",
    ("POST", "/phrases"): "operator",
    ("DELETE", "/phrases/{phrase_id}"): "operator",
    ("GET", "/schedules"): "viewer",
    ("POST", "/schedules"): "operator",
    ("PATCH", "/schedules/{schedule_id}"): "operator",
    ("DELETE", "/schedules/{schedule_id}"): "operator",
    ("POST", "/schedules/{schedule_id}/run"): "operator",
    ("GET", "/talk/status"): "operator",
    # Fetched by the speaker with signed URLs, or the public web UI.
    ("GET", "/tts.mp3"): "signed",
    ("GET", "/yt/{filename}"): "signed",
    ("GET", "/talk/chime.wav"): "signed",
    ("GET", "/talk/{talk_id}/live"): "signed",
    ("GET", "/"): None,
    ("GET", "/manifest.webmanifest"): None,
    ("GET", "/apple-touch-icon.png"): None,
}
ROLES = ["viewer", "operator", "admin"]
GUARDED = [(m, p, r) for (m, p), r in ROLE_TABLE.items() if r in ROLES]


def _roles_of(dependant):
    found = []
    for dep in dependant.dependencies:
        if hasattr(dep.call, "role"):
            found.append(dep.call.role)
        found += _roles_of(dep)
    return found


def _route_role(route, router_deps=()):
    if any(getattr(d.call, "__name__", "") == "verify_media" for d in route.dependant.dependencies):
        return "signed"
    roles = [d.dependency.role for d in router_deps if hasattr(d.dependency, "role")] + _roles_of(route.dependant)
    assert len(set(roles)) <= 1, f"{route.path} has conflicting role guards {roles}"
    return roles[0] if roles else None


def test_role_table_covers_every_route(app):
    actual = {}
    sources = [(r, ()) for r in app.app.routes if isinstance(r, APIRoute)]
    for router in (app.viewer_api, app.operator_api, app.admin_api):
        sources += [(r, router.dependencies) for r in router.routes]
    for route, deps in sources:
        for method in route.methods - {"HEAD"}:
            actual[(method, route.path)] = _route_role(route, deps)
    assert actual == ROLE_TABLE

    # Nothing is mounted outside those routers: every documented operation is in the table.
    schema = app.app.openapi()["paths"]
    documented = {(m.upper(), path) for path, ops in schema.items() for m in ops}
    hidden = {("GET", "/manifest.webmanifest"), ("GET", "/apple-touch-icon.png")}
    assert documented | hidden == set(ROLE_TABLE)


def _url(path):
    return path.format(user_id=999, playlist_id=999, item_id=999, phrase_id=999, schedule_id=999,
                       filename="x.m4a")


def _call(client, method, path):
    kwargs = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
    if path == "/youtube/search":
        kwargs["params"] = {"q": "x"}
    return client.request(method, _url(path), **kwargs)


@pytest.mark.parametrize(("method", "path", "role"), GUARDED, ids=[f"{m} {p}" for m, p, _ in GUARDED])
def test_role_enforced(method, path, role, anon, as_role, app, fake_speaker, monkeypatch):
    import pychromecast.discovery

    monkeypatch.setattr(app, "yt_search", lambda q, limit: [])
    monkeypatch.setattr(pychromecast.discovery, "discover_chromecasts", lambda timeout: ([], _Browser()))

    r = _call(anon, method, path)
    assert r.status_code == 401, r.text
    assert isinstance(r.json()["detail"], str)

    rank = ROLES.index(role)
    for lower in ROLES[:rank]:
        r = _call(as_role(lower), method, path)
        assert r.status_code == 403, (lower, r.text)
    assert fake_speaker.media_controller.loads == [] and not fake_speaker.quit and fake_speaker.volume == 0.2

    for allowed in ROLES[rank:]:
        r = _call(as_role(allowed, f"{allowed}-ok"), method, path)
        assert r.status_code not in (401, 403), (allowed, r.text)


class _Browser:
    def stop_discovery(self):
        pass


def test_api_token_is_admin(client):
    assert client.get("/users").status_code == 200
    assert client.get("/activity").status_code == 200


def test_static_files_are_public(anon, app):
    assert anon.get("/").status_code == 200
    r = anon.get("/static/index.html")
    assert r.status_code == 200
    assert anon.get("/static/../config.json").status_code == 404
    assert anon.get("/manifest.webmanifest").status_code in (200, 404)  # frontend may not have added it yet


def test_root_files_served_from_static(anon, app, monkeypatch, tmp_path):
    (tmp_path / "manifest.webmanifest").write_text("{}")
    monkeypatch.setattr(app, "STATIC_DIR", tmp_path)
    r = anon.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    assert anon.get("/apple-touch-icon.png").status_code == 404


def test_viewer_cannot_change_anything(app, fake_speaker):
    from conftest import make_user

    viewer = session_client(make_user("v", "viewer"))
    assert viewer.get("/status").status_code == 200
    assert viewer.post("/say", json={"text": "hi"}).status_code == 403
    assert viewer.get("/settings").status_code == 403
    assert fake_speaker.media_controller.loads == []
