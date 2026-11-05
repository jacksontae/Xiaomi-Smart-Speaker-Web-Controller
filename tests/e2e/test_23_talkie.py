"""Talkie: on "This device" the Announce page is a walkie-talkie between members, for every role (nothing goes to the
speaker from there, so there is no speaker side to switch to). Two tabs: Walkie (live to the members who have it
open, as cards) and Voice messages (kept a day, delete with Undo). Chrome's fake mic does the talking; other pages
show a "join the Walkie" chip and the nav counts the messages not played yet."""
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


def needs_ffmpeg(seeded):
    if not seeded.get("/talk/status")["available"]:
        pytest.skip("ffmpeg not on the server's PATH: nothing to record with")


def hold(app, button, state_of, ms):
    """Hold `button` with the mouse until `state_of` (the card or bar) is live, for `ms`; returns still holding."""
    p = app.page
    button.hover()
    p.mouse.down()
    expect(state_of).to_have_attribute("data-state", "live", timeout=10_000)
    p.wait_for_timeout(ms)  # talk for a bit (the fake mic beeps)


def test_operator_gets_only_talkie(make_app, seeded):
    app = make_app("operator", device="desktop", route="now")
    p = on_this_device(app)
    app.header("Talkie")
    expect(p.locator(".sb [data-route='announce']")).to_have_text(re.compile(r"^Talkie"))
    assert p.title().startswith("Talkie")
    expect(p.locator("form.ann-card")).to_have_count(0)  # no speaker side
    tabs = p.get_by_role("radiogroup", name="Talkie mode")
    expect(tabs.get_by_role("radio")).to_have_count(2)
    expect(tabs.get_by_role("radio", name="Walkie")).to_have_attribute("aria-checked", "true")
    expect(p.get_by_role("button", name="Talk to everyone. Hold to talk")).to_be_visible()
    expect(p.locator(".tw-help")).to_have_text(
        "Plays live to everyone in the room, one person at a time. Heard once, not kept.")
    expect(p.locator(".tw-room .tw-cap")).to_have_text("In the room · 1")
    me = p.locator(".tw-pc.me")
    expect(me).to_have_attribute("aria-label", "You: Listening")
    expect(p.locator(".tw-hint")).to_be_hidden()  # never on the Talkie page

    tabs.get_by_role("radio", name=re.compile("Voice messages")).click()
    assert app.hash() == "#/announce/messages"
    expect(p.locator(".tw-card")).to_be_hidden()
    expect(p.locator(".tw-room")).to_be_hidden()
    expect(p.get_by_role("button", name="Hold to record a message")).to_be_visible()
    expect(p.locator(".tw-recent .tw-cap")).to_have_text("Last 24 hours")
    p.reload()  # the tab is in the address
    app.header("Talkie")
    expect(p.get_by_role("radio", name=re.compile("Voice messages"))).to_have_attribute("aria-checked", "true")

    # back on the speaker output the page is Announce again
    p.evaluate("localStorage.setItem('spk.output', 'speaker')")
    p.goto(f"{p.url.split('#')[0]}#/announce")
    p.reload()
    app.header("Announce")
    expect(p.locator(".sb [data-route='announce']")).to_have_text("Announce")
    expect(p.locator("form.ann-card")).to_be_visible()
    app.clean("talkie operator")


def test_viewer_gets_only_talkie(make_app, seeded):
    app = make_app("viewer", device="phone", lang="th", route="now")
    p = on_this_device(app)
    app.header("ทอล์คกี้")
    expect(p.locator(".tabbar [data-route='announce']")).to_have_text(re.compile(r"^ทอล์คกี้"))
    tabs = p.get_by_role("radiogroup", name="โหมดทอล์คกี้")
    expect(tabs.get_by_role("radio", name="วอล์กกี้")).to_have_attribute("aria-checked", "true")
    expect(tabs.get_by_role("radio", name=re.compile("ข้อความเสียง"))).to_be_visible()
    expect(p.locator(".tw-label")).to_have_text("กดค้างเพื่อพูด")
    expect(p.locator(".tw-pc.me .tw-pc-n")).to_have_text("คุณ")
    app.clean("talkie viewer")


