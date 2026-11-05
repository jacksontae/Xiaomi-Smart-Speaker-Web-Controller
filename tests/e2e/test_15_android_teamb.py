"""Android look on Playlists, Music and Schedule (page team B) and the shared Android kit (static/js/android-kit.js):
extended FABs on phones (shrink on scroll, hidden on tablets and off Android), the Play all | Shuffle button group,
the full-screen schedule editor (Save in its top bar, system back closes it), the search field with clear button,
and the tablet two-pane layouts. /status is mocked as in test_14 (the speaker is offline in this suite)."""
import time

from playwright.sync_api import expect

from . import test_14_android_shell as shell

android_app = shell.android_app  # the fixture: Android user agent, mocked /status
ANDROID_TABLET = shell.ANDROID_TABLET


def make_playlist(api, name, items=2):
    p = api.post("/playlists", {"name": name}).json()
    for i in range(items):
        api.post(f"/playlists/{p['id']}/items", {"kind": "url", "source": f"https://audio.example.com/{i}.mp3",
                                                 "title": f"{name} clip {i + 1}"})
    return p


def test_playlists_phone_fab_and_button_group(android_app, seeded):
    name = f"Android list {int(time.time()) % 10000}"
    pl = make_playlist(seeded, name)
    app = android_app("operator", route="playlists", playing=False)
    p = app.page
    fab = p.locator(".ak-fab")
    expect(fab).to_be_visible()
    expect(fab).to_have_attribute("aria-label", "New playlist")
    expect(p.locator(".phd .btn.primary")).to_be_hidden()  # the header button the FAB stands in for
    p.wait_for_timeout(500)  # entrance animation
    box = fab.bounding_box()
    assert box["height"] == 56 and 412 - (box["x"] + box["width"]) >= 15, box
    assert box["y"] + 56 <= p.locator(".tabbar").bounding_box()["y"], "the FAB sits above the nav pill"
    fab.click()
    sheet = app.sheet()
    sheet.get_by_label("Playlist name").fill(f"{name} new")
    sheet.locator("button[type=submit]").click()
    app.no_sheet()
    app.header()
    expect(p.locator(".pl-name")).to_have_text(f"{name} new")
    # detail: Add item is the FAB; Play all | Shuffle connected, 2 px apart
    p.evaluate(f"location.hash = '#/playlists/{pl['id']}'")
    expect(p.locator(".pl-name")).to_have_text(name)
    add = p.locator(".ak-fab")
    expect(add).to_have_count(1)  # the list page's FAB went with the list page
    expect(add).to_have_attribute("aria-label", "Add item")
    expect(p.locator(".pl-links .pl-add")).to_be_hidden()
    a, b = p.locator(".pl-play").bounding_box(), p.locator(".pl-shuf").bounding_box()
    assert abs(b["x"] - (a["x"] + a["width"]) - 2) <= 1 and a["height"] == 56, (a, b)
    add.click()
    expect(app.sheet().locator(".tb-chips")).to_be_visible()
    p.go_back()  # system back closes the sheet, the page stays
    app.no_sheet()
    assert app.hash() == f"#/playlists/{pl['id']}"
    app.clean("android playlists phone")


def test_fab_shrinks_on_scroll(android_app, seeded):
    pl = make_playlist(seeded, f"Long {int(time.time()) % 10000}", items=14)
    app = android_app("owner", route=f"playlists/{pl['id']}", playing=False)
    p = app.page
    fab = p.locator(".ak-fab")
    expect(fab).to_be_visible()
    p.wait_for_timeout(500)  # entrance animation
    wide = fab.bounding_box()["width"]
    p.mouse.wheel(0, 400)
    expect(fab).to_have_class("ak-fab small")
    p.wait_for_timeout(500)
    assert fab.bounding_box()["width"] == 56, "icon-only while scrolling down"
    p.mouse.wheel(0, -200)
    expect(fab).not_to_have_class("ak-fab small")
    p.wait_for_timeout(500)
    assert fab.bounding_box()["width"] == wide
    app.clean("fab scroll")


