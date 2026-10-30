"""Playlists: create/rename/delete with Undo, every item kind through the Add item sheet, reorder (buttons,
keyboard, menu), remove with Undo, repeat/play, desktop split view, viewer read-only."""
import json
import re
import time

from playwright.sync_api import expect

from .e2ekit import SPEAKER_WAIT, mp3_bytes, wait_for

YT = [{"video_id": "jNQXAC9IVRw", "title": "Zoo clip", "channel": "E2E", "duration": 19, "thumbnail": None}]
RADIO = [{"name": "Kind Radio", "url": "http://192.0.2.31/live.mp3", "content_type": "audio/mpeg", "favicon": None,
          "country": "TH", "tags": "pop"}]
SHOWS = [{"id": 7, "title": "Kind Show", "author": "E2E", "feed_url": "https://podcast.example.com/kind.xml",
          "artwork": None, "genre": "Talk"}]
FEED = {"title": "Kind Show", "author": "E2E", "artwork": None, "episodes": [
    {"title": "Kind episode", "url": "https://podcast.example.com/kind1.mp3", "content_type": "audio/mpeg",
     "duration": 300, "published": "2026-10-02T00:00:00Z", "thumbnail": None}]}


def mock(p, pattern, data):
    p.route(pattern, lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(data)))


def items(api, pid):
    return [i["title"] for i in api.get(f"/playlists/{pid}")["items"]]


def ensure_file(api, title="kind-file"):
    for f in api.get("/files")["items"]:
        if f["title"] == title:
            return f
    r = api.c.post(f"/files?name={title}.mp3&duration=1", content=mp3_bytes(1), headers={"Content-Type": "audio/mpeg"})
    r.raise_for_status()
    return r.json()


def create(app, name):
    p = app.page
    p.locator("#view .phd-r button.btn.primary").click()
    sheet = app.sheet()
    sheet.get_by_label("Playlist name").fill(name)
    sheet.locator("button[type=submit]").click()
    app.no_sheet()


