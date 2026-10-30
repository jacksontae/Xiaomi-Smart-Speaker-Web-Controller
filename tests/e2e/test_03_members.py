"""Members (owner): add with validation, edit name/role, new password, disable, delete, guards on yourself."""
import re
import time

from playwright.sync_api import expect


def add_member(app, name, username, password, role=None):
    p = app.page
    btn = p.locator("#view button.c-large-only", has_text="Add member")
    (btn if btn.is_visible() else p.get_by_role("button", name="Add member").first).click()
    sheet = app.sheet()
    sheet.get_by_label("Display name").fill(name)
    sheet.get_by_label("Username").fill(username)
    sheet.get_by_label("Starting password").fill(password)
    if role:
        sheet.get_by_role("radio", name=role).click()
    sheet.locator("button[type=submit]").click()
    return sheet


def test_members_desktop_crud(make_app, seeded):
    app = make_app("owner", device="desktop", route="members")
    p = app.page
    app.header("Members")
    expect(p.locator(".m-row", has_text="Olivia Owner")).to_contain_text("(you)")
    # validation, in order: name, username, password
    sheet = add_member(app, "", "", "")
    expect(sheet.locator(".form-error")).to_have_text("Enter a display name first")
    sheet.get_by_label("Display name").fill("Wipa Test")
    sheet.locator("button[type=submit]").click()
    expect(sheet.locator(".form-error")).to_have_text("Enter a username first")
    sheet.get_by_label("Username").fill("vera")  # taken
    sheet.locator("button[type=submit]").click()
    expect(sheet.locator(".form-error")).to_have_text("The password needs at least 8 characters")
    sheet.get_by_label("Starting password").fill("wipa-pass-123")
    sheet.locator("button[type=submit]").click()
    expect(sheet.locator(".form-error")).to_have_text("That username is already taken. Pick another.")
    sheet.get_by_label("Username").fill("Bad Name!")
    sheet.locator("button[type=submit]").click()
    expect(sheet.locator(".form-error")).to_have_text(re.compile("^That isn.t valid"))
    uname = f"wipa{int(time.time()) % 100000}"
    sheet.get_by_label("Username").fill(uname)
    sheet.get_by_role("radio", name="Viewer").click()
    expect(sheet.locator(".m-sec .small")).to_contain_text("Can't control the speaker")
    sheet.locator("button[type=submit]").click()
    app.toast("Wipa Test added")
    app.no_sheet()
    row = p.locator(".m-row", has_text="Wipa Test")
    expect(row).to_contain_text("Viewer")
    expect(row).to_contain_text("Hasn't signed in yet")
    # the new member is selected in the desktop pane
    pane = p.locator(".m-pane")
    expect(pane.locator(".m-ed-name")).to_have_text("Wipa Test")
    # rename + make operator
    pane.get_by_label("Display name").fill("")
    pane.get_by_role("button", name="Save").click()
    expect(pane.locator(".m-save .form-error")).to_have_text("Enter a display name first")
    pane.get_by_label("Display name").fill("Wipa Edited")
    pane.get_by_role("radio", name="Operator").click()
    pane.get_by_role("button", name="Save").click()
    expect(p.locator(".m-row", has_text="Wipa Edited")).to_contain_text("Operator")
    assert seeded.user(uname)["role"] == "operator"
    pane = p.locator(".m-pane")
    # new password: too short, then fine
    pane.locator(".m-pw input").fill("short")
    pane.get_by_role("button", name="Set new password").click()
    expect(pane.locator(".m-pw + p")).to_have_text("The password needs at least 8 characters")
    pane.locator(".m-pw input").fill("wipa-new-pass-1")
    pane.get_by_role("button", name="Set new password").click()
    expect(pane.locator(".m-pw + p")).to_have_text("New password set. They were signed out of every device.")
    # disable / enable
    sw = pane.locator("input.switch")
    sw.check()
    expect(p.locator(".m-row", has_text="Wipa Edited")).to_contain_text("Disabled")
    expect(p.locator(".m-row", has_text="Wipa Edited")).to_contain_text("Can't sign in anymore")
    assert seeded.user(uname)["disabled"] is True
    sw.uncheck()
    expect(p.locator(".m-row", has_text="Wipa Edited").locator(".c-badge")).to_have_text("Operator")
    # delete: Keep first, then Delete
    pane.get_by_role("button", name="Delete member").click()
    expect(pane.locator(".c-confirm")).to_contain_text("Delete Wipa Edited?")
    pane.get_by_role("button", name="Keep").click()
    expect(pane.locator(".c-confirm")).to_be_hidden()
    pane.get_by_role("button", name="Delete member").click()
    pane.locator(".c-confirm button.danger").click()
    app.toast("Wipa Edited deleted")
    expect(p.locator(".m-row", has_text="Wipa Edited")).to_have_count(0)
    assert seeded.user(uname) is None
    # header link to sign-in methods
    p.locator("#view a.m-desk-only", has_text="Sign-in methods").click()
    app.header("Sign-in methods")
    app.clean("members desktop")


