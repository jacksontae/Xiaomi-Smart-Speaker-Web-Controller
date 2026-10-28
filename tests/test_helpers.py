from pathlib import Path

import pytest


def test_split_text_keeps_short_text_whole(app):
    assert app.split_text("สวัสดีครับ") == ["สวัสดีครับ"]


def test_split_text_cuts_long_thai_without_spaces(app):
    text = "ก" * 400
    chunks = app.split_text(text)
    assert "".join(chunks) == text
    assert all(len(c) <= app.TTS_CHUNK for c in chunks)


def test_split_text_breaks_on_words(app):
    words = ["word"] * 100
    chunks = app.split_text(" ".join(words))
    assert all(len(c) <= app.TTS_CHUNK for c in chunks)
    assert " ".join(chunks).split() == words


@pytest.mark.parametrize(
    ("name", "expected"),
    [("a.m4a", "audio/mp4"), ("a.webm", "audio/webm"), ("a.mp3", "audio/mpeg")],
)
def test_content_type_for(app, name, expected):
    assert app.content_type_for(Path(name)) == expected


def test_settings_reject_out_of_range_volume(app):
    with pytest.raises(ValueError):
        app.Settings(default_volume=1.5)


def _fake_connections(app, monkeypatch):
    class Socket:
        def __init__(self):
            self.is_connected, self.alive, self.stopped = True, True, False

        def is_alive(self):
            return self.alive

        def disconnect(self):
            self.stopped = True

    class Conn:
        def __init__(self):
            self.socket_client = Socket()
            self.waits = 0

        def wait(self, timeout=None):
            self.waits += 1

    made = []
    monkeypatch.setattr(app, "connect_speaker", lambda ip: made.append(Conn()) or made[-1])
    monkeypatch.setattr(app, "_cast", None)
    return made


def test_get_cast_waits_while_pychromecast_reconnects(app, monkeypatch):
    from conftest import REAL_GET_CAST

    made = _fake_connections(app, monkeypatch)
    first = REAL_GET_CAST()
    first.socket_client.is_connected = False  # reconnect in progress, thread alive
    assert REAL_GET_CAST() is first
    assert first.waits == 2 and len(made) == 1 and not first.socket_client.stopped


def test_get_cast_replaces_dead_connection(app, monkeypatch):
    from conftest import REAL_GET_CAST

    made = _fake_connections(app, monkeypatch)
    first = REAL_GET_CAST()
    first.socket_client.alive = False
    second = REAL_GET_CAST()
    assert second is not first and first.socket_client.stopped and len(made) == 2
