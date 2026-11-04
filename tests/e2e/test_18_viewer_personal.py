"""Viewer rights follow the output this browser picked. On the speaker: no Music, shared playlists read-only, and
previous / next / a tap on a queue row move the speaker's queue. On This device: Music appears, and the viewer makes
and edits playlists of their own ("My playlists"); switching the output changes the nav and the page live.
Owners see other members' personal playlists grouped under "Members' playlists"; operators don't see them."""
import json
import re
import time

import pytest
from playwright.sync_api import expect

from .e2ekit import wait_for

HDR = {"X-Requested-With": "speaker-web"}
QUEUE = [{"id": i + 1, "kind": "youtube", "title": t, "duration": 180 + i * 7}
         for i, t in enumerate(["First tune", "Second tune", "Third tune", "Fourth tune"])]
STATUS = {"speaker": "Test speaker", "volume": 0.4, "muted": False, "resume_pending": None, "tts_lang": "en",
          "talking": None, "media": {"title": "Second tune", "state": "PLAYING", "duration": 187, "position": 30,
                                     "thumbnail": None},
          "queue": {"playlist_id": None, "name": "Morning", "index": 1, "length": 4, "shuffle": False,
                    "repeat": "off", "items": QUEUE}}


def nav(app):
    """Routes in the visible navigation (phone tab bar / Android pill, or the sidebar / rail)."""
    return app.page.locator(".tabbar a.tab, .sbn a.nv").evaluate_all(
        "els => els.filter((e) => e.offsetParent).map((e) => e.dataset.route)")


def pick(app, which):
    """Choose an output in the speaker picker (a sheet on phones, a popover on larger screens)."""
    p = app.page
    p.locator("[data-spk]:visible").first.click()
    row = p.locator(f".spi[data-out='{which}']")
    expect(row).to_be_visible()
    row.click()
    expect(p.locator("dialog.ov")).to_have_count(0)


def own_playlist(app, name):
    """A personal playlist made by the signed-in viewer through the API (as the page would)."""
    r = app.ctx.request.post("/playlists", headers=HDR, data={"name": name})
    assert r.ok and r.json()["mine"] and r.json()["owner_id"] is not None, r.text()
    return r.json()


def drop(app, pid):
    app.ctx.request.delete(f"/playlists/{pid}", headers=HDR)


@pytest.mark.parametrize("device", ["phone", "desktop", "android", "android-tablet"])
def test_nav_follows_the_output(make_app, seeded, device):
    app = make_app("viewer", device=device, route="playlists")
    p = app.page
    mine = own_playlist(app, f"Vera mix {device} {int(time.time()) % 10000}")
    app.go("playlists")
    assert "music" not in nav(app)
    expect(p.locator(".pl-row", has_text=mine["name"])).to_have_count(0)  # personal ones hide on the speaker
    expect(p.locator("#view .tb-sec")).to_have_count(0)
    app.go("")  # phones show the speaker picker on Now
    pick(app, "device")
    wait_for(lambda: "music" in nav(app), what="Music in the nav")
    app.go("playlists")
    expect(p.locator(".pl-list[data-group='mine'] .pl-row", has_text=mine["name"])).to_be_visible()
    expect(p.locator("#view .tb-sec h2").first).to_have_text("My playlists")
    app.go("")
    pick(app, "main")
    wait_for(lambda: "music" not in nav(app), what="Music gone from the nav")
    app.go("playlists")
    expect(p.locator(".pl-row", has_text=mine["name"])).to_have_count(0)
    drop(app, mine["id"])
    app.clean(f"nav {device}")


def test_leaving_this_device_on_music_goes_to_now(make_app, seeded):
    app = make_app("viewer", device="desktop")
    p = app.page
    app.go("music", wait_header=False)
    app.toast("This page is for Operators and above")  # not offered on the speaker
    p.wait_for_function("location.hash === '#/'")
    pick(app, "device")
    app.go("music/radio")
    app.header("Music")
    expect(p.locator("#view .mu-heart")).to_have_count(0)  # radio favourites are read-only for viewers
    app.go("music/files")
    expect(p.locator("#view .mu-fhead")).to_contain_text("only you and the owner can see them")
    expect(p.get_by_role("button", name="Upload")).to_be_visible()
    pick(app, "main")
    p.wait_for_function("location.hash === '#/'")
    app.header("Now playing")
    assert "music" not in nav(app)
    app.clean("leave music")


