"""About, Privacy and Licenses: open signed out from the sign-in page (no speaker name or owner contact there),
Account -> About on phone and desktop, the owner contact set in Speaker settings shown to members and hidden when
empty, Privacy's jump links, a Licenses row opening to its text, and the Thai strings."""
import re

from playwright.sync_api import expect

from .e2ekit import ROOT

VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "version.py").read_text())[1]
CONTACT = "it@example.com"


def heading(p, text):
    """The page title, with or without the shell (signed-out pages are screens)."""
    expect(p.locator("h1.pt").first).to_have_text(text, timeout=15_000)


def test_signed_out_from_sign_in(make_app, seeded, api):
    api.post("/settings", {"owner_contact": CONTACT})
    try:
        app = make_app(None, device="phone")
        p = app.page
        expect(p.locator("form.auth-form")).to_be_visible()
        foot = p.get_by_role("navigation", name="About this app")
        foot.get_by_role("link", name="About").click()
        heading(p, "About")
        expect(p.locator(".ab-ver")).to_contain_text(f"Version {VERSION}")
        expect(p.locator(".shell")).to_have_count(0)
        # no server details signed out: no speaker name, no owner contact, no "This server" card
        expect(p.locator(".pp-contact")).to_have_count(0)
        expect(p.get_by_text("This server", exact=True)).to_have_count(0)
        expect(p.get_by_text(CONTACT)).to_have_count(0)
        assert "server" not in app.ctx.request.get("/about").json()
        # links out of the app open in a new tab without a referrer
        new = p.get_by_role("link", name=re.compile("What’s new"))
        expect(new).to_have_attribute("href", re.compile(r"github\.com/.+/CHANGELOG\.md$"))
        expect(new).to_have_attribute("target", "_blank")
        expect(new).to_have_attribute("rel", "noopener noreferrer")
        app.no_hscroll("about signed out")
        # back to sign in, then Privacy from the footer
        p.locator("a.phd-back").click()
        expect(p.locator("form.auth-form")).to_be_visible()
        foot.get_by_role("link", name="Privacy").click()
        heading(p, "Privacy")
        expect(p.locator(".pv-table tbody tr")).to_have_count(4)
        expect(p.get_by_text("Entries are deleted after 90 days", exact=False)).to_be_visible()
        expect(p.get_by_text(CONTACT)).to_have_count(0)
        # a jump link scrolls in place; the router doesn't take it for a page
        p.locator(".pv-chip", has_text="Other companies").click()
        expect(p.locator("#pvh-third")).to_be_in_viewport()
        assert app.hash() == "#/privacy"
        heading(p, "Privacy")
        # Privacy -> About -> Licenses, still signed out
        p.locator("a.phd-back").click()
        heading(p, "About")
        p.get_by_role("link", name=re.compile("^Licenses")).click()
        heading(p, "Licenses")
        app.clean("signed out")
    finally:
        api.post("/settings", {"owner_contact": None})


def test_account_about_and_owner_contact(make_app, seeded, api):
    api.post("/settings", {"owner_contact": None})
    try:
        # phone owner: Account -> About (with the version); no contact yet, so the owner sees a hint
        app = make_app("owner", device="phone", route="account")
        p = app.page
        row = p.locator("a.c-link[href='#/about']")
        expect(row.locator(".c-val")).to_have_text(f"v{VERSION}")
        row.click()
        app.header("About")
        expect(p.get_by_text("This server", exact=True)).to_be_visible()
        expect(p.locator(".pp-contact")).to_have_count(0)
        hint = p.locator(".pp-owner")
        expect(hint).to_be_visible()
        # add the contact in Speaker settings
        hint.get_by_role("link", name="Add contact").click()
        app.header("Speaker settings")
        p.locator("#s-contact").fill(CONTACT)
        p.locator(".c-phone-only.btn.primary").click()
        app.toast("Speaker settings saved")
        assert api.get("/settings")["owner_contact"] == CONTACT
        app.go("about")
        expect(p.locator(".pp-contact a[href='mailto:it@example.com']")).to_be_visible()
        expect(p.locator(".pp-owner")).to_have_count(0)
        expect(p.locator("a.phd-back")).to_have_text("Account")
        app.clean("owner about")

        # desktop viewer: Account & app settings -> About this app; sees the contact, no owner hint, no back link
        v = make_app("viewer", device="desktop", route="prefs")
        q = v.page
        about = q.locator("a.c-link[href='#/about']")
        expect(about).to_contain_text(f"Version {VERSION}, privacy and licenses")
        about.click()
        v.header("About")
        expect(q.locator(".pp-contact")).to_contain_text(CONTACT)
        expect(q.locator(".pp-owner")).to_have_count(0)
        expect(q.locator("a.phd-back")).to_be_hidden()
        q.get_by_role("link", name=re.compile("^Privacy")).click()
        v.header("Privacy")
        expect(q.locator(".pv-meta a[href='mailto:it@example.com']")).to_be_visible()
        # emptied again: the row is gone
        api.post("/settings", {"owner_contact": ""})
        v.go("about")
        expect(q.locator(".pp-contact")).to_have_count(0)
        expect(q.locator(".pp-owner")).to_have_count(0)  # the hint is for owners only
        v.clean("viewer about")
    finally:
        api.post("/settings", {"owner_contact": None})


