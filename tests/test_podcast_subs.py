"""Podcast subscriptions: personal to each member, with a count of episodes newer than their last visit."""
import email.utils
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from conftest import make_user, session_client
from test_sources import net  # noqa: F401 - fixture

import store

SHOW = "https://feeds.example.com/daily.xml"


def rss(*days_ago, title="Daily Brief"):
    """A feed with one audio episode published each of `days_ago` days back (newest first)."""
    now = datetime.now(UTC)
    items = "".join(
        f"<item><title>Ep {d}</title><pubDate>{email.utils.format_datetime(now - timedelta(days=d))}</pubDate>"
        f'<enclosure url="https://cdn.example.com/ep{d}.mp3" type="audio/mpeg" length="1"/></item>'
        for d in days_ago
    )
    return (f'<?xml version="1.0"?><rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
            f'<title>{title}</title><itunes:author>Example Media</itunes:author>'
            f'<itunes:image href="https://cdn.example.com/daily.jpg"/>{items}</channel></rss>').encode()


@pytest.fixture
def people(app):
    out = {}
    for name, role in (("ann", "viewer"), ("ben", "viewer"), ("root", "admin")):
        out[name] = session_client(make_user(name, role, name.title()))
    return out


def follow(c, feed_url=SHOW, **body):
    r = c.post("/podcasts/subs", json={"feed_url": feed_url, "title": "Daily Brief", **body})
    assert r.status_code == 200, r.text
    return r.json()


