"""Help: search (EN + TH keywords), no-match state, Escape/clear, deep links + aliases, Try it per role."""
import re

from playwright.sync_api import expect


def test_help_search_and_deep_links(make_app, seeded):
    app = make_app("operator", device="desktop", route="help")
    p = app.page
    app.header("Help")
    expect(p.locator("#hq-start")).to_have_attribute("aria-expanded", "true")  # first topic open by default
    box = p.get_by_label("Search help")
    box.fill("passkey")
    expect(p.locator("[role=status].sr-only")).to_have_text(re.compile(r"\d+ topics? found"))
    expect(p.locator("#topic-passkey")).to_be_visible()
    box.fill("zzzz-nothing")
    expect(p.locator(".hp-none-t")).to_have_text("No topics match “zzzz-nothing”")
    p.get_by_role("button", name="Show all topics").click()
    expect(box).to_have_value("")
    expect(p.locator(".hp-topic").first).to_be_visible()
    box.fill("offline")
    p.get_by_role("button", name="Clear search").click()
    expect(box).to_have_value("")
    box.fill("ไมค์")  # Thai keyword finds the English topic
    expect(p.locator("#topic-talk")).to_be_visible()
    box.press("Escape")
    expect(box).to_have_value("")
    # toggling a topic updates the hash
    p.locator("#hq-schedule").click()
    expect(p.locator("#hp-schedule")).to_be_visible()
    assert app.hash() == "#/help/schedule"
    p.locator("#hq-schedule").click()
    expect(p.locator("#hp-schedule")).to_be_hidden()
    # deep links and aliases open, scroll to and focus the topic
    for link, topic in (("help/passkey", "passkey"), ("help/pk", "passkey"), ("help/talk", "talk"),
                        ("help/offline", "offline")):
        app.go(link)
        expect(p.locator(f"#hq-{topic}")).to_have_attribute("aria-expanded", "true")
        expect(p.locator(f"#hq-{topic}")).to_be_focused()
        expect(p.locator(f"#topic-{topic}")).to_be_in_viewport()
    # Try it goes to the page
    app.go("help/playlists")
    p.locator("#hp-playlists").get_by_role("link", name="Try it in Playlists").click()
    app.header("Playlists")
    app.clean("help")


def test_help_try_it_per_role_th(make_app, seeded):
    app = make_app("viewer", device="phone", route="help/music", lang="th", theme="dark")
    p = app.page
    app.header("คู่มือการใช้งาน")
    expect(p.locator("#hq-music")).to_have_attribute("aria-expanded", "true")
    # viewers can't open Music, so no Try it; Playlists they can
    expect(p.locator("#hp-music .hp-try")).to_have_count(0)
    p.locator("#hq-members").click()
    expect(p.locator("#hp-members .hp-try")).to_have_count(0)
    p.locator("#hq-playlists").click()
    expect(p.locator("#hp-playlists .hp-try")).to_have_count(1)
    p.get_by_label("ค้นหาในคู่มือ").fill("รหัสผ่าน")
    expect(p.locator(".hp-topic").first).to_be_visible()
    p.locator("a.phd-back").click()
    app.header("บัญชี")
    app.clean("help viewer th")
