"""Talkie: on "This device" the Announce page is a walkie-talkie between members. Operators can switch back to the
speaker's Announce page, viewers only get the Talkie; two members, one holds to talk with Chrome's fake mic, the
other hears it live and then plays it back from Recent."""
import re

import pytest
from playwright.sync_api import expect


def on_this_device(app, route="announce"):
    """Make "This device" the output (per browser) and open the route."""
    p = app.page
    p.evaluate("localStorage.setItem('spk.output', 'device')")
    p.goto(f"{p.url.split('#')[0]}#/{route}")
    p.reload()  # the output is read when the app loads
    app.header()
    return p


def test_operator_switches_between_talkie_and_speaker(make_app, seeded):
    app = make_app("operator", device="desktop", route="now")
    p = on_this_device(app)
    app.header("Talkie")
    expect(p.locator(".sb [data-route='announce']")).to_have_text("Talkie")
    assert p.title().startswith("Talkie")
    mode = p.get_by_role("radiogroup", name="Talk to")
    expect(mode.get_by_role("radio", name="Talkie")).to_have_attribute("aria-checked", "true")
    expect(p.get_by_role("button", name="Talk to everyone. Hold to talk")).to_be_visible()
    expect(p.locator(".tw-help")).to_have_text(
        "Everyone with the app open hears you live; others can play it back for 24 h.")
    expect(p.locator(".tw-count")).to_have_text(re.compile(r"\d+ online"))
    mode.get_by_role("radio", name="Speaker").click()
    app.header("Announce")
    expect(p.locator("form.ann-card")).to_be_visible()
    expect(p.locator(".out-note")).to_be_visible()  # announcements still go to the speaker
    p.get_by_role("radiogroup", name="Talk to").get_by_role("radio", name="Talkie").click()
    app.header("Talkie")
    # back on the speaker output the page is Announce again
    p.evaluate("localStorage.setItem('spk.output', 'speaker')")
    p.reload()
    app.header("Announce")
    expect(p.locator(".sb [data-route='announce']")).to_have_text("Announce")
    expect(p.get_by_role("radiogroup", name="Talk to")).to_have_count(0)
    app.clean("talkie operator")


def test_viewer_gets_only_talkie(make_app, seeded):
    app = make_app("viewer", device="phone", lang="th", route="now")
    p = on_this_device(app)
    app.header("ทอล์คกี้")
    expect(p.locator(".tabbar [data-route='announce']")).to_have_text("ทอล์คกี้")
    expect(p.get_by_role("radiogroup", name="พูดกับ")).to_have_count(0)
    expect(p.locator(".tw-label")).to_have_text("กดค้างเพื่อพูด")
    app.clean("talkie viewer")


def test_two_members_talk_live_and_play_back(make_app, seeded):
    if not seeded.get("/talk/status")["available"]:
        pytest.skip("ffmpeg not on the server's PATH: nothing to record with")
    listener = make_app("viewer", device="desktop", route="now")
    lp = on_this_device(listener)
    live_requests = []
    lp.on("request", lambda r: live_requests.append(r.url) if "/talkie/live/" in r.url else None)
    talker = make_app("operator", device="desktop", route="now")
    tp = on_this_device(talker)
    expect(tp.locator(".tw-count")).to_have_text("2 online")
    expect(lp.locator(".tw-count")).to_have_text("2 online")
    expect(lp.locator(".tw-faces .avatar")).to_have_count(2)

    ptt = tp.get_by_role("button", name="Talk to everyone. Hold to talk")
    expect(ptt).to_be_enabled()
    ptt.hover()
    tp.mouse.down()
    card = tp.locator(".tw-card")
    expect(card).to_have_attribute("data-state", "live", timeout=10_000)
    expect(tp.locator(".tw-label")).to_have_text("Release to send")
    expect(tp.locator(".tw-status")).to_have_text(re.compile(r"● You are live 0:0\d"))
    banner = lp.locator(".tw-live")
    expect(banner).to_contain_text("Oscar Operator is talking…")
    expect(lp.locator(".tw-label")).to_have_text("Wait until they finish")
    expect(lp.locator(".tw-ptt")).to_be_disabled()
    tp.wait_for_timeout(2500)  # talk for a bit (the fake mic beeps)
    tp.mouse.up()
    talker.toast("Sent. Everyone can play it back for 24 hours.")
    expect(card).to_have_attribute("data-state", "idle")
    expect(banner).to_be_hidden()
    assert live_requests, "the listener never fetched the live stream"

    mine = tp.locator(".tw-row").first
    expect(mine.locator("strong")).to_have_text("You")
    expect(mine.locator(".c-badge")).to_have_count(0)
    row = lp.locator(".tw-row").first
    expect(row.locator("strong")).to_have_text("Oscar Operator")
    expect(row.locator(".tw-len")).to_have_text(re.compile(r"0:0[1-4]"))
    # heard live in this browser (autoplay is allowed here), so it already counts as played
    expect(row.locator(".c-badge")).to_have_count(0)

    # a member who wasn't listening: "Not played yet" until they play it
    late = make_app("owner", device="android", route="now")
    ap = on_this_device(late)
    row = ap.locator(".tw-row").first
    expect(row.locator(".c-badge")).to_have_text("Not played yet")
    play = row.get_by_role("button", name="Play the message from Oscar Operator")
    with ap.expect_response(re.compile(r"/talkie/clips/[\w-]+\.mp3")) as got:
        play.click()
    assert got.value.status in (200, 206)
    expect(row.locator(".c-badge")).to_have_count(0)
    expect(row.locator(".tw-play[aria-pressed='true']")).to_have_count(1)  # one clip at a time, and this is it
    for a in (listener, talker, late):
        a.clean("talkie live")