def test_viewer_moves_the_speaker_queue(make_app, seeded):
    app = make_app("viewer", device="phone", go=False)
    p = app.page
    sent = []
    p.route(re.compile(r".*/status$"), lambda r: r.fulfill(status=200, content_type="application/json",
                                                          body=json.dumps(STATUS)))

    def queue_call(route):
        sent.append((urlpath(route.request.url), route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(STATUS["queue"]))

    p.route(re.compile(r".*/queue/(next|prev|jump)$"), queue_call)
    app.go("")
    expect(p.locator(".np-title")).to_have_text("Second tune")
    expect(p.locator(".np-transport")).to_be_visible()
    for name in ("Play", "Pause", "Stop and clear the queue"):
        expect(p.locator(".np-transport").get_by_role("button", name=name, exact=True)).to_be_hidden()
    expect(p.locator(".np-volume input[type=range]")).to_have_count(0)  # volume stays display only
    p.get_by_role("button", name="Next", exact=True).click()
    p.get_by_role("button", name="Previous", exact=True).click()
    p.get_by_role("button", name="Play Fourth tune").click()
    wait_for(lambda: len(sent) == 3, what="three queue calls")
    assert [s[0] for s in sent] == ["/queue/next", "/queue/prev", "/queue/jump"]
    assert json.loads(sent[2][1]) == {"index": 3}
    app.clean("viewer queue")


def urlpath(url):
    return re.sub(r"^https?://[^/]+", "", url).split("?")[0]


def test_viewer_own_playlist_crud(make_app, seeded):
    shared = seeded.post("/playlists", {"name": f"Team picks {int(time.time()) % 10000}"}).json()
    seeded.post(f"/playlists/{shared['id']}/items", {"kind": "tts", "source": "Shared item", "lang": "en"})
    app = make_app("viewer", device="desktop", route="playlists")
    p = app.page
    pick(app, "device")
    name = f"Vera evening {int(time.time()) % 10000}"
    p.locator("#view .phd-r button.btn.primary").click()
    sheet = app.sheet()
    sheet.get_by_label("Playlist name").fill(name)
    sheet.locator("button[type=submit]").click()
    app.no_sheet()
    mine = p.locator(".pl-list[data-group='mine']")
    expect(mine.locator(".pl-row", has_text=name)).to_be_visible()
    pane = p.locator(".pl-pane")
    expect(pane.locator(".pl-name")).to_have_text(name)
    pid = int(app.hash().rsplit("/", 1)[1])
    pl = next(x for x in app.ctx.request.get("/playlists").json() if x["id"] == pid)
    assert pl["mine"] and pl["can_edit"] and pl["owner_id"] is not None
    # add a text item from the empty playlist's "+"
    mine.locator(".pl-row", has_text=name).get_by_role("button", name=f"Add items to {name}").click()
    sheet = app.sheet()
    sheet.locator(".tb-chips").get_by_role("radio", name="Text", exact=True).click()
    sheet.get_by_label("Text", exact=True).fill("My own reminder")
    sheet.get_by_role("button", name="Add text").click()
    app.toast("Text added")
    sheet.get_by_role("button", name="Done").click()
    app.no_sheet()
    expect(mine.locator(".pl-row", has_text=name)).to_contain_text("1 item")
    # rename
    p.locator(".pl-row", has_text=name).locator("a.tb-stretch").click()
    pane.get_by_role("button", name=f"More for {name}").click()
    p.locator(".popover").get_by_role("button", name="Rename").click()
    sheet = app.sheet()
    sheet.get_by_label("Playlist name").fill(name + " v2")
    sheet.get_by_role("button", name="Save name").click()
    app.no_sheet()
    expect(pane.locator(".pl-name")).to_have_text(name + " v2")
    # the shared playlist stays read-only, and "add to playlist" offers only the viewer's own
    p.locator(".pl-row", has_text=shared["name"]).locator("a.tb-stretch").click()
    expect(pane.locator(".pl-name")).to_have_text(shared["name"])
    for sel in (".pl-links", ".pl-more", ".pl-grip"):
        expect(pane.locator(sel)).to_have_count(0)
    expect(pane.locator(".pl-play")).to_be_visible()  # plays on this device
    f = next((x for x in seeded.get("/files")["items"] if x["owner_id"] is None), None)
    if f:
        app.go("music/files")
        p.locator(".tb-row", has_text=f["title"]).get_by_role("button", name=f"Add {f['title']} to a playlist").click()
        sheet = app.sheet()
        expect(sheet.locator(".tb-pick", has_text=name + " v2")).to_be_visible()
        expect(sheet.locator(".tb-pick", has_text=shared["name"])).to_have_count(0)
        p.keyboard.press("Escape")
        app.no_sheet()
        app.go(f"playlists/{pid}")
    else:
        p.locator(".pl-row", has_text=name + " v2").locator("a.tb-stretch").click()
    # delete
    pane.get_by_role("button", name=f"More for {name} v2").click()
    p.locator(".popover").get_by_role("button", name="Delete playlist").click()
    app.toast(f"Deleted {re.escape(name)} v2")
    wait_for(lambda: all(x["id"] != pid for x in seeded.get("/playlists")), timeout=15, what="playlist deleted")
    seeded.delete(f"/playlists/{shared['id']}")
    app.clean("viewer crud")


def test_owner_sees_members_playlists(make_app, seeded):
    shared = seeded.post("/playlists", {"name": f"Everyone's {int(time.time()) % 10000}"}).json()
    viewer = make_app("viewer", device="desktop", go=False)
    mine = own_playlist(viewer, f"Vera private {int(time.time()) % 10000}")
    owner = make_app("owner", device="desktop", route="playlists")
    p = owner.page
    group = p.locator(".pl-list[data-group='members']")
    expect(group.locator(".pl-row", has_text=mine["name"])).to_contain_text("by Vera Viewer")
    expect(p.locator("#view .tb-sec h2", has_text="Members’ playlists")).to_be_visible()
    owner.shot("viewer-personal-owner-desktop")
    op = make_app("operator", device="desktop", route="playlists")
    expect(op.page.locator(".pl-row").first).to_be_visible()
    expect(op.page.locator(".pl-row", has_text=mine["name"])).to_have_count(0)
    expect(op.page.locator("#view .tb-sec")).to_have_count(0)  # operators look unchanged
    drop(viewer, mine["id"])
    seeded.delete(f"/playlists/{shared['id']}")
    owner.clean("owner members")
    op.clean("operator unchanged")