def test_schedule_full_screen_editor(android_app, seeded):
    name = f"Android sched {int(time.time()) % 10000}"
    app = android_app("operator", route="schedule", playing=False)
    p = app.page
    expect(p.locator(".sc-bar .btn")).to_be_hidden()
    p.locator(".ak-fab", has_text="New schedule").click()
    dlg = p.locator("dialog.ak-full[open]")
    expect(dlg).to_be_visible()
    panel = dlg.locator(".ak-full-panel")
    # it slides up; under load the animation may not have started yet, so wait for where it ends
    panel.evaluate("el => Promise.all(el.getAnimations().map((a) => a.finished))")
    p.wait_for_function("""() => { const r = document.querySelector('dialog.ak-full[open] .ak-full-panel')
      .getBoundingClientRect(); return r.x === 0 && r.y === 0 && r.width === 412; }""", timeout=5_000)
    expect(dlg.locator(".ak-full-t")).to_have_text("New schedule")
    expect(dlg.locator(".sc-form button[type=submit]")).to_have_count(0)  # Save lives in the top bar only
    save = dlg.locator(".ak-full-bar").get_by_role("button", name="Save")
    save.click()
    expect(dlg.locator(".form-error")).to_have_text("Give it a name before saving")
    # system back closes it and stays on the page
    p.go_back()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    assert app.hash() == "#/schedule"
    p.locator(".ak-fab").click()
    dlg = p.locator("dialog.ak-full[open]")
    dlg.get_by_label("Name").fill(name)
    dlg.get_by_label("Message to announce").fill("We are open")
    dlg.locator("input.sc-timein").fill("07:45")
    dlg.locator(".ak-full-bar").get_by_role("button", name="Save").click()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    expect(p.locator(".sc-row", has_text=name)).to_contain_text("07:45")
    assert any(s["name"] == name for s in seeded.get("/schedules")["items"])
    # closing with X takes the history entry back off: the next back leaves the page as usual
    p.locator(".sc-row", has_text=name).locator(".tb-stretch").click()
    dlg = p.locator("dialog.ak-full[open]")
    expect(dlg.locator(".ak-full-t")).to_have_text("Edit schedule")
    dlg.locator(".ak-full-x").click()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    p.wait_for_timeout(300)
    assert app.hash() == "#/schedule"
    app.clean("android schedule phone")


def test_music_search_field(android_app, seeded):
    app = android_app("operator", route="music/youtube", playing=False)
    p = app.page
    form = p.locator("form.tb-search-a")
    expect(form.locator(".tb-sic")).to_be_visible()
    clear = form.get_by_role("button", name="Clear search")
    expect(clear).to_be_hidden()
    form.locator("input").fill("jazz")
    expect(clear).to_be_visible()
    expect(form.get_by_role("button", name="Search", exact=True)).to_be_visible()
    clear.click()
    expect(form.locator("input")).to_have_value("")
    expect(clear).to_be_hidden()
    app.clean("android music search")


def test_tablet_two_panes(android_app, seeded):
    pl = make_playlist(seeded, f"Tablet {int(time.time()) % 10000}")
    app = android_app("owner", device=ANDROID_TABLET, route=f"playlists/{pl['id']}", playing=False)
    p = app.page
    expect(p.locator(".pl-desk .pl-split")).to_be_visible()
    expect(p.locator(".pl-pane .pl-name")).to_have_text(pl["name"])
    expect(p.locator(".ak-fab")).to_be_hidden()  # tablets keep the header button
    expect(p.locator(".phd .btn.primary", has_text="New playlist")).to_be_visible()
    p.evaluate("location.hash = '#/schedule'")
    app.header()
    expect(p.locator(".sc-left .sc-bar .btn", has_text="New schedule")).to_be_visible()
    p.locator(".sc-left .sc-bar .btn").click()
    expect(p.locator(".sc-pane .sc-form")).to_be_visible()
    expect(p.locator("dialog.ov")).to_have_count(0)  # side by side, no dialog
    app.clean("android tablet panes")


def test_glass_look_has_no_kit(make_app, seeded):
    app = make_app("owner", device="phone", route="schedule")
    p = app.page
    expect(p.get_by_role("button", name="New schedule")).to_be_visible()
    expect(p.locator(".ak-fab")).to_have_count(0)
    assert not p.evaluate("performance.getEntriesByType('resource').some((e) => e.name.includes('android-kit.css'))")
    p.get_by_role("button", name="New schedule").click()
    expect(app.sheet().locator(".sc-form button[type=submit]")).to_be_visible()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    app.clean("glass look unchanged")


def test_fab_goes_when_the_page_is_left_while_loading(android_app, seeded):
    """Leaving Playlists before it finished rendering must not leave its FAB on the next page."""
    app = android_app("operator", route="announce", playing=False)
    p = app.page
    held = []  # Playlists waits for its stylesheet; hold it back until we have moved on
    p.route("**/views/playlists.css*", lambda route: held.append(route))
    p.evaluate("location.hash = '#/playlists'")
    for _ in range(50):
        if held:
            break
        p.wait_for_timeout(50)
    assert held, "Playlists asked for its stylesheet"
    p.evaluate("location.hash = '#/announce'")
    expect(p.locator(".phd .pt")).to_have_text("Announce")
    held[0].continue_()
    p.wait_for_timeout(800)  # Playlists finishes rendering, unseen
    expect(p.locator(".ak-fab")).to_have_count(0)
    assert p.evaluate("document.documentElement.hasAttribute('data-fab')") is False
    p.unroute("**/views/playlists.css*")
    app.clean("fab left while loading")
