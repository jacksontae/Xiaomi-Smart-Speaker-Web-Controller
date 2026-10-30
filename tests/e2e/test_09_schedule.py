"""Schedule: create with validation (name, text, time, days, once), switch off/on, edit, test-it-now error path,
delete with Keep/Delete, playlist schedules, desktop side panel vs sheet, viewer read-only."""
import time

from playwright.sync_api import expect

from .e2ekit import SPEAKER_WAIT


def editor(app, desk):
    return app.page.locator(".sc-pane .sc-form") if desk else app.sheet().locator(".sc-form")


def test_schedule_say_crud_ipad(make_app, seeded, drained):
    app = make_app("operator", device="ipad", route="schedule")
    p = app.page
    expect(p.locator(".sc-clock")).to_contain_text("Speaker time now")
    name = f"Opening {int(time.time()) % 10000}"
    p.get_by_role("button", name="New schedule").click()
    f = editor(app, False)
    save = f.locator("button[type=submit]")
    save.click()
    expect(f.locator(".form-error")).to_have_text("Give it a name before saving")
    f.get_by_label("Name").fill(name)
    save.click()
    expect(f.locator(".form-error")).to_have_text("Type the message to announce")
    f.get_by_label("Message to announce").fill("We are open, welcome")
    save.click()
    expect(f.locator(".form-error")).to_have_text("Pick a time")
    f.locator("input.sc-timein").fill("07:30")
    # repeat presets and day toggles
    presets = f.locator(".sc-presets")
    presets.get_by_role("button", name="Mon–Fri").click()
    expect(f.locator(".sc-summary")).to_have_text("Plays Monday to Friday")
    for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
        f.locator(".sc-days").get_by_role("button", name=d).click()
    expect(f.locator(".sc-summary")).to_have_text("Pick at least one day")
    save.click()
    expect(f.locator(".form-error")).to_have_text("Pick at least one day")
    f.locator(".sc-days").get_by_role("button", name="Saturday").click()
    expect(f.locator(".sc-summary")).to_have_text("Plays every Saturday")
    presets.get_by_role("button", name="Every day").click()
    # own volume
    f.locator(".sc-volbox input.switch").check()
    f.locator("input.sc-range").fill("35")
    expect(f.locator(".sc-volv")).to_have_text("35%")
    save.click()
    app.no_sheet()
    row = p.locator(".sc-row", has_text=name)
    expect(row).to_contain_text("07:30")
    expect(row).to_contain_text("Every day")
    s = next(x for x in seeded.get("/schedules")["items"] if x["name"] == name)
    assert (s["time"], s["days"], s["volume"], s["action"]) == ("07:30", [0, 1, 2, 3, 4, 5, 6], 0.35, "say")
    # switch off -> "Off" group
    row.get_by_role("switch", name=f"Turn on {name}").uncheck()
    expect(p.locator(".sc-group", has_text="Off").locator(".sc-row", has_text=name)).to_be_visible()
    row = p.locator(".sc-row", has_text=name)
    row.get_by_role("switch", name=f"Turn on {name}").check()
    expect(p.locator(".sc-group", has_text="Off").locator(".sc-row", has_text=name)).to_have_count(0)
    # edit: change to once on a date
    p.get_by_role("button", name=f"Edit {name} at 07:30").click()
    f = editor(app, False)
    expect(f.locator(".sc-info")).to_contain_text("Not played yet")
    f.locator(".sc-presets").get_by_role("button", name="Once").click()
    expect(f.locator(".sc-summary")).to_contain_text("Plays once on")
    f.locator("input.sc-timein").fill("23:59")
    shown = f.locator("input.sc-datein").input_value()
    app.soft(lambda: expect(f.locator(".sc-summary")).not_to_contain_text("on …"),
             "switching a repeating schedule to Once uses the date the field shows")
    f.locator("button[type=submit]").click()
    app.page.wait_for_timeout(500)
    # a successful save closes the sheet (so the editor's error line is gone, not empty)
    app.soft(lambda: expect(p.locator("dialog.ov[open] .sc-form")).to_have_count(0),
             "saving 'Once' without touching the (pre-filled) date works")
    if p.locator("dialog.ov[open]").count():
        f.locator("input.sc-datein").fill(shown)  # workaround: touch the date field
        f.locator("button[type=submit]").click()
    app.no_sheet()
    expect(p.locator(".sc-row", has_text=name)).to_contain_text("Once,")
    # Test it now on a saved, unchanged schedule -> runs it -> the speaker is offline
    p.get_by_role("button", name=f"Edit {name} at 23:59").click()
    f = editor(app, False)
    f.get_by_role("button", name="Test it now").click()
    app.toast("Can't reach the speaker", timeout=SPEAKER_WAIT)
    # delete: Keep, then Delete
    f.get_by_role("button", name="Delete this schedule").click()
    expect(f.locator(".sc-del")).to_contain_text(f"Delete “{name}”? This can’t be undone.")
    f.get_by_role("button", name="Keep").click()
    f.get_by_role("button", name="Delete this schedule").click()
    f.locator(".sc-del button.danger").click()
    app.toast(f"Deleted {name}")
    app.no_sheet()
    expect(p.locator(".sc-row", has_text=name)).to_have_count(0)
    assert not any(x["name"] == name for x in seeded.get("/schedules")["items"])
    # "Announce now" in the mode switch goes back
    p.get_by_role("tablist", name="Announce mode").get_by_role("tab", name="Announce now").click()
    app.header("Announce")
    assert app.hash() == "#/announce"
    app.clean("schedule ipad")


