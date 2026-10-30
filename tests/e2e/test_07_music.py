"""Music (operator+): YouTube / radio / podcast searches (one live search each, then mocked results so the
rest is repeatable), favourites, add to playlist, play errors, and My files upload/rename/delete/413/415."""
import json
import re
import time

from playwright.sync_api import expect

from .e2ekit import SPEAKER_WAIT, mp3_bytes

YT = [{"video_id": "jNQXAC9IVRw", "title": "E2E Song One", "channel": "E2E Channel", "duration": 185,
       "thumbnail": None},
      {"video_id": "e2eVid00002", "title": "E2E Song Two", "channel": "E2E Channel", "duration": 61,
       "thumbnail": None}]
RADIO = [{"name": "E2E Radio", "url": "http://192.0.2.30/stream.mp3", "content_type": "audio/mpeg", "favicon": None,
          "country": "TH", "tags": "jazz,lounge,easy", "bitrate": 128}]
SHOWS = [{"id": 1, "title": "E2E Podcast", "author": "E2E Author", "feed_url": "https://podcast.example.com/feed.xml",
          "artwork": None, "genre": "News", "episode_count": 2}]
FEED = {"title": "E2E Podcast", "author": "E2E Author", "artwork": None, "episodes": [
    {"title": "Episode one", "url": "https://podcast.example.com/ep1.mp3", "content_type": "audio/mpeg",
     "duration": 600, "published": "2026-10-01T00:00:00Z", "thumbnail": None},
    {"title": "Episode two", "url": "https://podcast.example.com/ep2.mp3", "content_type": "audio/mpeg",
     "duration": 1200, "published": "2026-10-08T00:00:00Z", "thumbnail": None}]}


def _eq(a, b):
    assert a == b, f"{a} != {b}"


def mock(p, pattern, data, status=200):
    p.route(pattern, lambda r: r.fulfill(status=status, content_type="application/json", body=json.dumps(data)))


def source(p, name):
    p.locator(".mu-src").get_by_role("radio", name=name).click()


def test_music_youtube_live_then_mocked(make_app, seeded):
    app = make_app("operator", device="desktop", route="music")
    p = app.page
    app.header("Music")
    source(p, "Radio")
    assert app.hash() == "#/music/radio"
    source(p, "YouTube")
    assert app.hash() == "#/music/youtube"
    expect(p.locator(".mu-out")).to_contain_text("Search for a song")
    # empty search
    p.locator(".tb-search button[type=submit]").click()
    expect(p.locator(".mu-out")).to_have_text("Type something to search for first.")
    # one live search (internet): results or a plain error, never a crash
    p.get_by_label("Search YouTube").fill("lofi")
    p.locator(".tb-search button[type=submit]").click()
    expect(p.locator(".mu-out .tb-cap, .mu-out .tb-err, .mu-out .tb-note").first).to_be_visible(timeout=30_000)
    expect(p.locator(".mu-out .tb-loading")).to_have_count(0, timeout=30_000)
    # mocked results from here
    mock(p, "**/youtube/search*", YT)
    p.get_by_label("Search YouTube").fill("e2e")
    p.locator(".tb-search button[type=submit]").click()
    expect(p.locator(".mu-out .tb-cap")).to_have_text("Results for “e2e”")
    row = p.locator(".tb-row", has_text="E2E Song One")
    expect(row.locator(".tb-dur")).to_have_text("3:05")
    # add to a new playlist from the result
    name = f"From YouTube {int(time.time()) % 10000}"
    row.get_by_role("button", name="Add E2E Song One to a playlist").click()
    sheet = app.sheet()
    sheet.get_by_role("button", name="Create and add").click()
    expect(sheet.locator(".form-error")).to_have_text("Give it a name first.")
    sheet.get_by_label("New playlist").fill(name)
    sheet.get_by_role("button", name="Create and add").click()
    app.toast(f"Added to {name}", timeout=30_000)  # the server looks the video up on YouTube
    app.no_sheet()
    pl = next(x for x in seeded.get("/playlists") if x["name"] == name)
    assert seeded.get(f"/playlists/{pl['id']}")["items"][0]["source"] == "jNQXAC9IVRw"
    # a video YouTube doesn't know: the add fails with a message, and no empty playlist is left behind
    count = len(seeded.get("/playlists"))
    p.locator(".tb-row", has_text="E2E Song Two").get_by_role("button", name="Add E2E Song Two to a playlist").click()
    sheet = app.sheet()
    sheet.get_by_label("New playlist").fill(name + " B")
    sheet.get_by_role("button", name="Create and add").click()
    expect(sheet.locator(".form-error")).not_to_have_text("", timeout=30_000)
    app.soft(lambda: expect(sheet.locator(".form-error")).not_to_have_text("Not found. It may have been deleted."),
             "unknown YouTube video: message says the video wasn't found, not 'may have been deleted'")
    app.soft(lambda: _eq(len(seeded.get("/playlists")), count),
             "'Create and add' with an item the server refuses leaves no empty playlist behind")
    sheet.locator(".tb-pick", has_text=name).first.click()
    expect(sheet.locator(".form-error")).not_to_have_text("", timeout=30_000)
    sheet.locator(".sheet-close").click()
    app.no_sheet()
    # network failure on play: plain message, button back to Play
    p.route("**/youtube", lambda r: r.abort() if r.request.method == "POST" else r.continue_())
    play = row.get_by_role("button", name="Play E2E Song One on the speaker")
    play.click()
    app.toast("Can't reach the server")
    expect(row.get_by_role("button", name="Play E2E Song One on the speaker")).to_be_enabled()
    # the search survives leaving and coming back
    app.go("playlists")
    app.go("music")
    expect(p.get_by_label("Search YouTube")).to_have_value("e2e")
    app.clean("music youtube")


