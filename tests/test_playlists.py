import pytest
import yt_dlp
from conftest import REAL_YT_EXTRACT

VIDEOS = {
    "dQw4w9WgXcQ": {"title": "Never Gonna", "duration": 213, "channel": "Rick"},
    "abcdefghijk": {"title": "Piano Calm", "duration": 600.5, "uploader": "Studio"},
}


@pytest.fixture
def fake_yt(app, monkeypatch):
    """yt-dlp stand-in: watch URLs resolve to VIDEOS, ytsearchN: returns flat entries. Records every target."""
    calls = []

    def extract(target):
        calls.append(target)
        if target.startswith("ytsearch"):
            n, words = target.removeprefix("ytsearch").split(":", 1)
            hits = [{"id": vid, **meta} for vid, meta in VIDEOS.items() if words.lower() in meta["title"].lower()]
            return {"entries": hits[: int(n)]}
        vid = target.rsplit("v=", 1)[-1].rsplit("/", 1)[-1]
        if vid not in VIDEOS:
            raise yt_dlp.utils.DownloadError("Video unavailable")
        return {"id": vid, **VIDEOS[vid]}

    monkeypatch.setattr(app, "yt_extract", extract)
    return calls


def new_playlist(client, name="Morning"):
    r = client.post("/playlists", json={"name": name})
    assert r.status_code == 200
    return r.json()


def add(client, pid, **body):
    return client.post(f"/playlists/{pid}/items", json=body)


def test_playlist_crud(client):
    pl = new_playlist(client, "  Morning  ")
    assert pl["name"] == "Morning" and pl["items"] == [] and set(pl) == {"id", "name", "updated_at", "items"}
    assert client.patch(f"/playlists/{pl['id']}", json={"name": "Evening"}).json()["name"] == "Evening"
    assert client.get(f"/playlists/{pl['id']}").json()["name"] == "Evening"
    assert client.post("/playlists", json={"name": "   "}).status_code == 400
    assert client.delete(f"/playlists/{pl['id']}").status_code == 204
    assert client.get(f"/playlists/{pl['id']}").status_code == 404
    assert client.delete(f"/playlists/{pl['id']}").status_code == 404
    assert client.patch("/playlists/999", json={"name": "x"}).status_code == 404