def test_licenses_rows_open_to_their_text(make_app, seeded):
    app = make_app("operator", device="desktop", route="licenses")
    p = app.page
    app.header("Licenses")
    expect(p.locator("a.phd-back")).to_have_text("About")
    # the three groups
    caps = p.locator(".c-cap").all_inner_texts()
    assert any(c.startswith("In your browser · 1") for c in caps), caps
    assert any(c.startswith("Runs on the server") for c in caps), caps
    assert any(c.startswith("Relay firmware · 5") for c in caps), caps
    # a package row opens to its license text, and closes again
    q = p.locator(".li-q", has=p.locator(".c-title", has_text=re.compile("^fastapi$")))
    expect(q).to_have_attribute("aria-expanded", "false")
    q.click()
    expect(q).to_have_attribute("aria-expanded", "true")
    panel = p.locator(f"#{q.get_attribute('aria-controls')}")
    expect(panel.locator(".li-text")).to_contain_text("Permission is hereby granted")
    expect(panel.locator("a.li-web")).to_have_attribute("href", "https://github.com/fastapi/fastapi")
    expect(panel.locator("a.li-web")).to_have_attribute("target", "_blank")
    q.click()
    expect(panel).to_be_hidden()
    # copyleft ones are marked; the font row shows its copyright and the OFL text shipped with the font
    font = p.locator(".li-q", has=p.locator(".c-title", has_text="Anuphan"))
    expect(font.locator(".c-badge.li-copy")).to_have_text("OFL-1.1")
    font.click()
    fp = p.locator(f"#{font.get_attribute('aria-controls')}")
    expect(fp.locator(".li-cr")).to_have_text("Copyright 2019 The Anuphan Project Authors")
    expect(fp.locator(".li-text")).to_contain_text("SIL OPEN FONT LICENSE")
    # this app's MIT license
    p.locator(".li-own summary").click()
    expect(p.locator(".li-own .li-text")).to_contain_text("Copyright (c) 2026 Jackson Tae")
    # the notices
    expect(p.locator(".li-n")).to_have_count(3)
    app.clean("licenses")


def test_thai(make_app, seeded):
    out = make_app(None, device="phone", lang="th")
    p = out.page
    foot = p.locator("nav.auth-foot")
    expect(foot).to_have_text(re.compile("ความเป็นส่วนตัว\\s*·\\s*เกี่ยวกับแอป"))
    foot.get_by_role("link", name="เกี่ยวกับแอป").click()
    heading(p, "เกี่ยวกับแอป")
    expect(p.locator("a.phd-back")).to_have_text("เข้าสู่ระบบ")
    expect(p.locator(".ab-ver")).to_contain_text(f"เวอร์ชัน {VERSION}")
    out.clean("signed out th")

    app = make_app("viewer", device="phone", lang="th", theme="dark", route="privacy")
    q = app.page
    app.header("ความเป็นส่วนตัว")
    expect(q.locator(".pv-table thead th")).to_have_text(["ข้อมูล", "ผู้ชม", "ผู้ควบคุม", "เจ้าของ"])
    expect(q.get_by_text("ข้อความเสียงเก็บ 24 ชั่วโมง", exact=False)).to_be_visible()
    app.go("licenses")
    app.header("สัญญาอนุญาต")
    expect(q.locator(".li-own .c-sub")).to_have_text("สัญญาอนุญาต MIT")
    app.go("account")
    expect(q.locator("a.c-link[href='#/about'] .c-title")).to_have_text("เกี่ยวกับแอป")
    app.clean("th")
