"""Sign-in methods switches and Speaker settings (owner): save, dirty state, validation, LAN scan."""
import json
import re

import httpx
from playwright.sync_api import expect

from .e2ekit import BASE

CID = "1234-abc.apps.googleusercontent.com"  # placeholder client id: the server only checks its shape


def auth_state():
    return httpx.get(f"{BASE}/auth/state").json()


def row_switch(p, title):
    return p.locator(".c-row", has=p.locator(".c-title", has_text=title)).locator("input.switch")


def test_signin_methods_google_and_passkey_switches(make_app, seeded):
    app = make_app("owner", device="desktop", route="auth")
    p = app.page
    app.header("Sign-in methods")
    save = p.locator(".c-save button.btn.primary")
    expect(save).to_be_disabled()
    g = row_switch(p, "Sign in with Google")
    expect(g).to_be_disabled()  # no client id yet
    cid = p.locator("#a-cid")
    cid.fill("not-a-client-id")
    expect(p.locator("#a-cid + p.form-error")).to_have_text("The client ID ends with .apps.googleusercontent.com")
    expect(g).to_be_disabled()
    cid.fill(CID)
    expect(p.locator("#a-cid + p.form-error")).to_have_text("")
    expect(g).to_be_enabled()
    expect(p.locator(".c-save .small")).to_have_text("Not saved yet")
    try:
        g.check()
        save.click()
        app.toast("Sign-in methods saved")
        app.soft(lambda: expect(save).to_be_disabled(), "Save turns disabled again after a successful save")
        st = auth_state()
        assert st["methods"]["google"] is True and st["google_client_id"] == CID
        # the sign-in page now offers Google (without loading Google's script until it is used)
        guest = make_app(None, device="phone")
        expect(guest.page.get_by_role("button", name="Continue with Google")).to_be_visible()
        guest.clean("login with google button")
        # Google off again; passkeys off -> the passkey button disappears from sign-in
        g.uncheck()
        pk = row_switch(p, "Sign in with a passkey")
        pk.uncheck()
        req = row_switch(p, "Require a passkey for owners")
        expect(req).to_be_disabled()
        expect(req.locator("xpath=..")).to_contain_text("Turn on passkey sign-in first.")
        save.click()
        app.toast("Sign-in methods saved")
        st = auth_state()
        assert st["methods"]["google"] is False and st["methods"]["passkey"] is False
        guest2 = make_app(None, device="desktop")
        expect(guest2.page.get_by_role("button", name="Sign in with a passkey")).to_have_count(0)
        pk.check()
        save.click()
        app.toast("Sign-in methods saved")
        assert auth_state()["methods"]["passkey"] is True
        # require passkeys while the owner has none: refused with the owner's name
        req.check()
        save.click()
        expect(p.locator("#view .page > p.form-error")).to_contain_text(
            "Every owner needs a passkey first. Still missing: Olivia Owner")
        expect(req.locator("xpath=..")).to_contain_text("Still missing")
        # who uses what
        expect(p.locator(".c-row", has_text="Password").locator(".c-count").first).to_have_text(re.compile(r"\d+"))
    finally:
        seeded.post("/settings", {"google_signin": False, "passkey_signin": True, "passkey_required_for_admins": False})
    expect(p.locator(".a-secure")).to_contain_text(f"Passkeys work on {BASE}")
    app.clean("sign-in methods")


