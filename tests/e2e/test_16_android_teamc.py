"""Android look on the owner/account pages (page team C): Members (Add member FAB, full-screen editor and add form on
phones, list | editor panes on tablets in landscape), Activity (filter chips, no second filter on tablets), one
centred column on tablets for Settings / Sign-in methods / Account, the Help search field, tile tones, and the shared
fixes made alongside (danger links keep their colour, Now's top bar has no speaker chip on Android phones).
/status is mocked as in test_14."""
import time

from playwright.sync_api import expect

from . import test_14_android_shell as shell
from .e2ekit import VIEWER, wait_for

android_app = shell.android_app  # the fixture: Android user agent, mocked /status
ANDROID_TABLET = shell.ANDROID_TABLET


def test_members_phone_fab_and_full_screen_editor(android_app, seeded):
    vera = seeded.ensure_user(VIEWER)
    app = android_app("owner", route="members", playing=False)
    p = app.page
    fab = p.locator(".ak-fab")
    expect(fab).to_be_visible()
    expect(fab).to_have_attribute("aria-label", "Add member")
    expect(p.locator(".phd .iconbtn", has=p.locator("use[href='#i-plus']"))).to_be_hidden()  # the FAB stands in for it
    # edit: full-screen dialog, Save in its top bar, no Save button in the body
    p.locator(".m-row", has_text=vera["display_name"]).click()
    dlg = p.locator("dialog.ak-full[open]")
    expect(dlg).to_be_visible()
    p.wait_for_timeout(500)  # entrance animation
    box = dlg.locator(".ak-full-panel").bounding_box()
    assert (round(box["x"]), round(box["y"]), box["width"]) == (0, 0, 412), f"full screen: {box}"
    expect(dlg.locator(".ak-full-t")).to_have_text(vera["display_name"])
    expect(dlg.locator(".m-ed .m-save .btn")).to_be_hidden()
    name = dlg.get_by_label("Display name")
    name.fill("")
    dlg.locator(".ak-full-bar").get_by_role("button", name="Save").click()
    expect(dlg.locator(".m-save .form-error")).to_have_text("Enter a display name first")
    expect(dlg.locator(".m-save")).to_be_visible()
    new_name = f"Vera {int(time.time()) % 10000}"
    name.fill(new_name)
    dlg.locator(".ak-full-bar").get_by_role("button", name="Save").click()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    app.toast("Saved")
    expect(p.locator(".m-row", has_text=new_name)).to_be_visible()
    seeded.patch(f"/users/{vera['id']}", {"display_name": VIEWER["display_name"]})
    # system back closes the editor and stays on the page
    p.locator(".m-row").first.click()
    expect(p.locator("dialog.ak-full[open]")).to_be_visible()
    p.go_back()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    assert app.hash() == "#/members"
    # add member: full-screen form, the top-bar button submits it
    fab.click()
    dlg = p.locator("dialog.ak-full[open]")
    expect(dlg.locator(".ak-full-t")).to_have_text("Add member")
    expect(dlg.locator(".m-add button[type=submit]")).to_be_hidden()
    dlg.locator(".ak-full-bar").get_by_role("button", name="Add").click()
    expect(dlg.locator(".m-add .form-error")).to_have_text("Enter a display name first")
    dlg.locator(".ak-full-x").click()
    expect(p.locator("dialog.ak-full")).to_have_count(0)
    app.clean("android members phone")


def test_members_tablet_panes(android_app, seeded):
    vera = seeded.ensure_user(VIEWER)
    app = android_app("owner", device=ANDROID_TABLET, route="members", playing=False)
    p = app.page
    expect(p.locator(".ak-fab")).to_be_hidden()
    expect(p.locator(".phd .btn.primary", has_text="Add member")).to_be_visible()
    pane = p.locator(".m-pane")
    expect(pane).to_be_visible()
    p.locator(".m-row", has_text=vera["display_name"]).click()
    expect(pane.locator(".m-ed-name")).to_have_text(vera["display_name"])
    expect(p.locator("dialog.ov")).to_have_count(0)  # side by side, no dialog
    expect(pane.locator(".m-ed-head .btn", has_text="Save")).to_be_visible()  # Save next to the name
    lb, pb = p.locator(".m-list").bounding_box(), pane.bounding_box()
    assert pb["x"] > lb["x"] + lb["width"], (lb, pb)
    # AT_Members: Sign-in methods is a row of the Your account card, not a card of its own
    row = p.locator(".m-mine a[href='#/auth']")
    expect(row).to_be_visible()
    expect(row).to_contain_text("Sign-in methods")
    expect(p.locator(".m-methods")).to_be_hidden()
    row.click()
    wait_for(lambda: app.hash() == "#/auth", what="the sign-in methods page")
    app.clean("android members tablet")