def test_playlist_phone_full_flow(make_app, seeded, drained):
    ensure_file(seeded)
    app = make_app("operator", device="phone", route="playlists")
    p = app.page
    for pat, data in (("**/youtube/search*", YT), ("**/radio/search*", RADIO), ("**/podcasts/search*", SHOWS),
                      ("**/podcasts/episodes*", FEED)):
        mock(p, pat, data)
    name = f"Every kind {int(time.time()) % 10000}"
    # create (empty name refused)
    p.locator("#view .phd-r button.btn.primary").click()
    sheet = app.sheet()
    sheet.locator("button[type=submit]").click()
    expect(sheet.locator(".form-error")).to_have_text("Give it a name first.")
    sheet.get_by_label("Playlist name").fill(name)
    sheet.locator("button[type=submit]").click()
    app.no_sheet()
    expect(p).to_have_url(re.compile(r"#/playlists/\d+$"))
    pid = int(app.hash().rsplit("/", 1)[1])
    app.header(name)
    expect(p.locator(".pl-items")).to_contain_text("No items in this playlist yet.")
    expect(p.locator(".pl-play")).to_be_disabled()
    # add one of every kind
    p.locator(".pl-links").get_by_role("button", name="Add item").click()
    sheet = app.sheet()
    count = sheet.locator(".tb-count")
    expect(count).to_have_text("Nothing added yet")
    chip = lambda label: sheet.locator(".tb-chips").get_by_role("radio", name=label, exact=True)  # noqa: E731
    chip("Text").click()
    sheet.get_by_role("button", name="Add text").click()
    expect(sheet.locator(".form-error")).to_have_text("Type what the speaker should say first.")
    sheet.get_by_label("Text", exact=True).fill("Welcome, we are open")
    sheet.get_by_role("radiogroup", name="Voice language").get_by_role("radio", name="English").click()
    sheet.get_by_role("button", name="Add text").click()
    app.toast("Text added")
    expect(count).to_have_text("1 item added")
    chip("Audio link").click()
    sheet.get_by_label("Audio file link").fill("ftp://audio.example.com/x.mp3")
    sheet.get_by_role("button", name="Add link").click()
    expect(sheet.locator(".form-error")).to_have_text("Use a link that starts with http:// or https://")
    sheet.get_by_label("Audio file link").fill("https://audio.example.com/clip.mp3")
    sheet.get_by_label("Display name").fill("Link clip")
    sheet.get_by_role("button", name="Add link").click()
    app.toast("Link added")
    expect(count).to_have_text("2 items added")
    chip("My files").click()
    sheet.get_by_label("Search your files").fill("kind-file")
    sheet.get_by_role("button", name="Add kind-file").click()
    expect(count).to_have_text("3 items added")
    # tapping the check removes it again, then add back
    sheet.get_by_role("button", name=re.compile("^Added kind-file")).click()
    expect(count).to_have_text("2 items added")
    sheet.get_by_role("button", name="Add kind-file").click()
    expect(count).to_have_text("3 items added")
    chip("Radio").click()
    sheet.get_by_label("Search radio stations").fill("kind")
    sheet.locator("form.tb-search button[type=submit]").click()
    sheet.get_by_role("button", name="Add Kind Radio").click()
    expect(count).to_have_text("4 items added")
    chip("Podcast").click()
    sheet.get_by_label("Podcast name or RSS link").fill("kind")
    sheet.locator("form.tb-search button[type=submit]").click()
    sheet.locator(".tb-row.tb-tap", has_text="Kind Show").click()
    sheet.get_by_role("button", name="Add Kind episode").click()
    expect(count).to_have_text("5 items added")
    chip("YouTube").click()
    sheet.get_by_label("Search YouTube").fill("zoo")
    sheet.locator("form.tb-search button[type=submit]").click()
    sheet.get_by_role("button", name="Add Zoo clip").click()
    expect(count).to_have_text("6 items added", timeout=30_000)  # the server looks the video up on YouTube
    sheet.get_by_role("button", name="Done").click()
    app.no_sheet()
    expect(p.locator(".pl-it")).to_have_count(6)
    assert items(seeded, pid) == ["Welcome, we are open", "Link clip", "kind-file", "Kind Radio", "Kind episode",
                                  "Zoo clip"]
    expect(p.locator(".pl-meta")).to_contain_text("6 items")
    kinds = p.locator(".pl-it .tb-s").all_inner_texts()
    assert kinds[0] == "Announcement in English" and "Radio station, live" in kinds and "My file" in kinds, kinds
    # reorder mode: up/down buttons
    p.get_by_role("button", name="Reorder").click()
    p.get_by_role("button", name="Move Link clip up").click()
    wait_for(lambda: items(seeded, pid)[0] == "Link clip", what="Link clip first on the server")
    expect(p.get_by_role("button", name="Move Link clip up")).to_be_disabled()
    p.get_by_role("button", name="Move Zoo clip down").is_disabled()
    p.get_by_role("button", name="Done").click()
    # item menu (sheet on phones): move to top, remove + Undo, remove for good
    p.get_by_role("button", name="Options for Zoo clip").click()
    app.sheet().get_by_role("button", name="Move to top").click()
    wait_for(lambda: items(seeded, pid)[0] == "Zoo clip", what="move to top")
    app.no_sheet()
    p.get_by_role("button", name="Options for Kind Radio").click()
    app.sheet().get_by_role("button", name="Remove from playlist").click()
    t = app.toast("Removed Kind Radio")
    expect(p.locator(".pl-it", has_text="Kind Radio")).to_have_count(0)
    t.get_by_role("button", name="Undo").click()
    expect(p.locator(".pl-it", has_text="Kind Radio")).to_have_count(1)
    app.no_sheet()
    p.get_by_role("button", name="Options for Kind Radio").click()
    app.sheet().get_by_role("button", name="Remove from playlist").click()
    wait_for(lambda: "Kind Radio" not in items(seeded, pid), timeout=10, what="delayed delete sent")
    # repeat cycles; Play all hits the offline speaker
    rep = p.locator(".pl-rep")
    expect(rep).to_have_attribute("aria-label", "Repeat: off")
    rep.click()
    expect(rep).to_have_attribute("aria-label", "Repeat: whole playlist")
    rep.click()
    expect(rep).to_have_attribute("aria-label", "Repeat: one item")
    rep.click()
    expect(rep).to_have_attribute("aria-label", "Repeat: off")
    p.locator(".pl-play").click()
    app.toast("Can't reach the speaker", timeout=SPEAKER_WAIT)
    # rename from the More menu
    p.get_by_role("button", name=f"More for {name}").click()
    app.sheet().get_by_role("button", name="Rename").click()
    expect(p.locator("dialog.ov")).to_have_count(1)  # the menu sheet has closed, the name sheet is open
    sheet = app.sheet()
    sheet.get_by_label("Playlist name").fill(name + " (renamed)")
    sheet.get_by_role("button", name="Save name").click()
    app.no_sheet()
    app.header(name + " (renamed)")
    # delete with Undo, then for good
    p.get_by_role("button", name=f"More for {name} (renamed)").click()
    app.sheet().get_by_role("button", name="Delete playlist").click()
    t = app.toast(f"Deleted {re.escape(name)} \\(renamed\\)")
    app.header("Playlists")
    expect(p.locator(".pl-row", has_text=name)).to_have_count(0)
    t.get_by_role("button", name="Undo").click()
    expect(p.locator(".pl-row", has_text=name)).to_have_count(1)
    p.locator(".pl-row", has_text=name).locator("a.tb-stretch").click()
    p.get_by_role("button", name=re.compile("^More for")).click()
    app.sheet().get_by_role("button", name="Delete playlist").click()
    wait_for(lambda: not any(x["id"] == pid for x in seeded.get("/playlists")), timeout=10, what="playlist deleted")
    app.clean("playlists phone")


