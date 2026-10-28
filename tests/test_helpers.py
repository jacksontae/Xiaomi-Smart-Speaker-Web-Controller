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
