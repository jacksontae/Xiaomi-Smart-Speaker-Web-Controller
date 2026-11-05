"""Podcast subscriptions on Music > Podcasts: follow a show from its episodes, see it under Following with a count
of new episodes, open it (the count clears, its new episodes are marked), unfollow. The podcast API is stubbed in
the browser with a small stateful fake shaped like the server's (feeds are never fetched for real)."""
import json
import re

import pytest
from playwright.sync_api import expect

from .e2ekit import wait_for

FEED_URL = "https://podcast.example.com/subs.xml"
SHOWS = [{"id": 7, "title": "E2E Daily", "author": "E2E Author", "feed_url": FEED_URL, "artwork": None,
          "genre": "News", "episode_count": 3}]
EPISODES = [
    {"title": f"Daily part {n}", "url": f"https://podcast.example.com/d{n}.mp3", "content_type": "audio/mpeg",
     "duration": 600, "published": f"2026-10-{day}T00:00:00+00:00", "thumbnail": None}
    for n, day in ((3, "09"), (2, "08"), (1, "01"))
]
FEED = {"title": "E2E Daily", "author": "E2E Author", "artwork": None, "description": None, "episodes": EPISODES}
LAST_VISIT = "2026-10-05T00:00:00+00:00"  # the follower "last opened" the show before parts 2 and 3 came out

TEXT = {
    "en": {"label": "Podcast name or RSS link", "open": "Show episodes of E2E Daily", "follow": "Follow",
           "following": "Following", "section": "Following", "new2": "2 new", "new": "New",
           "back": "All followed shows", "results": "All results"},
    "th": {"label": "ชื่อพอดแคสต์ หรือลิงก์ RSS", "open": "ดูตอนของ E2E Daily", "follow": "ติดตาม",
           "following": "ติดตามอยู่", "section": "กำลังติดตาม", "new2": "ใหม่ 2 ตอน", "new": "ใหม่",
           "back": "ทั้งหมดที่ติดตาม", "results": "ผลการค้นหาทั้งหมด"},
}


class FakeSubs:
    """GET/POST /podcasts/subs, POST …/{id}/seen, DELETE …/{id} and GET /podcasts/episodes, kept in memory."""

    def __init__(self):
        self.sub = None
        self.calls = []

    def view(self):
        fresh = sum(ep["published"] > self.sub["seen_at"] for ep in EPISODES)
        return self.sub | {"new_count": fresh}

    def handle(self, route):
        req = route.request
        path = re.sub(r"^https?://[^/]+", "", req.url).split("?")[0]
        self.calls.append((req.method, path))
        if path == "/podcasts/subs" and req.method == "GET":
            body = [self.view()] if self.sub else []
        elif path == "/podcasts/subs" and req.method == "POST":
            data = json.loads(req.post_data)
            assert data["feed_url"] == FEED_URL and data["title"] == "E2E Daily", data
            self.sub = {"id": 1, "feed_url": FEED_URL, "title": data["title"], "author": data.get("author"),
                        "artwork": None, "latest_at": EPISODES[0]["published"], "seen_at": LAST_VISIT,
                        "created_at": LAST_VISIT}
            body = self.view()
        elif path == "/podcasts/subs/1/seen":
            self.sub["seen_at"] = "2026-11-01T00:00:00+00:00"
            body = self.view()
        elif path == "/podcasts/subs/1" and req.method == "DELETE":
            self.sub = None
            route.fulfill(status=204)
            return
        elif path == "/podcasts/episodes":
            body = FEED | {"subscription": self.sub}
        elif path == "/podcasts/search":
            body = SHOWS
        else:
            route.continue_()
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


@pytest.mark.parametrize(("device", "lang"), [("phone", "th"), ("android", "en")])
def test_follow_open_and_unfollow(make_app, seeded, device, lang):
    tx = TEXT[lang]
    fake = FakeSubs()
    app = make_app("operator", device=device, lang=lang, go=False)
    p = app.page
    p.route(re.compile(r".*/podcasts/(subs|episodes|search)(/.*)?(\?.*)?$"), fake.handle)
    app.go("music/podcasts")
    subs = p.locator(".mu-subs")
    expect(p.get_by_label(tx["label"])).to_be_visible()
    expect(subs).to_be_hidden()  # following nothing yet

    # follow from the show's episodes (opened from search results)
    field = p.get_by_label(tx["label"])
    field.fill("e2e")
    field.press("Enter")
    p.get_by_role("button", name=tx["open"]).click()
    expect(p.locator(".mu-show-t")).to_have_text("E2E Daily")
    follow = p.locator(".mu-follow")
    expect(follow).to_have_attribute("aria-pressed", "false")
    expect(follow).to_have_text(tx["follow"])
    follow.click()
    expect(follow).to_have_attribute("aria-pressed", "true")
    expect(follow).to_have_text(tx["following"])
    assert ("POST", "/podcasts/subs") in fake.calls

    # back on the list: Following shows it with its new-episode count
    p.get_by_role("button", name=tx["results"]).click()
    expect(subs).to_be_visible()
    expect(subs.locator(".tb-sec h2")).to_have_text(tx["section"])
    row = subs.locator(".tb-row", has_text="E2E Daily")
    expect(row.locator(".c-badge")).to_have_text(tx["new2"])
    expect(row).to_contain_text("E2E Author ·")

    # open it: back link names the Following list, parts 2 and 3 are marked new, and it is marked seen
    row.locator(".mu-rowbtn").click()
    expect(p.locator(".mu-show-t")).to_have_text("E2E Daily")
    expect(p.get_by_role("button", name=tx["back"])).to_be_visible()
    expect(subs).to_be_hidden()
    expect(p.locator(".tb-s > .mu-new")).to_have_count(2)
    expect(p.locator(".tb-row", has_text="Daily part 3").locator(".mu-new")).to_have_text(tx["new"])
    expect(p.locator(".tb-row", has_text="Daily part 1").locator(".mu-new")).to_have_count(0)
    expect(p.locator(".mu-follow")).to_have_attribute("aria-pressed", "true")
    wait_for(lambda: ("POST", "/podcasts/subs/1/seen") in fake.calls, what="the show marked seen")
    p.get_by_role("button", name=tx["back"]).click()
    expect(row).to_be_visible()
    expect(row.locator(".c-badge")).to_have_count(0)  # the count cleared

    # unfollow: the Following section goes away
    row.locator(".mu-rowbtn").click()
    p.locator(".mu-follow").click()
    expect(p.locator(".mu-follow")).to_have_attribute("aria-pressed", "false")
    assert ("DELETE", "/podcasts/subs/1") in fake.calls
    p.get_by_role("button", name=tx["back"]).click()
    expect(p.get_by_role("button", name=tx["open"])).to_be_visible()  # back on the search results
    expect(subs).to_be_hidden()
    app.clean(f"podcast subs {device}")
