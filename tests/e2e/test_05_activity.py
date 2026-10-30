"""Activity (owner): filters on phone/iPad (segmented) and desktop (side list), paging with Show older."""
import httpx
from playwright.sync_api import expect

from .e2ekit import BASE, pw


def seed(api, n=60):
    u = api.ensure_user({"username": "actseed", "display_name": "Act Seed", "password": pw("actseed-pass-1"),
                         "role": "viewer"})
    for i in range(n):
        api.patch(f"/users/{u['id']}", {"display_name": f"Act Seed {i}"})
    # a failed sign-in, so the Failed filter has something
    httpx.post(f"{BASE}/auth/login", headers={"X-Requested-With": "speaker-web"},
               json={"username": "actseed", "password": pw("wrong-password")})


def test_activity_paging_and_filters_desktop(make_app, seeded):
    seed(seeded)
    app = make_app("owner", device="desktop", route="activity")
    total = len(seeded.get("/activity?limit=500"))
    p = app.page
    app.header("Activity")
    rows = p.locator(".a-row")
    expect(rows).to_have_count(50)
    expect(p.locator(".a-row").first).to_contain_text("Olivia Owner: Signed in")  # newest first
    more = p.get_by_role("button", name="Show older")
    more.click()
    expect(rows).to_have_count(min(total, 100))
    while more.is_visible():
        more.click()
        p.wait_for_timeout(400)
    expect(rows).to_have_count(total)
    expect(p.locator(".a-end")).to_have_text("That's everything. Older entries aren't kept.")
    # desktop filter list on the left
    side = p.locator(".a-side")
    side.get_by_role("radio", name="Failed").click()
    expect(side.get_by_role("radio", name="Failed")).to_have_attribute("aria-checked", "true")
    expect(p.locator(".a-row:not(.fail)")).to_have_count(0)
    expect(p.locator(".a-row.fail").first).to_contain_text("System: Sign-in failed")
    side.get_by_role("radio", name="Account").click()
    expect(p.locator(".a-row", has_text="Changed a member").first).to_be_visible()
    expect(p.locator(".a-row", has_text="Sign-in failed")).to_have_count(0)
    side.get_by_role("radio", name="Playback").click()
    shown = p.locator(".a-row").count()
    if shown == 0:
        expect(p.locator(".a-feed .c-empty")).to_have_text("Nothing like this in the entries shown.")
    side.get_by_role("radio", name="All").click()
    expect(rows).to_have_count(total)
    app.clean("activity desktop")


def test_activity_phone_segmented_th(make_app, seeded):
    app = make_app("owner", device="phone", route="activity", lang="th", theme="dark")
    p = app.page
    app.header("ประวัติการใช้งาน")
    seg = p.locator(".a-seg")
    expect(seg).to_be_visible()
    seg.get_by_role("radio").nth(3).click()  # Failed
    expect(p.locator(".a-row:not(.fail)")).to_have_count(0)
    seg.get_by_role("radio").nth(0).click()
    expect(p.locator(".a-row").first).to_be_visible()
    # Thai detail for a sign-in ("from <ip>")
    expect(p.locator(".a-detail", has_text="จาก").first).to_be_visible()
    p.locator("a.phd-back").click()
    app.header("บัญชี")
    app.clean("activity phone th")