def test_music_radio_favourites_and_play(make_app, seeded, drained):
    app = make_app("operator", device="phone", route="music/radio")
    p = app.page
    # the pane opens with popular stations from the live directory (results or a plain error)
    expect(p.locator(".mu-block .tb-sec, .mu-block .tb-err").first).to_be_visible(timeout=30_000)
    mock(p, "**/radio/search*", RADIO)
    p.get_by_label("Search radio stations").fill("e2e")
    p.get_by_label("Search radio stations").press("Enter")
    row = p.locator(".mu-block").last.locator(".tb-row", has_text="E2E Radio")
    expect(row).to_contain_text("jazz, lounge, TH")
    heart = row.locator("button.mu-heart")
    expect(heart).to_have_attribute("aria-pressed", "false")
    heart.click()
    expect(heart).to_have_attribute("aria-pressed", "true")
    expect(p.locator(".mu-block").first).to_contain_text("Favourites")
    assert any(f["name"] == "E2E Radio" for f in seeded.get("/radio/favorites"))
    # play from the favourite: the offline speaker says so
    fav = p.locator(".mu-block").first.locator(".tb-row", has_text="E2E Radio")
    fav.get_by_role("button", name="Play E2E Radio on the speaker").click()
    expect(fav.locator(".tb-s")).to_have_text("Loading on the speaker…")
    app.toast("Can't reach the speaker", timeout=SPEAKER_WAIT)
    # un-favourite from the favourites row
    fav.locator("button.mu-heart").click()
    expect(p.locator(".mu-block").first).not_to_contain_text("Favourites")
    assert not any(f["name"] == "E2E Radio" for f in seeded.get("/radio/favorites"))
    # directory down: plain message with Try again
    p.unroute("**/radio/search*")
    mock(p, "**/radio/search*", {"detail": "radio-browser unreachable"}, status=502)
    p.get_by_label("Search radio stations").fill("down")
    p.get_by_label("Search radio stations").press("Enter")
    expect(p.locator(".tb-err")).to_contain_text("Couldn't reach the radio directory")
    expect(p.locator(".tb-err").get_by_role("button", name="Try again")).to_be_visible()
    app.clean("music radio")


def test_music_podcasts(make_app, seeded):
    app = make_app("operator", device="ipad", route="music/podcasts")
    p = app.page
    field = p.get_by_label("Podcast name or RSS link")
    # a feed on a private network is refused by the server (real request)
    field.fill("http://192.0.2.5/feed.xml")
    p.get_by_role("button", name="Find").click()
    expect(p.locator(".tb-err")).to_contain_text(re.compile("private network|Couldn't read that podcast feed"),
                                                 timeout=30_000)
    mock(p, "**/podcasts/search*", SHOWS)
    mock(p, "**/podcasts/episodes*", FEED)
    field.fill("e2e")
    p.get_by_role("button", name="Find").click()
    expect(p.locator(".tb-sec h2")).to_have_text("Podcasts matching “e2e”")
    p.get_by_role("button", name="Show episodes of E2E Podcast").click()
    expect(p.locator(".mu-show-t")).to_have_text("E2E Podcast")
    ep = p.locator(".tb-row", has_text="Episode one")
    expect(ep).to_contain_text("10 min")
    ep.get_by_role("button", name="Add Episode one to a playlist").click()
    sheet = app.sheet()
    name = f"Pods {int(time.time()) % 10000}"
    sheet.get_by_label("New playlist").fill(name)
    sheet.get_by_role("button", name="Create and add").click()
    app.toast(f"Added to {name}")
    app.no_sheet()
    p.get_by_role("button", name="All results").click()
    expect(p.get_by_role("button", name="Show episodes of E2E Podcast")).to_be_visible()
    mock(p, "**/podcasts/search*", {"detail": "itunes down"}, status=502)
    p.unroute("**/podcasts/search*")
    mock(p, "**/podcasts/search*", {"detail": "itunes down"}, status=502)
    field.fill("down")
    p.get_by_role("button", name="Find").click()
    expect(p.locator(".tb-err")).to_contain_text("Couldn't reach the podcast directory")
    app.clean("music podcasts")


