"""First-account setup, sign in (errors, lockout, offer) and passkeys through a CDP virtual authenticator."""
import re

import httpx
import pytest
from playwright.sync_api import expect

from .e2ekit import API_TOKEN, BASE, OPERATOR, OWNER, pw, wait_for


def test_first_account_setup(make_app, server, api):
    if httpx.get(f"{BASE}/auth/state").json()["needs_setup"] is False:
        pytest.skip("server already has an owner (rerun against a fresh E2E_DIR)")
    app = make_app(role=None, device="phone", go=False)
    p = app.page
    app.go("", wait_header=False)
    expect(p.locator(".setup h1")).to_have_text("First-time setup")
    # empty submit: every field explains itself
    p.get_by_role("button", name="Create owner account").click()
    expect(p.locator(".setup-err")).to_have_text("Fix the fields in red, then try again.")
    expect(p.get_by_label("API token", exact=True)).to_have_attribute("aria-invalid", "true")
    # "Sign in" while nobody exists yet says so
    p.get_by_role("button", name="Sign in").click()
    expect(p.locator(".setup-err")).to_contain_text("no account on this speaker yet")
    # bad username / short password are flagged client-side
    p.get_by_label("API token", exact=True).fill("wrong-token")
    p.get_by_label("Display name").fill(OWNER["display_name"])
    p.get_by_label("Username").fill("A B")
    p.get_by_label("Password", exact=True).fill("short")
    expect(p.get_by_label("Username")).to_have_value("a b")  # lower-cased as you type
    p.get_by_role("button", name="Create owner account").click()
    expect(p.get_by_label("Username")).to_have_attribute("aria-invalid", "true")
    expect(p.get_by_label("Password", exact=True)).to_have_attribute("aria-invalid", "true")
    # language switch keeps the typed values (module-level draft)
    p.locator(".lang-toggle button[lang=th]").click()
    expect(p.locator(".setup h1")).to_have_text("ตั้งค่าครั้งแรก")
    expect(p.locator("html")).to_have_attribute("lang", "th")
    p.locator(".lang-toggle button[lang=en]").click()
    expect(p.get_by_label("Display name")).to_have_value(OWNER["display_name"])
    # wrong token: the server refuses with a plain message
    p.get_by_label("Username").fill(OWNER["username"])
    p.get_by_label("Password", exact=True).fill(OWNER["password"])
    p.get_by_role("button", name="Create owner account").click()
    expect(p.locator(".setup-err")).to_contain_text("That API token is wrong")
    p.get_by_label("API token", exact=True).fill(API_TOKEN)
    p.get_by_role("button", name="Create owner account").click()
    expect(p.locator(".shell")).to_be_attached(timeout=15_000)
    app.header("Now playing")
    assert httpx.get(f"{BASE}/auth/state").json()["needs_setup"] is False
    assert api.user("owner")["role"] == "admin"
    app.clean("after setup")


def test_login_errors_and_forgot(make_app, seeded):
    app = make_app(role=None, device="desktop")
    p = app.page
    expect(p.locator(".auth-form h1")).to_have_text("Sign in")
    p.locator("form.auth-form button[type=submit]").click()
    expect(p.locator(".auth-form .form-error")).to_have_text("Enter your username and password first.")
    p.locator("input[name=username]").fill(OWNER["username"])
    p.locator("input[name=password]").fill("not-the-password")
    p.locator("form.auth-form button[type=submit]").click()
    expect(p.locator(".auth-form .form-error")).to_have_text("Wrong username or password.")
    expect(p.locator("input[name=password]")).to_have_attribute("aria-invalid", "true")
    # Forgot password reveals the help text
    forgot = p.get_by_role("button", name="Forgot password")
    forgot.click()
    expect(p.locator("#forgot-help")).to_be_visible()
    expect(forgot).to_have_attribute("aria-expanded", "true")
    # passkey button is offered on localhost (secure context) because the server has passkeys on
    expect(p.get_by_role("button", name="Sign in with a passkey")).to_be_visible()
    expect(p.get_by_role("button", name="Continue with Google")).to_have_count(0)  # Google is off
    # correct password signs in
    p.locator("input[name=password]").fill(OWNER["password"])
    p.locator("form.auth-form button[type=submit]").click()
    expect(p.locator(".shell")).to_be_attached(timeout=15_000)
    app.clean("login page")


