"""Owner reset: unlink a member's Google account and remove a lost phone's passkey from Members (desktop pane and
phone sheet); the member is signed out of every device. The Google link and passkeys are written straight into the
test database (no Google or authenticator here)."""
import sqlite3
from datetime import UTC, datetime

import httpx
from playwright.sync_api import expect

from .e2ekit import BASE, pw

RITA = {"username": "rita", "display_name": "Rita Reset", "password": pw("rita-pass-123"), "role": "operator"}


def seed(api, workdir):
    """Rita with Google linked and two passkeys, plus a signed-in session of hers."""
    u = api.ensure_user(RITA)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with sqlite3.connect(workdir / "data.db") as db:
        db.execute("UPDATE users SET google_sub = 'e2e-rita', google_email = 'rita@example.com' WHERE id = ?",
                   (u["id"],))
        db.execute("DELETE FROM passkeys WHERE user_id = ?", (u["id"],))
        for n, name in enumerate(("iPhone", "MacBook")):
            db.execute(
                "INSERT INTO passkeys (user_id, credential_id, public_key, user_handle, name, created_at, last_used_at)"
                " VALUES (?, ?, x'00', 'e2e-rita', ?, ?, ?)",
                (u["id"], f"e2e-rita-{n}", name, now, now if n == 0 else None))
    c = httpx.Client(base_url=BASE, headers={"X-Requested-With": "speaker-web"})
    c.post("/auth/login", json={"username": RITA["username"], "password": RITA["password"]}).raise_for_status()
    return c


def signed_in(c):
    return c.get("/auth/state").json()["user"] is not None


def test_owner_reset_desktop(make_app, seeded, workdir):
    rita = seed(seeded, workdir)
    assert signed_in(rita)
    app = make_app("owner", device="desktop", route="members")
    p = app.page
    p.locator(".m-row", has_text="Rita Reset").click()
    sec = p.locator(".m-sec", has_text="Sign-in")
    expect(sec.locator("li", has_text="Passkey iPhone · last used today")).to_be_visible()
    expect(sec.locator("li", has_text="Passkey MacBook · not used yet")).to_be_visible()
    expect(sec).to_contain_text("Remove one here if a phone is lost")

    # Unlink Google: confirm, Keep backs out, then Unlink for real
    g = sec.locator("li", has_text="Google · rita@example.com")
    g.get_by_role("button", name="Unlink").click()
    confirm = sec.locator(".c-confirm")
    expect(confirm).to_contain_text("Unlink Google from Rita Reset?")
    expect(confirm.get_by_role("button", name="Keep")).to_be_focused()
    confirm.get_by_role("button", name="Keep").click()
    expect(confirm).to_have_count(0)
    g.get_by_role("button", name="Unlink").click()
    sec.locator(".c-confirm").get_by_role("button", name="Unlink").click()
    expect(p.locator(".toast")).to_contain_text("Unlinked Google from Rita Reset and signed them out of every device.")
    expect(sec.locator("li", has_text="rita@example.com")).to_have_count(0)
    assert not signed_in(rita)
    assert seeded.user("rita")["google_email"] is None

    # Remove the lost iPhone's passkey; the MacBook one stays
    sec.locator("li", has_text="Passkey iPhone").get_by_role("button", name="Remove").click()
    expect(sec.locator(".c-confirm")).to_contain_text("Remove the iPhone passkey from Rita Reset?")
    sec.locator(".c-confirm").get_by_role("button", name="Remove").click()
    expect(p.locator(".toast").last).to_contain_text("Removed Rita Reset’s iPhone passkey")
    expect(sec.locator("li", has_text="Passkey iPhone")).to_have_count(0)
    expect(sec.locator("li", has_text="Passkey MacBook")).to_be_visible()
    acts = [(a["action"], a["detail"]) for a in seeded.get("/activity")[:2]]
    assert acts == [("member update", "rita: removed passkey iPhone"),
                    ("member update", "rita: unlinked Google rita@example.com")]

    # your own row stays read-only (Account changes those)
    p.locator(".m-row", has_text="Olivia Owner").click()
    expect(p.locator(".m-sec", has_text="Sign-in").get_by_role("button", name="Unlink")).to_have_count(0)
    app.clean("owner reset desktop")


def test_owner_reset_phone_thai(make_app, seeded, workdir):
    seed(seeded, workdir)
    app = make_app("owner", device="phone", lang="th", route="members")
    p = app.page
    p.locator(".m-row", has_text="Rita Reset").click()
    sheet = app.sheet()
    sec = sheet.locator(".m-sec", has_text="การเข้าสู่ระบบ")
    sec.locator("li", has_text="พาสคีย์ MacBook").get_by_role("button", name="ลบ").click()
    expect(sec.locator(".c-confirm")).to_contain_text("ลบพาสคีย์ MacBook ของ Rita Reset?")
    expect(sec.locator(".c-confirm").get_by_role("button", name="เก็บไว้")).to_be_visible()
    sec.locator(".c-confirm").get_by_role("button", name="ลบ").click()
    expect(p.locator(".toast")).to_contain_text("ลบพาสคีย์ MacBook ของ Rita Reset แล้ว")
    g = sec.locator("li", has_text="Google · rita@example.com")
    expect(g.get_by_role("button", name="ยกเลิกการเชื่อม")).to_be_visible()
    app.clean("owner reset phone")