def backdate(app, sub_id, days):
    """Pretend the member last opened the show `days` days ago."""
    with app.db.tx() as db:
        db.execute("UPDATE podcast_subs SET seen_at = ? WHERE id = ?",
                   ((datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds"), sub_id))


def test_follow_counts_new_episodes_and_opening_clears_them(people, app, net):  # noqa: F811
    net.routes[("feeds.example.com", "/daily.xml")] = httpx.Response(200, content=rss(1, 3, 10))
    ann = people["ann"]
    sub = follow(ann, author="Example Media", artwork="https://cdn.example.com/daily.jpg")
    assert sub["title"] == "Daily Brief" and sub["new_count"] == 0 and sub["seen_at"]
    [listed] = ann.get("/podcasts/subs").json()
    assert listed["new_count"] == 0  # episodes from before following aren't new
    assert listed["latest_at"][:10] == (datetime.now(UTC) - timedelta(days=1)).date().isoformat()

    backdate(app, sub["id"], 5)
    app._feed_cache.clear()
    assert ann.get("/podcasts/subs").json()[0]["new_count"] == 2
    show = ann.get("/podcasts/episodes", params={"feed": SHOW}).json()
    assert show["subscription"]["id"] == sub["id"] and len(show["episodes"]) == 3
    seen = show["subscription"]["seen_at"]  # the page marks episodes after this one as new
    assert sum(ep["published"] > seen for ep in show["episodes"]) == 2

    r = ann.post(f"/podcasts/subs/{sub['id']}/seen")
    assert r.status_code == 200 and r.json()["new_count"] == 0 and r.json()["seen_at"] > seen
    assert ann.get("/podcasts/subs").json()[0]["new_count"] == 0

    assert ann.delete(f"/podcasts/subs/{sub['id']}").status_code == 204
    assert ann.get("/podcasts/subs").json() == []
    assert ann.get("/podcasts/episodes", params={"feed": SHOW}).json()["subscription"] is None


def test_subscriptions_are_personal(people, app, net):  # noqa: F811
    net.routes[("feeds.example.com", "/daily.xml")] = httpx.Response(200, content=rss(1))
    ann, ben, root = people["ann"], people["ben"], people["root"]
    sub = follow(ann)
    assert ben.get("/podcasts/subs").json() == [] and root.get("/podcasts/subs").json() == []
    assert ben.get("/podcasts/episodes", params={"feed": SHOW}).json()["subscription"] is None
    assert ben.post(f"/podcasts/subs/{sub['id']}/seen").status_code == 404
    assert ben.delete(f"/podcasts/subs/{sub['id']}").status_code == 404
    assert root.delete(f"/podcasts/subs/{sub['id']}").status_code == 404  # not even an admin's to remove
    theirs = follow(ben)
    assert theirs["id"] != sub["id"] and len(ann.get("/podcasts/subs").json()) == 1

    app.db.delete_user(app.db.credentials("ann")[0]["id"])  # a member's subscriptions go with them
    with app.db.tx() as db:
        assert db.execute("SELECT COUNT(*) FROM podcast_subs").fetchone()[0] == 1


def test_following_twice_keeps_one_row(people, app, net):  # noqa: F811
    ann = people["ann"]
    first = follow(ann)
    backdate(app, first["id"], 3)
    again = follow(ann, title="Daily Brief (new name)")
    assert again["id"] == first["id"] and again["title"] == "Daily Brief (new name)"
    assert again["seen_at"] < first["seen_at"]  # following again doesn't reset what counts as new
    assert len(ann.get("/podcasts/subs").json()) == 1


def test_follow_without_details_reads_the_feed(people, net):  # noqa: F811
    net.routes[("feeds.example.com", "/daily.xml")] = httpx.Response(200, content=rss(2, 4, title="From the feed"))
    r = people["ann"].post("/podcasts/subs", json={"feed_url": SHOW})
    assert r.status_code == 200, r.text
    sub = r.json()
    assert sub["title"] == "From the feed" and sub["author"] == "Example Media"
    assert sub["artwork"] == "https://cdn.example.com/daily.jpg" and sub["latest_at"]
    r = people["ann"].post("/podcasts/subs", json={"feed_url": "https://feeds.example.com/missing.xml"})
    assert r.status_code == 502


def test_follow_checks_the_url_and_needs_an_account(people, client, net):  # noqa: F811
    ann = people["ann"]
    assert ann.post("/podcasts/subs", json={"feed_url": "file:///etc/passwd", "title": "x"}).status_code == 400
    r = ann.post("/podcasts/subs", json={"feed_url": "http://lan.example.com/feed", "title": "x"})
    assert r.status_code == 400 and "public internet" in r.json()["detail"]
    sub = follow(ann, artwork="javascript:alert(1)")
    assert sub["artwork"] is None
    assert client.get("/podcasts/subs").status_code == 400  # the API token is no member
    assert client.post("/podcasts/subs", json={"feed_url": SHOW, "title": "x"}).status_code == 400
    net.routes[("feeds.example.com", "/daily.xml")] = httpx.Response(200, content=rss(1))
    assert client.get("/podcasts/episodes", params={"feed": SHOW}).json()["subscription"] is None


def test_feeds_are_cached_and_a_failing_one_shows_no_count(people, app, net):  # noqa: F811
    net.routes[("feeds.example.com", "/daily.xml")] = httpx.Response(200, content=rss(1))
    net.routes[("feeds.example.com", "/down.xml")] = httpx.Response(500)
    ann = people["ann"]
    follow(ann)
    follow(ann, feed_url="https://feeds.example.com/down.xml", title="Down show")
    subs = {s["title"]: s for s in ann.get("/podcasts/subs").json()}
    assert subs["Daily Brief"]["new_count"] == 0 and subs["Down show"]["new_count"] is None
    fetched = len(net.seen)
    ann.get("/podcasts/subs")
    assert len(net.seen) == fetched  # both answers (the failure too) are cached
    app._feed_cache[SHOW] = (app._feed_cache[SHOW][0] - app.FEED_CACHE_TTL - 1, app._feed_cache[SHOW][1])
    ann.get("/podcasts/subs")
    assert len(net.seen) == fetched + 1  # only the stale one is read again


def test_migration_from_6_adds_subscriptions(tmp_path):
    path = tmp_path / "v6.db"
    db = sqlite3.connect(path)
    for statement in store.SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    for version in range(2, 7):
        for statement in store.MIGRATIONS[version]:
            db.execute(statement)
    db.execute("INSERT INTO users (id, username, display_name, role, password_hash, created_at)"
               " VALUES (3, 'vee', 'Vee', 'viewer', 'x', 'x')")
    db.execute("PRAGMA user_version = 6")
    db.commit()
    db.close()

    upgraded = store.Store(path)
    assert upgraded.schema_version() == store.SCHEMA_VERSION
    sub = upgraded.add_sub(3, SHOW, "Daily Brief")
    assert upgraded.list_subs(3) == [sub] and upgraded.list_subs(4) == []