def test_login_lockout_real(make_app, seeded):
    """Five wrong tries for one name lock that name out (429); the button stays disabled with a countdown."""
    app = make_app(role=None, device="phone")
    p = app.page
    p.locator("input[name=username]").fill("lockout-probe")
    for _ in range(5):
        p.locator("input[name=password]").fill(pw("wrong-password"))
        p.locator("form.auth-form button[type=submit]").click()
        expect(p.locator(".auth-form .form-error")).to_have_text("Wrong username or password.")
        p.wait_for_timeout(150)
    p.locator("input[name=password]").fill(pw("wrong-password"))
    p.locator("form.auth-form button[type=submit]").click()
    err = p.locator(".auth-form .form-error")
    expect(err).to_contain_text("Too many wrong tries. You can try again in 5 minutes.")
    expect(p.locator("form.auth-form button[type=submit]")).to_be_disabled()
    app.clean("lockout")


def test_login_lockout_countdown(make_app, seeded):
    """Countdown ticks down and the form unlocks by itself (server answer mocked to Retry-After: 3)."""
    app = make_app(role=None, device="desktop")
    p = app.page
    body = '{"detail":"Too many attempts"}'
    p.route("**/auth/login", lambda r: r.fulfill(status=429, headers={"Retry-After": "3"},
                                                 content_type="application/json", body=body))
    p.locator("input[name=username]").fill(OWNER["username"])
    p.locator("input[name=password]").fill("whatever-123")
    p.locator("form.auth-form button[type=submit]").click()
    err = p.locator(".auth-form .form-error")
    expect(err).to_have_text("Too many wrong tries. You can try again in 3 seconds.")
    btn = p.locator("form.auth-form button[type=submit]")
    expect(btn).to_be_disabled()
    expect(err).to_have_text("Too many wrong tries. You can try again in 1 second.", timeout=4000)
    expect(btn).to_be_enabled(timeout=4000)
    expect(err).to_have_text("")
    p.unroute("**/auth/login")
    app.login_ui(OWNER)
    app.clean("lockout countdown")


def test_disabled_account(make_app, seeded):
    u = seeded.ensure_user({"username": "dora", "display_name": "Dora Disabled", "password": pw("dora-pass-123"),
                            "role": "viewer"})
    seeded.patch(f"/users/{u['id']}", {"disabled": True})
    app = make_app(role=None, device="desktop")
    p = app.page
    p.locator("input[name=username]").fill("dora")
    p.locator("input[name=password]").fill(pw("dora-pass-123"))
    p.locator("form.auth-form button[type=submit]").click()
    expect(p.locator(".auth-form .form-error")).to_have_text(
        "This account is turned off. Ask the owner to turn it back on.")
    app.clean("disabled login")


def test_passkey_offer_not_now_and_never(make_app, seeded):
    seeded.ensure_user({"username": "otto", "display_name": "Otto Offer", "password": pw("otto-pass-123"),
                        "role": "operator"})
    spec = {"username": "otto", "password": pw("otto-pass-123")}
    app = make_app(role=None, device="phone", offer=True)
    p = app.page
    app.login_ui(spec)
    sheet = app.sheet()
    expect(sheet.locator(".pko-h")).to_have_text("Sign in faster next time")
    sheet.get_by_role("button", name="Not now").click()
    expect(p.locator("dialog.ov[open]")).to_have_count(0)
    # sign out from the phone Account page, sign in again: asked again, then "Don't ask again"
    app.go("account")
    p.locator("button.c-row.danger", has_text="Sign out").click()
    app.toast("Signed out")
    expect(p.locator("input[name=username]")).to_be_visible()
    app.login_ui(spec)
    sheet = app.sheet()
    sheet.get_by_role("button", name="Don't ask again").click()
    assert p.evaluate("localStorage.getItem('spk.pkOffer')") == "never"
    app.go("account")
    p.locator("button.c-row.danger", has_text="Sign out").click()
    expect(p.locator("input[name=username]")).to_be_visible()
    app.login_ui(spec)
    p.wait_for_timeout(1500)
    expect(p.locator("dialog.ov[open]")).to_have_count(0)
    app.clean("offer")


def _authenticator(app):
    cdp = app.ctx.new_cdp_session(app.page)
    cdp.send("WebAuthn.enable", {"enableUI": False})
    auth = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
        "isUserVerified": True, "automaticPresenceSimulation": True,
    }})
    return cdp, auth["authenticatorId"]