def upload(p, name, data, mime="audio/mpeg"):
    p.locator(".mu-pane input[type=file]").set_input_files(files=[{"name": name, "mimeType": mime, "buffer": data}])


def test_music_files_upload_rename_delete(make_app, seeded):
    app = make_app("operator", device="desktop", route="music/files")
    p = app.page
    expect(p.locator(".mu-fnote")).to_contain_text("Audio files up to 1 MB")
    title = f"e2e-tone-{int(time.time()) % 100000}"
    upload(p, f"{title}.mp3", mp3_bytes(2))
    app.toast(f"{title} uploaded")
    row = p.locator(".tb-row", has_text=title)
    expect(row).to_be_visible()
    # client-side checks: too big, not audio
    upload(p, "huge.mp3", b"ID3" + b"\0" * (1024 * 1024 + 10))
    expect(p.locator(".mu-uperr")).to_contain_text("huge.mp3 is too big. Files can be up to 1 MB.")
    upload(p, "notes.txt", b"hello", mime="text/plain")
    expect(p.locator(".mu-uperr")).to_contain_text("notes.txt isn’t an audio file the speaker can play")
    # server-side checks: content that isn't audio (415), and a 413 from the server
    upload(p, "fake.mp3", b"this is not audio at all" * 10)
    expect(p.locator(".mu-uperr")).to_contain_text("fake.mp3 isn’t an audio file the speaker can play")
    p.route("**/files?*", lambda r: r.fulfill(status=413, content_type="application/json",
                                             body='{"detail":"Files can be at most 1 MB"}')
            if r.request.method == "POST" else r.continue_())
    upload(p, "big-on-server.mp3", mp3_bytes(1))
    expect(p.locator(".mu-uperr")).to_contain_text("big-on-server.mp3 is too big. Files can be up to 1 MB.")
    p.unroute("**/files?*")
    # rename (empty refused)
    p.locator(".mu-edit").click()
    row.get_by_role("button", name=f"Rename {title}").click()
    sheet = app.sheet()
    sheet.get_by_label("File name").fill(" ")
    sheet.locator("button[type=submit]").click()
    expect(sheet.locator(".form-error")).to_have_text("Give it a name first.")
    sheet.get_by_label("File name").fill(f"{title} renamed")
    sheet.locator("button[type=submit]").click()
    app.no_sheet()
    row = p.locator(".tb-row", has_text=f"{title} renamed")
    expect(row).to_be_visible()
    # delete with Undo, then for real
    row.get_by_role("button", name=f"Delete {title} renamed").click()
    toast = app.toast(f"{title} renamed deleted")
    expect(p.locator(".tb-row", has_text=f"{title} renamed")).to_have_count(0)
    toast.get_by_role("button", name="Undo").click()
    expect(p.locator(".tb-row", has_text=f"{title} renamed")).to_be_visible()
    p.wait_for_timeout(6500)
    if p.locator(".mu-edit[aria-pressed=false]").count():  # the list was empty for a moment, which ends Edit
        p.locator(".mu-edit").click()
    assert any(f["title"] == f"{title} renamed" for f in seeded.get("/files")["items"])
    p.locator(".tb-row", has_text=f"{title} renamed").get_by_role("button", name=f"Delete {title} renamed").click()
    p.wait_for_timeout(6800)
    assert not any(f["title"].startswith(title) for f in seeded.get("/files")["items"])
    app.clean("music files")


def test_music_file_play_offline(make_app, seeded, drained):
    app = make_app("operator", device="phone", route="music/files")
    p = app.page
    title = f"e2e-play-{int(time.time()) % 100000}"
    upload(p, f"{title}.mp3", mp3_bytes(1))
    app.toast(f"{title} uploaded")
    p.locator(".tb-row", has_text=title).get_by_role("button", name=f"Play {title} on the speaker").click()
    app.toast("Can't reach the speaker", timeout=SPEAKER_WAIT)
    app.clean("music file play")


def test_music_why_joox_link(make_app, seeded):
    app = make_app("operator", device="desktop", route="music")
    p = app.page
    p.locator(".mu-why-lg a").click()
    app.header("Help")
    assert app.hash() == "#/help/joox"
    expect(p.locator("#hq-joox")).to_have_attribute("aria-expanded", "true")
    app.clean("why joox")
