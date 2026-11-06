"""Your data (Account): "Download my data" saves the member's JSON export; "Delete my account" needs the username
typed before the red button works, then signs out and the member can't sign in again; the only owner gets the
"Can't delete this account yet" sheet that leads to Members. Phone (rows on the Account page) and desktop (buttons
in Account & app settings)."""
import json
import re

import pytest
from playwright.sync_api import expect

from .e2ekit import BASE, pw


def open_delete(app, device):
    p = app.page
    if device == "phone":
        p.locator("button.c-row.danger", has_text="Delete my account").click()
    else:
        p.get_by_role("button", name="Delete account…").click()
    return app.sheet()


@pytest.mark.parametrize("device", ["phone", "desktop"])
def test_download_my_data(make_app, seeded, api, device):
    app = make_app("viewer", device=device, route="account")
    p = app.page
    expect(p.get_by_role("heading", name="Your data")).to_be_visible()
    if device == "phone":
        btn = p.locator("button.c-row", has_text="Download my data")
    else:
        btn = p.get_by_role("button", name="Download", exact=True)
    with p.expect_download() as info:
        btn.click()
    dl = info.value
    assert re.fullmatch(r"speaker-my-data-\d{4}-\d{2}-\d{2}\.json", dl.suggested_filename)
    with open(dl.path(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["profile"]["username"] == "vera"
    assert "password_hash" not in json.dumps(data)
    app.toast(f"Downloaded {re.escape(dl.suggested_filename)}")
    last = api.get("/activity?limit=1")[0]
    assert (last["actor"], last["action"]) == ("Vera Viewer", "data export")
    app.clean(f"download {device}")


@pytest.mark.parametrize("device", ["phone", "desktop"])
def test_delete_my_account(make_app, seeded, api, device):
    spec = {"username": f"leaver{device}", "display_name": f"Leaver {device.title()}",
            "password": pw("leaver-pass-123"), "role": "viewer"}
    api.ensure_user(spec)
    app = make_app(None, device=device, go=False)
    app.login_api(spec)
    app.go("account")
    p = app.page
    sheet = open_delete(app, device)
    expect(sheet.get_by_text("This removes for good")).to_be_visible()
    go = sheet.get_by_role("button", name="Delete my account")
    field = sheet.get_by_label(f"Type your username ({spec['username']}) to confirm")
    expect(go).to_be_disabled()
    field.fill("vera")  # someone else's username
    expect(go).to_be_disabled()
    field.fill(f"  {spec['username'].upper()} ")  # case and spaces don't matter, as on the server
    expect(go).to_be_enabled()
    go.click()
    expect(p.locator("form.auth-form")).to_be_visible(timeout=15_000)
    app.toast("Your account was deleted")
    expect(p.locator(".shell")).to_have_count(0)
    assert api.user(spec["username"]) is None
    r = app.ctx.request.post(f"{BASE}/auth/login", headers={"X-Requested-With": "speaker-web"},
                             data={"username": spec["username"], "password": spec["password"]})
    assert r.status == 401
    app.clean(f"delete {device}")
    entry = next(e for e in api.get("/activity?limit=20") if e["action"] == "member delete")
    assert (entry["actor"], entry["detail"]) == (spec["display_name"], f"{spec['username']} (own account)")
    if device == "desktop":  # the owner's Activity says whose account it was
        owner = make_app("owner", device=device, route="activity")
        row = owner.page.locator(".a-detail", has_text=f"{spec['username']} (their own account)").first
        expect(row).to_be_visible()
        owner.clean("activity")


@pytest.mark.parametrize("device,lang", [("phone", "th"), ("desktop", "en")])
def test_last_owner_is_refused(make_app, seeded, api, device, lang):
    # the owner must be the only enabled owner here, or this would really delete them
    others = [u for u in api.get("/users") if u["role"] == "admin" and not u["disabled"] and u["username"] != "owner"]
    for u in others:
        api.patch(f"/users/{u['id']}", {"disabled": True})
    try:
        assert [u["username"] for u in api.get("/users") if u["role"] == "admin" and not u["disabled"]] == ["owner"]
        app = make_app("owner", device=device, lang=lang, route="account")
        p = app.page
        if lang == "th":
            p.locator("button.c-row.danger", has_text="ลบบัญชีของฉัน").click()
            sheet = app.sheet()
            sheet.locator("input").fill("owner")
            sheet.get_by_role("button", name="ลบบัญชีของฉัน").click()
            title, members, header = "ยังลบบัญชีนี้ไม่ได้", "ไปที่สมาชิก", None
        else:
            sheet = open_delete(app, device)
            sheet.locator("input").fill("owner")
            sheet.get_by_role("button", name="Delete my account").click()
            title, members, header = "Can't delete this account yet", "Open Members", "Members"
        refused = p.locator("dialog.ov[open]", has_text=title)
        expect(refused).to_be_visible()
        expect(refused.get_by_role("alert")).to_be_visible()
        expect(p.locator("dialog.ov", has=p.locator("input"))).to_have_count(0)  # the confirm sheet closed
        refused.get_by_role("link", name=members).click()
        app.no_sheet()
        assert app.hash() == "#/members"
        app.header(header)
        assert api.user("owner") is not None
        app.clean(f"last owner {device}")
    finally:
        for u in others:
            api.patch(f"/users/{u['id']}", {"disabled": False})
