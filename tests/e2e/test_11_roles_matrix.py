"""Every page for every role at phone / iPad / desktop: renders, no JS errors, no sideways scroll; pages above the
role are refused (redirect + message) and hidden from the navigation. EN and TH, light and dark, reduced motion."""
import pytest
from playwright.sync_api import expect

ROUTES = {  # route -> minimum role
    "": "viewer", "announce": "viewer", "music": "operator", "playlists": "viewer", "schedule": "viewer",
    "members": "admin", "settings": "admin", "activity": "admin", "auth": "admin", "account": "viewer",
    "prefs": "viewer", "help": "viewer",
}
RANK = {"viewer": 0, "operator": 1, "admin": 2}
ROLE_RANK = {"viewer": 0, "operator": 1, "owner": 2}
TABS = {"viewer": ["now", "announce", "playlists"], "operator": ["now", "announce", "music", "playlists"],
        "owner": ["now", "announce", "music", "playlists"]}
SIDE_ADMIN = ["members", "settings", "activity"]

COMBOS = [
    ("owner", "phone", "en", "light", None), ("owner", "ipad", "th", "dark", None),
    ("owner", "desktop", "en", "light", "on"),
    ("operator", "phone", "th", "dark", None), ("operator", "ipad", "en", "light", None),
    ("operator", "desktop", "en", "dark", None),
    ("viewer", "phone", "en", "light", None), ("viewer", "ipad", "en", "light", "system"),
    ("viewer", "desktop", "th", "light", None),
]


@pytest.mark.parametrize(("role", "device", "lang", "theme", "motion"), COMBOS,
                         ids=[f"{c[0]}-{c[1]}-{c[2]}-{c[3]}" + (f"-motion-{c[4]}" if c[4] else "") for c in COMBOS])
def test_every_page(make_app, seeded, role, device, lang, theme, motion):
    app = make_app(role, device=device, lang=lang, theme=theme, motion=motion, reduced_media=motion == "system")
    p = app.page
    expect(p.locator("html")).to_have_attribute("lang", lang)
    expect(p.locator("html")).to_have_attribute("data-theme", theme)
    if motion:
        expect(p.locator("html")).to_have_attribute("data-motion", "reduce")
    # navigation shows only what the role may open
    if device == "phone":
        tabs = p.locator(".tabbar a.tab").evaluate_all("els => els.map((e) => e.dataset.route)")
        assert tabs == TABS[role], tabs
        expect(p.locator(".tabdock")).to_be_visible()
    else:
        side = p.locator(".sbn a.nv").evaluate_all("els => els.map((e) => e.dataset.route)")
        assert side == TABS[role] + (SIDE_ADMIN if role == "owner" else []), side
        expect(p.locator(".sb")).to_be_visible()
    for route, need in ROUTES.items():
        if ROLE_RANK[role] >= RANK[need]:
            app.go(route)
            expect(p.locator("#view .page").first).to_be_visible()
            p.wait_for_timeout(250)  # let late fetches land before checking layout
            app.no_hscroll(f"#/{route}")
        else:
            app.go(route, wait_header=False)
            expect(p.locator("#toasts .toast.err").last).to_be_visible()
            p.wait_for_function("location.hash === '#/'")
            app.header()
    app.go("announce")
    app.shot(f"matrix-{role}-{device}-{lang}-{theme}")
    app.clean(f"{role}/{device}/{lang}")


def test_forbidden_message_text(make_app, seeded):
    app = make_app("viewer", device="desktop")
    app.go("members", wait_header=False)
    app.toast("This page is for Owners and above")
    app.go("music", wait_header=False)
    app.toast("This page is for Operators and above")
    app.clean("forbidden text")


def test_api_role_gating(make_app, seeded):
    """The server refuses what the UI hides (viewer -> operator/admin calls; operator -> admin calls)."""
    hdr = {"X-Requested-With": "speaker-web"}
    viewer = make_app("viewer", device="desktop")
    r = viewer.ctx.request
    assert r.post("/say", headers=hdr, data={"text": "x"}).status == 403
    assert r.post("/playlists", headers=hdr, data={"name": "x"}).status == 403
    assert r.get("/users").status == 403
    assert r.get("/talk/status").status == 403
    op = make_app("operator", device="desktop")
    r = op.ctx.request
    assert r.get("/settings").status == 403
    assert r.get("/activity").status == 403
    assert r.post("/users", headers=hdr, data={"username": "x", "password": "x" * 8}).status == 403
    # writes without the X-Requested-With header are refused (CSRF guard)
    assert r.post("/playlists", data={"name": "no header"}).status == 403
    viewer.clean("api gating viewer")
    op.clean("api gating operator")
