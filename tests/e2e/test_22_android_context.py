"""Android big header's context line (ctx.header({ sub }), ui.js headerSub): one short line under the page title on
Now, Announce, Music, Playlists, Schedule, Members, Activity and Settings, live with /status where the page polls it;
hidden on iOS / desktop. Playlists sorted into Music / Announcements (announcement-only playlists, the server's
tts_only), nested in the owner groups. /status is mocked as in test_14 (the speaker is offline in this suite)."""
import re
import time

from playwright.sync_api import expect

from . import test_14_android_shell as shell
from .test_18_viewer_personal import drop, own_playlist

android_app = shell.android_app  # the fixture: Android user agent, mocked /status


def sub(p):
    return p.locator("#view .phd-sub").first


def make_playlist(api, name, kind="url", items=2):
    p = api.post("/playlists", {"name": name}).json()
    for i in range(items):
        body = {"kind": "tts", "source": f"{name} notice {i + 1}"} if kind == "tts" else \
            {"kind": "url", "source": f"https://audio.example.com/{i}.mp3", "title": f"{name} clip {i + 1}"}
        api.post(f"/playlists/{p['id']}/items", body)
    return p


def test_context_lines_phone(android_app, seeded):
    app = android_app("owner", route="")
    p = app.page
    expect(sub(p)).to_have_text("Test speaker is playing")
    expect(sub(p)).to_be_visible()
    app.status["media"]["state"] = "PAUSED"  # live: the next poll repaints it
    expect(sub(p)).to_have_text("Test speaker is paused", timeout=10_000)
    app.status["media"]["state"] = "PLAYING"
    checks = [
        ("announce", "Announce", "Test speaker connected, playing music"),
        ("music", "Music", "Speaker is playing Morning Café Jazz"),
        ("playlists", "Playlists", re.compile(r"^\d+ playlists?$")),
        ("schedule", "Announce",
         re.compile(r"(more today, next at \d\d:\d\d|^Nothing more today, next .+|^Nothing scheduled)$")),
        ("members", "Members", re.compile(r"^\d+ people, (all active|\d+ disabled)$")),
        ("activity", "Activity", re.compile(r"(^\d+\+? today|^Nothing yet today)$")),
        ("settings", "Speaker settings", "Speaker connected"),
    ]
    for route, title, line in checks:
        p.evaluate(f"location.hash = '#/{route}'")
        app.header(title)
        expect(sub(p)).to_have_text(line)
        expect(sub(p)).to_be_visible()
    # one line: it never pushes the page sideways
    app.no_hscroll("context lines")
    app.clean("android context lines")


def test_context_line_thai_and_offline(android_app, seeded):
    app = android_app("owner", route="", prefs={"spk.lang": "th"})
    expect(sub(app.page)).to_have_text("Test speaker กำลังเล่น")
    app.page.evaluate("location.hash = '#/playlists'")
    expect(sub(app.page)).to_have_text(re.compile(r"^มี \d+ เพลย์ลิสต์$"))
    app.clean("android context thai")
    off = android_app("owner", route="", playing=False)
    expect(sub(off.page)).to_have_text("Speaker is offline")
    off.clean("android context offline")


def test_context_line_android_only(make_app, seeded):
    app = make_app("owner", device="desktop", route="")
    expect(app.page.locator("#view .phd-sub")).to_have_count(1, timeout=20_000)  # Now sets it after the first poll
    expect(sub(app.page)).to_be_hidden()  # shell.css hides it off Android
    app.clean("desktop no context line")


def test_playlists_music_and_announcements(android_app, make_app, seeded):
    n = int(time.time()) % 10000
    music = make_playlist(seeded, f"Ctx music {n}")
    says = make_playlist(seeded, f"Ctx notices {n}", kind="tts")
    assert says["id"] in [x["id"] for x in seeded.get("/playlists") if x["tts_only"]]
    try:
        # operators (shared playlists only): Music / Announcements are the page's sections
        app = android_app("operator", route="playlists", playing=False)
        p = app.page
        expect(p.locator("#view .tb-sec h2")).to_have_text(["Music", "Announcements"])
        expect(p.locator(".pl-list[data-kind='says'] .pl-row", has_text=says["name"])).to_be_visible()
        expect(p.locator(".pl-list[data-kind='music'] .pl-row", has_text=music["name"])).to_be_visible()
        expect(p.locator(".pl-list[data-kind='music'] .pl-row", has_text=says["name"])).to_have_count(0)
        app.clean("android playlist kinds")
        # owner on desktop with a member's playlist: owner groups first, the kinds inside the shared group
        viewer = make_app("viewer", device="desktop", go=False)
        mine = own_playlist(viewer, f"Ctx Vera {n}")
        try:
            owner = make_app("owner", device="desktop", route="playlists")
            q = owner.page
            expect(q.locator("#view .tb-sec h2")).to_have_text(["Shared", "Members’ playlists"])
            shared_says = q.locator(".pl-list[data-group='shared'][data-kind='says'] .pl-row", has_text=says["name"])
            expect(shared_says).to_be_visible()
            expect(q.locator(".pl-kind")).to_have_text(["Music", "Announcements"])  # only the shared group has both
            expect(q.locator(".pl-list[data-group='members'] .pl-row", has_text=mine["name"])).to_be_visible()
            owner.clean("desktop playlist kinds")
        finally:
            drop(viewer, mine["id"])
    finally:
        seeded.delete(f"/playlists/{music['id']}")
        seeded.delete(f"/playlists/{says['id']}")