def test_passkey_offer_add_rename_signin_remove(make_app, seeded):
    """Passkey life cycle on the owner account: offer -> create, duplicate refused, rename, passkey sign-in, remove."""
    app = make_app(role=None, device="desktop", offer=True)
    p = app.page
    cdp, aid = _authenticator(app)
    for k in seeded.get("/users"):
        assert not (k["username"] == "owner" and k["has_passkey"]), "owner already has a passkey; use a fresh E2E_DIR"
    app.login_ui(OWNER)
    sheet = app.sheet()
    sheet.get_by_role("button", name="Create passkey").click()
    app.toast("Passkey added")
    expect(p.locator("dialog.ov[open]")).to_have_count(0)
    assert seeded.user("owner")["has_passkey"] is True
    # Account & app settings lists it; adding a second one on the same authenticator is refused (excludeCredentials)
    app.go("prefs")
    rows = p.locator(".ca-pks .c-row")
    expect(rows).to_have_count(1)
    name = rows.first.locator(".c-title").inner_text()
    assert name, "passkey row has no name"
    app.soft(lambda: expect(rows.first.locator("button.btn")).to_have_accessible_name(re.compile("Edit passkey")),
             "passkey Edit button accessible name (aria-labelledby from settingRow overrides its aria-label)")
    p.locator("button.ca-add").click()
    expect(p.locator(".ca-pad.form-error")).to_have_text("This device already has a passkey for your account.")
    # rename (empty name refused)
    rows.first.locator("button.btn", has_text="Edit").click()
    sheet = app.sheet()
    sheet.locator("input").fill("  ")
    sheet.get_by_role("button", name="Save").click()
    expect(sheet.locator(".form-error").first).to_have_text("Give the passkey a name first")
    sheet.locator("input").fill("E2E laptop key")
    sheet.get_by_role("button", name="Save").click()
    app.toast("Passkey renamed")
    expect(p.locator(".ca-pks .c-title")).to_have_text("E2E laptop key")
    # members list shows the passkey mark
    app.go("members")
    expect(p.locator(".m-row", has_text="Olivia Owner").locator(".m-pk")).to_have_count(1)
    # sign out and back in with the passkey
    p.locator("button.uchip").click()
    p.locator(".popover .mi.danger", has_text="Sign out").click()
    expect(p.locator("input[name=username]")).to_be_visible()
    p.get_by_role("button", name="Sign in with a passkey").click()
    expect(p.locator(".shell")).to_be_attached(timeout=15_000)
    app.header("Now playing")
    acts = seeded.get("/activity?limit=5")
    assert any(a["action"] == "login ok" and "passkey" in (a["detail"] or "") for a in acts), acts
    # remove it again (confirm step first, Cancel keeps it)
    app.go("prefs")
    p.locator(".ca-pks .c-row").first.locator("button.btn", has_text="Edit").click()
    sheet = app.sheet()
    sheet.get_by_role("button", name="Remove passkey").click()
    expect(sheet.locator(".c-confirm")).to_be_visible()
    sheet.locator(".c-confirm").get_by_role("button", name="Cancel").click()
    expect(sheet.locator(".c-confirm")).to_be_hidden()
    sheet.get_by_role("button", name="Remove passkey").click()
    sheet.locator(".c-confirm").get_by_role("button", name="Remove").click()
    app.toast("Passkey removed")
    expect(p.locator(".ca-pks")).to_contain_text("No passkeys yet")
    assert seeded.user("owner")["has_passkey"] is False
    cdp.send("WebAuthn.removeVirtualAuthenticator", {"authenticatorId": aid})
    app.clean("passkeys")


def test_passkey_signin_unknown_credential(make_app, seeded):
    """A passkey the server doesn't know: plain error, no crash."""
    app = make_app(role=None, device="phone")
    p = app.page
    cdp, aid = _authenticator(app)
    # register a credential the server never saw, straight on the authenticator
    import base64
    import os

    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
    key = ec.generate_private_key(ec.SECP256R1())
    pkcs8 = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption())
    cdp.send("WebAuthn.addCredential", {"authenticatorId": aid, "credential": {
        "credentialId": base64.b64encode(os.urandom(16)).decode(), "isResidentCredential": True, "rpId": "localhost",
        "privateKey": base64.b64encode(pkcs8).decode(), "userHandle": base64.b64encode(b"stranger").decode(),
        "signCount": 0,
    }})
    p.get_by_role("button", name="Sign in with a passkey").click()
    expect(p.locator(".auth-form .form-error")).to_have_text(re.compile("That passkey didn.t work here"),
                                                             timeout=15_000)
    app.clean("unknown passkey")


def test_operator_cannot_reach_setup_again(seeded):
    r = httpx.post(f"{BASE}/auth/setup", headers={"X-Requested-With": "speaker-web"},
                   json={"api_token": API_TOKEN, "username": "x2", "display_name": "x", "password": pw("x-pass-123")})
    assert r.status_code == 409
    assert OPERATOR["username"] in [u["username"] for u in seeded.get("/users")]


def test_session_end_signs_out(make_app, seeded):
    """A 401 on any call (session revoked elsewhere) returns to the sign-in screen with a message."""
    app = make_app("operator", device="desktop")
    p = app.page
    app.ctx.clear_cookies()
    app.go("playlists", wait_header=False)
    p.evaluate("location.hash = '#/announce'")
    wait_for(lambda: p.locator("input[name=username]").is_visible(), timeout=20, what="sign-in screen after 401")
    app.toast("You were signed out")
    app.clean("401")