def test_activity_chips_one_filter(android_app, seeded):
    for device, where in ((shell.ANDROID_PHONE, "phone"), (ANDROID_TABLET, "tablet")):
        app = android_app("owner", device=device, route="activity", playing=False)
        p = app.page
        chips = p.locator(".a-chips")
        expect(chips).to_be_visible()
        expect(p.locator(".a-seg")).to_have_count(0)
        expect(p.locator(".a-side")).to_have_count(0)  # the 1280 px tablet showed both before
        expect(p.get_by_role("radiogroup", name="Show only")).to_have_count(1)
        expect(chips.get_by_role("radio", name="All")).to_have_attribute("aria-checked", "true")
        chips.get_by_role("radio", name="Account").click()
        expect(chips.get_by_role("radio", name="Account")).to_have_attribute("aria-checked", "true")
        expect(chips.locator("[aria-checked=true] .a-chk")).to_be_visible()
        expect(p.locator(".a-row").first).to_be_visible()
        app.clean(f"android activity {where}")


def test_tablet_single_column_and_help_search(android_app, seeded):
    app = android_app("owner", device=ANDROID_TABLET, route="settings", playing=False)
    p = app.page
    cards = p.locator(".c-cols .c-card")
    expect(cards.first).to_be_visible()
    xs = {round(b["x"]) for b in (cards.nth(i).bounding_box() for i in range(cards.count()))}
    ws = {round(b["width"]) for b in (cards.nth(i).bounding_box() for i in range(cards.count()))}
    assert len(xs) == 1 and len(ws) == 1 and ws.pop() <= 680, (xs, ws)
    # the label of a text field in a card sits inside its box
    lab, inp = p.locator("label[for=s-name]").bounding_box(), p.locator("#s-name").bounding_box()
    assert inp["y"] < lab["y"] < inp["y"] + inp["height"], (lab, inp)
    p.evaluate("location.hash = '#/help'")
    expect(p.locator(".hp-input")).to_be_visible()
    sic, field = p.locator(".hp-sic").bounding_box(), p.locator(".hp-input").bounding_box()
    pad = p.locator(".hp-input").evaluate("e => parseFloat(getComputedStyle(e).paddingLeft)")
    assert sic["x"] + sic["width"] < field["x"] + pad, "the search icon doesn't cover the text"
    assert field["height"] == 56
    app.clean("android tablet column + help")


def test_tile_tones_and_danger_links(android_app, seeded):
    app = android_app("owner", route="account", playing=False)
    p = app.page
    out = p.locator(".c-row.danger .c-tile")
    expect(out).to_be_visible()
    plain = p.locator(".c-tile").first.evaluate("e => getComputedStyle(e).backgroundColor")
    assert out.evaluate("e => getComputedStyle(e).backgroundColor") != plain, "the sign-out tile keeps its error tone"
    # a danger link keeps its colour (android.css used to paint every .linkbtn primary)
    p.evaluate("location.hash = '#/schedule'")
    expect(p.locator(".sc-bar")).to_be_visible()  # schedule.css is in
    color = p.evaluate("""() => { const b = document.createElement('button'); b.className = 'linkbtn sc-delbtn';
      document.querySelector('#view').append(b); const c = getComputedStyle(b).color; b.remove(); return c; }""")
    err = p.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--md-error').trim()")
    assert color == "rgb(186, 26, 26)" and err == "#ba1a1a", (color, err)
    app.clean("android tones")


def test_now_bar_title_without_chip(android_app, seeded):
    app = android_app("owner", route="", playing=True)
    p = app.page
    expect(p.locator(".topbar .spchip")).to_have_count(0)
    expect(p.locator(".now-page .phd .spchip")).to_be_visible()  # the chip lives under the big title
    expect(p.locator(".topbar .topbar-r a[href='#/help']")).to_have_count(1)
    expect(p.locator(".topbar-t")).to_be_attached()
    app.clean("android now bar")
