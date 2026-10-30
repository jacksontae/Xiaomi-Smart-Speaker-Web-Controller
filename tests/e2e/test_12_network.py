"""Network failures (requests aborted with page.route): each surface says so plainly and recovers."""
import re

from playwright.sync_api import expect

NETWORK = "Can't reach the server"


def test_list_load_failure_and_retry(make_app, seeded):
    app = make_app("operator", device="desktop", go=False)
    p = app.page
    p.route("**/playlists", lambda r: r.abort())
    app.go("playlists")
    err = p.locator(".pl-listcol .tb-err")
    expect(err).to_contain_text(NETWORK)
    p.unroute("**/playlists")
    err.get_by_role("button", name="Try again").click()
    expect(p.locator(".pl-listcol .tb-err")).to_have_count(0)
    app.clean("playlists retry")


def test_write_failure_toast(make_app, seeded):
    app = make_app("operator", device="phone", route="announce")
    p = app.page
    p.route("**/phrases", lambda r: r.abort() if r.request.method == "POST" else r.continue_())
    box = p.locator(".ann-phrases")
    box.get_by_role("button", name="Add phrase").click()
    box.locator("input.ann-newin").fill("will fail")
    box.get_by_role("button", name="Add", exact=True).click()
    app.toast(NETWORK)
    expect(box.locator("input.ann-newin")).to_have_value("will fail")  # nothing lost
    app.clean("phrase write failure")


def test_boot_failure_screen(make_app, seeded):
    app = make_app("operator", device="ipad", go=False)
    p = app.page
    p.route("**/auth/state", lambda r: r.abort())
    app.go("", wait_header=False)
    expect(p.locator("h1")).to_have_text("The app couldn't start")
    expect(p.locator("p.muted")).to_contain_text(NETWORK)
    p.unroute("**/auth/state")
    p.get_by_role("button", name="Try again").click()
    app.header("Now playing")
    app.clean("boot failure")


def test_view_module_blocked(make_app, seeded):
    """A page script that never arrives (ad blocker, dropped network) explains itself and retries."""
    app = make_app("owner", device="desktop")
    p = app.page
    p.route("**/js/views/activity.js*", lambda r: r.abort())
    app.go("activity", wait_header=False)
    expect(p.locator("#view p.lead")).to_contain_text("This page didn't load.")
    p.unroute("**/js/views/activity.js*")
    p.locator("#view").get_by_role("button", name="Try again").click()
    # browsers cache a failed dynamic import for the page's lifetime: the retry may need a reload
    app.soft(lambda: app.header("Activity"), "Try again after a blocked page script loads the page")
    # app.js logs the failed import on purpose; anything else is still an error
    app.errors = [e for e in app.errors if "Failed to fetch dynamically imported module" not in e]
    app.clean("module blocked")


def test_status_failure_shows_offline(make_app, seeded):
    app = make_app("viewer", device="phone", go=False)
    p = app.page
    p.route("**/status", lambda r: r.abort())
    app.go("")
    expect(p.locator(".np-title")).to_have_text(re.compile("Can't reach"), timeout=15_000)
    expect(p.locator(".spoff").first).to_have_text("Offline")
    app.clean("status failure")


def test_members_save_failure_inline(make_app, seeded):
    app = make_app("owner", device="desktop", route="members")
    p = app.page
    p.locator(".m-row", has_text="Vera Viewer").click()
    pane = p.locator(".m-pane")
    p.route("**/users/*", lambda r: r.abort() if r.request.method == "PATCH" else r.continue_())
    pane.get_by_label("Display name").fill("Vera Changed")
    pane.get_by_role("button", name="Save").click()
    expect(pane.locator(".m-save .form-error")).to_contain_text(NETWORK)
    app.clean("members failure")