def test_members_self_guards(make_app, seeded):
    app = make_app("owner", device="desktop", route="members")
    p = app.page
    p.locator(".m-row", has_text="(you)").click()
    pane = p.locator(".m-pane")
    expect(pane.locator(".m-role-self")).to_have_text("Owner")
    expect(pane).to_contain_text("You can't change your own role.")
    expect(pane.locator("input.switch")).to_have_count(0)
    expect(pane.get_by_role("button", name="Delete member")).to_have_count(0)
    # the server guards stay in place even if a request gets through
    me = seeded.user("owner")
    r = app.ctx.request.patch(f"/users/{me['id']}", headers={"X-Requested-With": "speaker-web"},
                              data={"role": "viewer"})
    assert r.status == 409
    r = app.ctx.request.delete(f"/users/{me['id']}", headers={"X-Requested-With": "speaker-web"})
    assert r.status == 409
    app.clean("self guards")


def test_members_phone_sheet(make_app, seeded):
    app = make_app("owner", device="phone", route="members")
    p = app.page
    app.header("Members")
    expect(p.locator("#view a.phd-back")).to_have_text(re.compile("Account"))
    uname = f"pho{int(time.time()) % 100000}"
    p.get_by_role("button", name="Add member").first.click()
    sheet = app.sheet()
    sheet.get_by_label("Display name").fill("Phone Person")
    sheet.get_by_label("Username").fill(uname)
    sheet.get_by_label("Starting password").fill("phone-pass-123")
    sheet.locator("button[type=submit]").click()
    app.toast("Phone Person added")
    app.no_sheet()
    p.locator(".m-row", has_text="Phone Person").click()
    sheet = app.sheet()
    sheet.get_by_label("Display name").fill("Phone Renamed")
    sheet.get_by_role("button", name="Save").click()
    app.toast("Saved")
    app.no_sheet()
    expect(p.locator(".m-row", has_text="Phone Renamed")).to_be_visible()
    p.locator(".m-row", has_text="Phone Renamed").click()
    sheet = app.sheet()
    sheet.get_by_role("button", name="Delete member").click()
    sheet.locator(".c-confirm button.danger").click()
    app.toast("Phone Renamed deleted")
    expect(p.locator("dialog.ov[open]")).to_have_count(0)
    app.clean("members phone")


def test_members_ipad_dialog(make_app, seeded):
    app = make_app("owner", device="ipad", route="members", lang="th", theme="dark")
    p = app.page
    app.header("สมาชิก")
    p.locator(".m-row", has_text="Vera Viewer").click()
    sheet = app.sheet()
    expect(sheet.locator("h2")).to_have_text("Vera Viewer")
    sheet.locator(".sheet-close").click()
    expect(p.locator("dialog.ov[open]")).to_have_count(0)
    app.clean("members ipad th")