def test_speaker_settings_save_and_validation(make_app, seeded, drained):
    before = seeded.get("/settings")
    app = make_app("owner", device="desktop", route="settings")
    p = app.page
    app.header("Speaker settings")
    save = p.locator(".c-save button.btn.primary")
    name = p.locator("#s-name")
    expect(name).to_have_value(before["speaker_name"])
    expect(save).to_be_disabled()
    # the unreachable speaker is reported after the status poll times out
    expect(p.locator("#s-name + p")).to_have_text("Can't reach the speaker right now.", timeout=30_000)
    try:
        name.fill("Lobby speaker")
        expect(save).to_be_enabled()
        expect(p.locator(".c-save .small")).to_be_visible()
        name.fill(before["speaker_name"])  # back to the saved value -> not dirty
        expect(save).to_be_disabled()
        name.fill("Lobby speaker")
        # sound: keep-volume switch shows/hides the slider; language segmented; resume switch
        keep = row_switch(p, "Leave the volume as it is")
        keep.uncheck()
        vol = p.locator(".s-vol input[type=range]")
        expect(vol).to_be_visible()
        vol.fill("60")
        expect(p.locator(".s-pct")).to_have_text("60%")
        p.get_by_role("radiogroup", name="Default announcement language").get_by_role("radio", name="日本語").click()
        row_switch(p, "Resume music after announcements").uncheck()
        save.click()
        app.toast("Speaker settings saved")
        app.soft(lambda: expect(save).to_be_disabled(), "Save turns disabled again after a successful save")
        s = seeded.get("/settings")
        assert (s["speaker_name"], s["default_volume"], s["tts_lang"], s["resume_after_say"]) == (
            "Lobby speaker", 0.6, "ja", False)
        p.reload()
        app.header()
        expect(p.locator("#s-name")).to_have_value("Lobby speaker")
        expect(p.locator(".s-pct")).to_have_text("60%")
        # client-side validation: cache and port (a valid port change would restart the server: never saved here)
        cache = p.locator(".c-row", has_text="YouTube tracks kept on disk").locator("input")
        cache.fill("0")
        save.click()
        expect(p.locator(".page > p.form-error").first).to_have_text("Keep at least 1 track.")
        cache.fill("20")
        port = p.locator(".c-row", has=p.locator(".c-title", has_text=re.compile("^Port$"))).locator("input")
        port.fill("80")
        save.click()
        expect(p.locator(".page > p.form-error").first).to_have_text("The port must be a number from 1024 to 65535.")
        p.reload()
        app.header()
        # an empty speaker name should not be accepted
        p.locator("#s-name").fill("")
        p.locator(".c-save button.btn.primary").click()
        app.page.wait_for_timeout(1500)
        app.soft(lambda: expect(p.locator(".page > p.form-error").first).not_to_have_text(""),
                 "empty speaker name is refused with a message")
        app.soft(lambda: _assert(seeded.get("/settings")["speaker_name"] != ""),
                 "server keeps a non-empty speaker name")
        p.reload()
        app.header()
        # an IP address that isn't one should not be accepted either
        p.locator("#s-ip").fill("not an address")
        p.locator(".c-save button.btn.primary").click()
        app.page.wait_for_timeout(1500)
        app.soft(lambda: _assert(seeded.get("/settings")["speaker_ip"] != "not an address"),
                 "server refuses a speaker_ip that is not an address")
    finally:
        seeded.post("/settings", {k: before[k] for k in (
            "speaker_name", "speaker_ip", "default_volume", "tts_lang", "resume_after_say", "cache_keep")})
    app.clean("speaker settings")


def _assert(cond):
    assert cond


def test_speaker_settings_lan_scan_mocked(make_app, seeded):
    """Find speakers (LAN discovery mocked so the real network is never scanned): Use fills the fields."""
    app = make_app("owner", device="phone", route="settings")
    p = app.page
    found = [{"name": "Lab speaker", "ip": "192.0.2.20", "model": "Test model"}]
    p.route("**/speakers", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(found)))
    p.get_by_role("button", name="Find speakers on the LAN").click()
    expect(p.locator(".s-found")).to_contain_text("Found 1 speaker. Pick the one to use.")
    use = p.locator(".s-dev button", has_text="Use")
    app.soft(lambda: expect(use).to_have_accessible_name(re.compile("Use")),
             "LAN scan Use button accessible name (settingRow aria-labelledby replaces it with the speaker name)")
    use.click()
    expect(p.locator("#s-ip")).to_have_value("192.0.2.20")
    expect(p.locator("#s-name")).to_have_value("Lab speaker")
    expect(p.locator(".s-found")).to_contain_text("Connects to 192.0.2.20 when you save.")
    expect(p.locator("button.c-phone-only", has_text="Save")).to_be_enabled()
    # none found / failure
    p.unroute("**/speakers")
    p.route("**/speakers", lambda r: r.fulfill(status=200, content_type="application/json", body="[]"))
    p.get_by_role("button", name="Look again").click()
    expect(p.locator(".s-found")).to_contain_text("No speakers answered.")
    p.unroute("**/speakers")
    p.route("**/speakers", lambda r: r.abort())
    p.get_by_role("button", name="Look again").click()
    expect(p.locator(".s-found .form-error")).to_have_text(re.compile("^Can't reach the server"))
    app.clean("lan scan")
    # nothing saved
    assert seeded.get("/settings")["speaker_ip"] == "192.0.2.10"