def test_walkie_cards_and_join_chip(make_app, seeded):
    needs_ffmpeg(seeded)
    listener = make_app("viewer", device="desktop", route="now")
    lp = on_this_device(listener)
    live_requests = []
    lp.on("request", lambda r: live_requests.append(r.url) if "/talkie/live/" in r.url else None)
    talker = make_app("operator", device="desktop", route="now")
    tp = on_this_device(talker)
    expect(lp.locator(".tw-room .tw-cap")).to_have_text("In the room · 2")
    expect(lp.locator(".tw-pc")).to_have_count(2)

    # a member elsewhere in the app: the chip says who is in the Walkie; Join opens it
    other = make_app("owner", device="phone", route="now")
    op = on_this_device(other, "")
    hint = op.locator(".tw-hint")
    expect(hint).to_be_visible()
    expect(hint.locator(".tw-hint-t")).to_have_text("2 on Walkie")
    expect(hint.locator(".tw-hint-av")).to_have_count(2)
    hint.get_by_role("link").click()
    other.header("Talkie")
    assert other.hash() == "#/announce/walkie"
    expect(hint).to_be_hidden()  # not on the Talkie page
    expect(op.locator(".tw-room .tw-cap")).to_have_text("In the room · 3")
    # on Voice messages: online but out of the room, greyed for the others
    op.get_by_role("radio", name=re.compile("Voice messages")).click()
    away = lp.locator(".tw-pc.away")
    expect(away).to_have_attribute("aria-label", "Olivia Owner: Can’t hear")
    expect(lp.locator(".tw-pc").last).to_have_class(re.compile(r"\baway\b"))  # at the bottom
    expect(lp.locator(".tw-room .tw-cap")).to_have_text("In the room · 2")

    ptt = tp.get_by_role("button", name="Talk to everyone. Hold to talk")
    expect(ptt).to_be_enabled()
    hold(talker, ptt, tp.locator(".tw-card"), 300)
    expect(tp.locator(".tw-label")).to_have_text("Release to stop")
    expect(tp.locator(".tw-status")).to_have_text(re.compile(r"● You are live 0:0\d"))
    expect(tp.locator(".tw-pc.me")).to_have_class(re.compile(r"\btalking\b"))
    # the listener sees them talking once the voice plays
    oscar = lp.locator(".tw-pc", has_text="Oscar")
    expect(oscar).to_have_class(re.compile(r"\btalking\b"), timeout=10_000)
    expect(oscar.locator(".tw-pc-bars")).to_have_count(1)
    expect(lp.locator(".tw-label")).to_have_text("Wait until they finish")
    expect(lp.locator(".tw-ptt")).to_be_disabled()
    # out of the room: no audio, but the Walkie tab shows someone talks there
    expect(op.locator(".tw-livebadge")).to_be_visible()
    expect(op.get_by_role("img", name="Someone is talking on Walkie")).to_be_visible()
    tp.wait_for_timeout(1500)
    tp.mouse.up()
    expect(tp.locator(".tw-card")).to_have_attribute("data-state", "idle", timeout=10_000)
    expect(oscar).not_to_have_class(re.compile(r"\btalking\b"), timeout=10_000)
    expect(op.locator(".tw-livebadge")).to_be_hidden()
    assert live_requests, "the listener never fetched the live stream"
    # a walkie talk is not kept
    tp.get_by_role("radio", name=re.compile("Voice messages")).click()
    expect(tp.locator(".tw-row")).to_have_count(0)

    # Hide puts the chip away (until the room empties)
    op.goto(f"{op.url.split('#')[0]}#/playlists")
    other.header()
    expect(hint).to_be_visible()
    expect(hint.locator(".tw-hint-t")).to_have_text("1 on Walkie")
    hint.get_by_role("button", name="Hide").click()
    expect(hint).to_be_hidden()
    for a in (listener, talker, other):
        a.clean("talkie walkie")


def test_voice_message_delete_undo_and_unread(make_app, seeded):
    needs_ffmpeg(seeded)
    author = make_app("operator", device="desktop", route="now")
    ap = on_this_device(author, "announce/messages")
    deletes = []
    ap.on("request", lambda r: deletes.append(r.url) if r.method == "DELETE" and "/talkie/clips/" in r.url else None)
    reader = make_app("viewer", device="phone", route="now")
    rp = on_this_device(reader, "")

    rec = ap.get_by_role("button", name="Hold to record a message")
    hold(author, rec, ap.locator(".tw-recbar"), 1500)
    expect(ap.locator(".tw-reclabel")).to_have_text(re.compile(r"● Recording 0:0\d"))
    ap.mouse.up()
    author.toast("Sent. Everyone can play it back for 24 hours.")
    mine = ap.locator(".tw-row").first
    expect(mine.locator("strong")).to_have_text("You")
    expect(mine.locator(".c-badge")).to_have_count(0)

    # the others: a count on the nav item (any page) and on the tab, "Not played yet" on the row
    navb = rp.locator(".tabbar [data-route='announce'] .tw-navb")
    expect(navb).to_have_text(re.compile(r"^[1-9]\d*$"))
    unread = int(navb.inner_text())
    expect(navb).to_have_attribute("aria-label", f"{unread} not played yet")
    rp.locator(".tabbar [data-route='announce']").click()
    reader.header("Talkie")
    tab = rp.get_by_role("radio", name=re.compile("Voice messages"))
    expect(tab.locator(".tw-unread")).to_have_text(str(unread))
    tab.click()
    row = rp.locator(".tw-row").first
    expect(row.locator("strong")).to_have_text("Oscar Operator")
    expect(row.locator(".c-badge")).to_have_text("Not played yet")
    expect(row.locator(".tw-more")).to_have_count(0)  # only the author deletes

    # delete, Undo: back, and nothing went to the server
    count = ap.locator(".tw-row").count()
    mine.get_by_role("button", name="Message options").click()
    ap.locator(".popover").get_by_role("button", name="Delete").click()
    expect(ap.locator(".tw-row")).to_have_count(count - 1)
    author.toast("Voice message deleted").get_by_role("button", name="Undo").click()
    expect(ap.locator(".tw-row")).to_have_count(count)
    ap.wait_for_timeout(5500)
    assert deletes == []

    # delete for real: the DELETE goes once the Undo's time is up, and the others lose it too
    ap.locator(".tw-row").first.get_by_role("button", name="Message options").click()
    deleted = lambda r: r.request.method == "DELETE" and "/talkie/clips/" in r.url  # noqa: E731
    with ap.expect_response(deleted, timeout=10_000) as got:
        ap.locator(".popover").get_by_role("button", name="Delete").click()
        expect(ap.locator(".tw-row")).to_have_count(count - 1)
    assert got.value.status == 204
    expect(rp.locator(".tw-row")).to_have_count(count - 1)
    if unread == 1:
        expect(rp.locator(".tabbar [data-route='announce'] .tw-navb")).to_have_count(0)
        expect(tab.locator(".tw-unread")).to_be_hidden()
    for a in (author, reader):
        a.clean("talkie messages")