def test_playlists_desktop_split(make_app, seeded):
    app = make_app("operator", device="desktop", route="playlists")
    p = app.page
    name = f"Desk list {int(time.time()) % 10000}"
    create(app, name)
    expect(p.locator(".pl-row.sel")).to_contain_text(name)
    pane = p.locator(".pl-pane")
    expect(pane.locator(".pl-name")).to_have_text(name)
    pid = int(app.hash().rsplit("/", 1)[1])
    # the empty playlist's "+" in the list opens the Add item sheet
    p.locator(".pl-row", has_text=name).get_by_role("button", name=f"Add items to {name}").click()
    sheet = app.sheet()
    sheet.locator(".tb-chips").get_by_role("radio", name="Text", exact=True).click()
    for text in ("First message", "Second message"):
        sheet.get_by_label("Text", exact=True).fill(text)
        sheet.get_by_role("button", name="Add text").click()
        app.toast("Text added")
    sheet.get_by_role("button", name="Done").click()
    app.no_sheet()
    expect(p.locator(".pl-row", has_text=name)).to_contain_text("2 items")
    app.soft(lambda: expect(pane.locator(".pl-it")).to_have_count(2),
             "desktop detail pane refreshes after items are added from the list row's + button")
    app.go("playlists")  # re-open: the pane loads fresh
    p.locator(".pl-row", has_text=name).locator("a.tb-stretch").click()
    pane = p.locator(".pl-pane")
    expect(pane.locator(".pl-it")).to_have_count(2)
    # keyboard on the drag handle
    pane.get_by_role("button", name=re.compile("^Drag to move First message")).focus()
    p.keyboard.press("ArrowDown")
    wait_for(lambda: items(seeded, pid) == ["Second message", "First message"], what="keyboard move")
    p.keyboard.press("ArrowUp")
    wait_for(lambda: items(seeded, pid) == ["First message", "Second message"], what="keyboard move back")
    # drag the second item above the first (mouse, from the handle)
    grip = pane.locator(".pl-it").nth(1).locator(".pl-grip")
    box = grip.bounding_box()
    first = pane.locator(".pl-it").nth(0).bounding_box()
    p.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    p.mouse.down()
    p.mouse.move(box["x"] + box["width"] / 2, first["y"] + 2, steps=12)
    p.mouse.up()
    wait_for(lambda: items(seeded, pid) == ["Second message", "First message"], what="drag reorder saved")
    # item menu is a popover on large screens
    pane.get_by_role("button", name="Options for First message").click()
    expect(p.locator(".popover.tb-pop")).to_be_visible()
    p.keyboard.press("Escape")
    expect(p.locator(".popover.tb-pop")).to_have_count(0)
    # switching selection in place
    other = f"Desk other {int(time.time()) % 10000}"
    create(app, other)
    expect(pane.locator(".pl-name")).to_have_text(other)
    p.locator(".pl-row", has_text=name).locator("a.tb-stretch").click()
    expect(pane.locator(".pl-name")).to_have_text(name)
    assert app.hash() == f"#/playlists/{pid}"
    app.clean("playlists desktop")


def test_playlists_viewer_read_only(make_app, seeded):
    pl = seeded.post("/playlists", {"name": f"Viewer sees {int(time.time()) % 10000}"}).json()
    seeded.post(f"/playlists/{pl['id']}/items", {"kind": "tts", "source": "Read only item", "lang": "en"})
    app = make_app("viewer", device="ipad", route="playlists")
    p = app.page
    expect(p.locator("#view .phd-r button.btn.primary")).to_have_count(0)
    row = p.locator(".pl-row", has_text=pl["name"])
    expect(row.locator(".tb-rb")).to_have_count(0)
    row.locator("a.tb-stretch").click()
    app.header(pl["name"])
    expect(p.locator(".pl-it")).to_have_count(1)
    for sel in (".pl-play", ".pl-grip", ".pl-more", ".pl-links", ".tb-stretch"):
        expect(p.locator(f"#view {sel}")).to_have_count(0)
    app.clean("playlists viewer")