def test_add_youtube_by_url_id_or_words(client, fake_yt):
    pid = new_playlist(client)["id"]
    by_url = add(client, pid, kind="youtube", source="https://www.youtube.com/watch?v=dQw4w9WgXcQ").json()
    assert by_url["source"] == "dQw4w9WgXcQ" and by_url["title"] == "Never Gonna" and by_url["duration"] == 213.0
    assert by_url["thumbnail"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert by_url["kind"] == "youtube" and by_url["lang"] is None
    by_id = add(client, pid, kind="youtube", source="abcdefghijk").json()
    assert by_id["title"] == "Piano Calm"
    by_words = add(client, pid, kind="youtube", source="piano").json()
    assert by_words["source"] == "abcdefghijk"
    assert fake_yt[-1] == "ytsearch1:piano"
    assert add(client, pid, kind="youtube", source="nothing matches").status_code == 404


def test_youtube_id_lookalike_falls_back_to_search(client, fake_yt):
    pid = new_playlist(client)["id"]
    add(client, pid, kind="youtube", source="piano_calm_")  # 11 id-like chars, but not a real video
    assert fake_yt == ["https://www.youtube.com/watch?v=piano_calm_", "ytsearch1:piano_calm_"]


def test_youtube_rejects_non_youtube_results(client, app, monkeypatch):
    monkeypatch.setattr(app, "yt_extract", lambda target: {"id": "soundcloud-123456", "title": "x"})
    pid = new_playlist(client)["id"]
    assert add(client, pid, kind="youtube", source="https://soundcloud.com/a/b").status_code == 400


def test_youtube_lookup_failure_is_502(client, app, monkeypatch):
    def broken(target):
        raise yt_dlp.utils.DownloadError("network down")

    monkeypatch.setattr(app, "yt_extract", broken)
    pid = new_playlist(client)["id"]
    assert add(client, pid, kind="youtube", source="https://youtu.be/zzzzzzzzzzz").status_code == 502


def test_add_url_and_tts_items(client, app):
    pid = new_playlist(client)["id"]
    url = add(client, pid, kind="url", source="https://radio.example/live.mp3", title="Radio").json()
    assert url["source"] == "https://radio.example/live.mp3" and url["title"] == "Radio"
    assert add(client, pid, kind="url", source="https://radio.example/x.mp3").status_code == 400  # no title
    assert add(client, pid, kind="url", source="file:///etc/passwd", title="x").status_code == 400
    text = "ประกาศ " * 20
    tts = add(client, pid, kind="tts", source=text).json()
    assert tts["title"] == text.strip()[:60] and tts["lang"] == app.settings.tts_lang
    assert add(client, pid, kind="tts", source="hello", lang="en").json()["lang"] == "en"
    assert add(client, pid, kind="tts", source="x" * 1001).status_code == 400
    assert add(client, pid, kind="tts", source="   ").status_code == 400
    assert add(client, pid, kind="video", source="x").status_code == 422
    assert add(client, 999, kind="tts", source="x").status_code == 404


def test_playlist_summary_list(client, fake_yt):
    pid = new_playlist(client, "B list")["id"]
    add(client, pid, kind="tts", source="first")
    add(client, pid, kind="youtube", source="dQw4w9WgXcQ")
    add(client, pid, kind="youtube", source="abcdefghijk")
    new_playlist(client, "a list")
    lists = client.get("/playlists").json()
    assert [p["name"] for p in lists] == ["a list", "B list"]
    empty, full = lists
    assert empty["item_count"] == 0 and empty["total_duration"] == 0 and empty["cover"] is None
    assert full["item_count"] == 3 and full["total_duration"] == 813.5
    assert full["cover"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert set(full) == {"id", "name", "item_count", "total_duration", "updated_at", "cover"}


def test_reorder_and_delete_items(client):
    pid = new_playlist(client)["id"]
    ids = [add(client, pid, kind="tts", source=f"item {i}").json()["id"] for i in range(3)]
    r = client.put(f"/playlists/{pid}/order", json={"item_ids": [ids[2], ids[0], ids[1]]})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [ids[2], ids[0], ids[1]]
    assert [i["id"] for i in client.get(f"/playlists/{pid}").json()["items"]] == [ids[2], ids[0], ids[1]]
    for bad in ([ids[0], ids[1]], [ids[0], ids[1], ids[1]], [*ids, 999], [ids[0], ids[1], 999]):
        assert client.put(f"/playlists/{pid}/order", json={"item_ids": bad}).status_code == 409, bad
    assert client.put("/playlists/999/order", json={"item_ids": []}).status_code == 404
    assert client.delete(f"/playlists/{pid}/items/{ids[0]}").status_code == 204
    assert client.delete(f"/playlists/{pid}/items/{ids[0]}").status_code == 404
    new_item = add(client, pid, kind="tts", source="last").json()
    assert [i["id"] for i in client.get(f"/playlists/{pid}").json()["items"]] == [ids[2], ids[1], new_item["id"]]


def test_item_of_another_playlist_cannot_be_deleted(client):
    a, b = new_playlist(client, "a")["id"], new_playlist(client, "b")["id"]
    item = add(client, a, kind="tts", source="x").json()
    assert client.delete(f"/playlists/{b}/items/{item['id']}").status_code == 404


def test_playlist_item_limit(client, app, monkeypatch):
    monkeypatch.setattr(app, "MAX_PLAYLIST_ITEMS", 2)
    pid = new_playlist(client)["id"]
    add(client, pid, kind="tts", source="1")
    add(client, pid, kind="tts", source="2")
    assert add(client, pid, kind="tts", source="3").status_code == 409


def test_viewer_reads_operator_writes(as_role):
    op, viewer = as_role("operator"), as_role("viewer")
    pid = new_playlist(op)["id"]
    assert viewer.get(f"/playlists/{pid}").status_code == 200
    assert viewer.post("/playlists", json={"name": "x"}).status_code == 403
    assert viewer.post(f"/playlists/{pid}/items", json={"kind": "tts", "source": "x"}).status_code == 403


def test_youtube_search(client, fake_yt):
    r = client.get("/youtube/search", params={"q": "e", "limit": 1})
    assert r.status_code == 200
    assert r.json() == [{
        "video_id": "dQw4w9WgXcQ", "title": "Never Gonna", "duration": 213.0, "channel": "Rick",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    }]
    assert fake_yt[-1] == "ytsearch1:e"
    both = client.get("/youtube/search", params={"q": "n"}).json()
    assert {v["video_id"] for v in both} == set(VIDEOS) and both[1]["channel"] == "Studio"
    assert fake_yt[-1] == "ytsearch8:n"
    assert client.get("/youtube/search", params={"q": ""}).status_code == 422
    assert client.get("/youtube/search", params={"q": "x", "limit": 50}).status_code == 422


def test_yt_extract_never_downloads(app, monkeypatch):
    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, target, download):
            seen["download"] = download
            return {"entries": []}

    monkeypatch.setattr(app, "yt_extract", REAL_YT_EXTRACT)
    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", FakeYDL)
    assert app.yt_search("x", 3) == []
    assert seen["download"] is False and seen["opts"]["skip_download"] and seen["opts"]["extract_flat"]