def test_schedule_playlist_desktop_panel(make_app, seeded, drained):
    pl = seeded.post("/playlists", {"name": f"Lunch music {int(time.time()) % 10000}"}).json()
    seeded.post(f"/playlists/{pl['id']}/items", {"kind": "tts", "source": "Lunch time", "lang": "en"})
    app = make_app("operator", device="desktop", route="schedule")
    p = app.page
    expect(p.locator(".sc-pane")).to_contain_text("Pick an item on the left to edit it, or make a new one.")
    p.get_by_role("button", name="New schedule").click()
    f = editor(app, True)
    name = f"Lunch {int(time.time()) % 10000}"
    f.get_by_label("Name").fill(name)
    f.get_by_role("radiogroup", name="What to play").get_by_role("radio", name="Play a playlist").click()
    f.get_by_label("Playlist").select_option("")
    f.locator("input.sc-timein").fill("12:00")
    f.locator("button[type=submit]").click()
    expect(f.locator(".form-error")).to_have_text("Choose a playlist")
    f.get_by_label("Playlist").select_option(str(pl["id"]))
    f.locator(".sc-swrow", has_text="Shuffle songs").locator("input").check()
    f.locator("button[type=submit]").click()
    row = p.locator(".sc-row", has_text=name)
    expect(row).to_contain_text(pl["name"])
    expect(p.locator(".sc-pane button[type=submit]")).to_have_text("Saved")
    s = next(x for x in seeded.get("/schedules")["items"] if x["name"] == name)
    assert s["playlist_id"] == pl["id"] and s["shuffle"] is True
    # edit in the panel; a dirty form tests the edited version (plays the playlist) -> offline speaker
    row.locator("button.tb-stretch").click()
    f = editor(app, True)
    f.get_by_label("Name").fill(name + " v2")
    f.get_by_role("button", name="Test it now").click()
    app.toast("Can't reach the speaker", timeout=SPEAKER_WAIT)
    f.locator("button[type=submit]").click()
    expect(p.locator(".sc-row", has_text=name + " v2")).to_be_visible()
    seeded.delete(f"/schedules/{s['id']}")
    app.clean("schedule desktop")


def test_schedule_viewer_read_only(make_app, seeded):
    seeded.post("/schedules", {"name": "Viewer visible", "enabled": True, "action": "say", "text": "Hello",
                               "lang": "en", "time": "08:00", "days": [0, 1, 2, 3, 4, 5, 6], "date": None,
                               "volume": None, "playlist_id": None, "shuffle": False})
    app = make_app("viewer", device="phone", route="schedule")
    p = app.page
    row = p.locator(".sc-row", has_text="Viewer visible")
    expect(row).to_be_visible()
    expect(row.locator("input.switch")).to_have_count(0)
    expect(row.locator("button")).to_have_count(0)
    expect(p.get_by_role("button", name="New schedule")).to_have_count(0)
    app.clean("schedule viewer")
