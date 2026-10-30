"""Live talk: the /talk WebSocket protocol and state machine, with a fake transcoder or a stub ffmpeg."""
import asyncio
import sys
import time
import wave
from io import BytesIO
from types import SimpleNamespace

import pytest
from conftest import BASE, path_of
from starlette.websockets import WebSocketDisconnect

import talk

WEBM = "audio/webm;codecs=opus"


class FakeTranscoder:
    """Stands in for ffmpeg: every chunk written comes straight back out as b"MP3:" + chunk."""

    def __init__(self, fmt, made, fail_start=False, fail_write=False):
        self.fmt, self.fail_start, self.fail_write = fmt, fail_start, fail_write
        self.written, self.finished, self.killed = [], False, False
        self.out = asyncio.Queue()
        made.append(self)

    async def start(self):
        if self.fail_start:
            raise talk.TranscoderError("Can't start ffmpeg (No such file or directory)")

    async def write(self, data):
        if self.fail_write:
            raise talk.TranscoderError("ffmpeg stopped: Invalid data found when processing input")
        self.written.append(data)
        self.out.put_nowait(b"MP3:" + data)

    async def read(self):
        return await self.out.get()

    async def finish(self, timeout):
        self.finished = True
        self.out.put_nowait(b"")

    def kill(self):
        self.killed = True
        self.out.put_nowait(b"")


@pytest.fixture
def talking(app, monkeypatch):
    """Fake transcoder, short timers, and the end-of-talk speaker work recorded instead of run."""
    made, finished = [], []
    opts = SimpleNamespace(made=made, finished=finished, fail_start=False, fail_write=False)
    monkeypatch.setattr(app, "talk_transcoder",
                        lambda fmt: FakeTranscoder(fmt, made, opts.fail_start, opts.fail_write))
    monkeypatch.setattr(app, "talk_available", lambda: True)
    for name, value in {"TALK_TICK": 0.02, "TALK_POLL": 0.01, "TALK_CHIME_WAIT": 0.1, "TALK_END_WAIT": 0.5,
                        "TALK_SPEAKER_WAIT": 2.0, "RESUME_REWIND": 1.0}.items():
        monkeypatch.setattr(app, name, value)

    async def finish(session):
        finished.append(session)

    monkeypatch.setattr(app, "talk_finish_on_speaker", finish)
    monkeypatch.setattr(app, "_talk", None)
    monkeypatch.setattr(app, "_talk_last", None)
    monkeypatch.setattr(app, "_talk_on_speaker", None)
    return opts


def start(ws, **extra):
    ws.send_json({"type": "start", "mime": WEBM, **extra})
    return ws.receive_json()


def until(ws, kind):
    """Messages up to and including the first of `kind`."""
    seen = []
    while not seen or seen[-1]["type"] != kind:
        seen.append(ws.receive_json())
    return seen


def refused(ws):
    error = ws.receive_json()
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    return error, closed.value.code


def actions(client):
    return [(e["actor"], e["action"], e["detail"]) for e in client.get("/activity").json()]


# --- Building blocks ---

@pytest.mark.parametrize(("mime", "fmt"), [
    ("audio/webm;codecs=opus", "webm"), ("audio/webm", "webm"), ("video/webm;codecs=opus", "webm"),
    ("audio/mp4", "mp4"), ("audio/mp4;codecs=mp4a.40.2", "mp4"), ("AUDIO/OGG; codecs=opus", "ogg"),
    ("audio/wav", None), ("", None), (None, None),
])
def test_input_format(mime, fmt):
    assert talk.input_format(mime) == fmt


def test_ffmpeg_command_reads_stdin_and_writes_mp3():
    cmd = talk.ffmpeg_command("mp4")
    assert cmd[cmd.index("-f") + 1] == "mp4" and cmd[cmd.index("-i") + 1] == "pipe:0"
    assert cmd[-2:] == ["mp3", "pipe:1"] and "libmp3lame" in cmd


def test_chime_is_a_short_wav():
    for tone in ("start", "end"):
        with wave.open(BytesIO(talk.chime_wav(tone))) as w:
            assert w.getnchannels() == 1 and 0.5 < w.getnframes() / w.getframerate() < 1.0
    assert talk.chime_wav("start") != talk.chime_wav("end")


def test_format_seconds():
    assert [talk.format_seconds(s) for s in (0, 4.6, 75.4, 600)] == ["0:00", "0:05", "1:15", "10:00"]


def test_live_stream_backlog_and_close():
    async def run():
        stream = talk.LiveStream(backlog=4)
        await stream.append(b"0123456789")
        got = []

        async def listen():
            async for chunk in stream.follow():
                got.append(chunk)

        listener = asyncio.create_task(listen())
        await asyncio.sleep(0)
        await stream.append(b"ab")
        await asyncio.sleep(0)
        await stream.close()
        await asyncio.wait_for(listener, 1)
        late = [c async for c in stream.follow()]  # after the end: the backlog, then done
        return b"".join(got), late, stream.listeners

    data, late, listeners = asyncio.run(run())
    assert data == b"6789ab" and late == [b"89ab"] and listeners == 2


# --- Stub ffmpeg (a real subprocess, no audio) ---

def stub_ffmpeg(tmp_path, monkeypatch, body):
    path = tmp_path / "ffmpeg"
    path.write_text(f"#!{sys.executable}\nimport sys, time\n{body}\n")
    path.chmod(0o755)
    monkeypatch.setattr(talk, "FFMPEG", str(path))
    return path


CAT = """
while chunk := sys.stdin.buffer.read1(4096):
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
"""


def test_stub_ffmpeg_passes_data_and_exits(tmp_path, monkeypatch):
    stub_ffmpeg(tmp_path, monkeypatch, CAT)

    async def run():
        t = talk.FfmpegTranscoder("webm")
        await t.start()
        await t.write(b"hello")
        first = await t.read()
        await t.finish(timeout=5)
        rest = await t.read()
        return first, rest, t.proc.returncode

    assert asyncio.run(run()) == (b"hello", b"", 0)


def test_stuck_ffmpeg_is_killed(tmp_path, monkeypatch):
    stub_ffmpeg(tmp_path, monkeypatch, "sys.stderr.write('stuck\\n'); sys.stderr.flush(); time.sleep(60)")

    async def run():
        t = talk.FfmpegTranscoder("webm")
        await t.start()
        await asyncio.sleep(0.2)
        await t.finish(timeout=0.3)
        return t.proc.returncode, t.errors

    returncode, errors = asyncio.run(run())
    assert returncode is not None and returncode < 0 and errors == "stuck"


def test_ffmpeg_that_exits_early_fails_writes(tmp_path, monkeypatch):
    stub_ffmpeg(tmp_path, monkeypatch, "sys.stderr.write('Invalid data\\n'); sys.exit(1)")

    async def run():
        t = talk.FfmpegTranscoder("mp4")
        await t.start()
        await t.proc.wait()
        await asyncio.sleep(0.1)  # let the stderr reader catch up
        with pytest.raises(talk.TranscoderError, match="Invalid data"):
            await t.write(b"x")
        await t.finish(timeout=1)

    asyncio.run(run())


def test_missing_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(talk, "FFMPEG", str(tmp_path / "nope"))
    assert not talk.ffmpeg_available()
    with pytest.raises(talk.TranscoderError, match="Can't start ffmpeg"):
        asyncio.run(talk.FfmpegTranscoder("webm").start())


# --- WebSocket protocol ---

def test_talk_happy_path(as_role, client, anon, app, fake_speaker, talking):
    op = as_role("operator")
    with op.websocket_connect("/talk") as ws:
        ready = start(ws, volume=0.5)
        assert ready["type"] == "ready" and ready["max_seconds"] == 120 and ready["format"] == "audio/mpeg"
        assert until(ws, "live")[-1] == {"type": "live"}
        load = fake_speaker.media_controller.loads[-1]
        assert load["url"].startswith(f"{BASE}/talk/{ready['id']}/live?") and load["stream_type"] == "LIVE"
        assert load["content_type"] == "audio/mpeg" and load["title"] == "Live: Operator-User"
        assert fake_speaker.volume == 0.5
        assert client.get("/status").json()["talking"] == "Operator-User"
        assert op.get("/talk/status").json()["active"] == {"by": "Operator-User", "id": ready["id"]}
        ws.send_bytes(b"one")
        ws.send_bytes(b"two")
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        ws.send_json({"type": "stop"})
        ended = ws.receive_json()
        assert ended["type"] == "ended" and ended["reason"] == "stopped" and ended["seconds"] >= 0
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000

    t = talking.made[0]
    assert t.fmt == "webm" and t.written == [b"one", b"two"] and t.finished
    assert app._talk is None and [s.id for s in talking.finished] == [ready["id"]]
    live = anon.get(path_of(load["url"]))
    assert live.content == b"MP3:oneMP3:two" and live.headers["content-type"] == "audio/mpeg"
    assert anon.get(f"/talk/{ready['id']}/live").status_code == 403
    assert anon.get(path_of(app.media_url("/talk/other/live"))).status_code == 404
    assert actions(client)[0] == ("Operator-User", "talk", "Talked live for 0:00")
    assert op.get("/talk/status").json() == {"available": True, "max_seconds": 120, "active": None}


def test_safari_mp4_and_api_token(client, talking):
    with client.websocket_connect("/talk") as ws:
        assert start(ws, mime="audio/mp4")["type"] == "ready"
        ws.send_json({"type": "stop"})
        assert until(ws, "ended")[-1]["reason"] == "stopped"
    assert talking.made[0].fmt == "mp4"


def test_ended_stream_expires(client, anon, app, fake_speaker, talking, monkeypatch):
    with client.websocket_connect("/talk") as ws:
        start(ws)
        until(ws, "live")
        ws.send_json({"type": "stop"})
        until(ws, "ended")
    url = fake_speaker.media_controller.loads[-1]["url"]
    monkeypatch.setattr(app, "TALK_GRACE", 0)
    assert anon.get(path_of(url)).status_code == 404


@pytest.mark.parametrize(("who", "headers", "code", "close"), [
    ("anon", {}, "unauthorized", 4401),
    ("viewer", {}, "forbidden", 4403),
    ("operator", {"origin": "https://evil.example.com"}, "forbidden", 4403),
    ("anon", {"authorization": "Bearer wrong"}, "unauthorized", 4401),
])
def test_refused_callers(who, headers, code, close, anon, as_role, fake_speaker, talking):
    c = anon if who == "anon" else as_role(who)
    with c.websocket_connect("/talk", headers=headers) as ws:
        error, closed = refused(ws)
    assert error["type"] == "error" and error["code"] == code and closed == close
    assert talking.made == [] and fake_speaker.media_controller.loads == []


def test_same_origin_is_fine(as_role, talking):
    with as_role("operator").websocket_connect("/talk", headers={"origin": "http://testserver"}) as ws:
        assert start(ws)["type"] == "ready"
        ws.send_json({"type": "stop"})
        until(ws, "ended")


@pytest.mark.parametrize(("first", "detail"), [
    (b"\x1aE\xdf\xa3", "start message"),
    ("not json", "not JSON"),
    ({"type": "hello"}, "first message"),
    ({"type": "start", "mime": "audio/wav"}, "Unsupported recording format"),
    ({"type": "start", "mime": WEBM, "volume": 5}, "volume"),
])
def test_bad_start(first, detail, client, talking):
    with client.websocket_connect("/talk") as ws:
        if isinstance(first, bytes):
            ws.send_bytes(first)
        elif isinstance(first, str):
            ws.send_text(first)
        else:
            ws.send_json(first)
        error, closed = refused(ws)
    assert error["code"] == "bad_request" and detail in error["detail"] and closed == 4400
    assert talking.made == []


def test_start_timeout(client, app, talking, monkeypatch):
    monkeypatch.setattr(app, "TALK_START_TIMEOUT", 0.05)
    with client.websocket_connect("/talk") as ws:
        error, closed = refused(ws)
    assert error["code"] == "bad_request" and closed == 4400


def test_without_ffmpeg(client, app, talking, monkeypatch):
    monkeypatch.setattr(app, "talk_available", lambda: False)
    with client.websocket_connect("/talk") as ws:
        ws.send_json({"type": "start", "mime": WEBM})
        error, closed = refused(ws)
    assert error["code"] == "unavailable" and "ffmpeg" in error["detail"] and closed == 4503
    assert client.get("/talk/status").json()["available"] is False


def test_one_talker_at_a_time(as_role, talking):
    first, second = as_role("operator", "alice"), as_role("admin", "bob")
    with first.websocket_connect("/talk") as a:
        assert start(a)["type"] == "ready"
        with second.websocket_connect("/talk") as b:
            b.send_json({"type": "start", "mime": WEBM})
            error, closed = refused(b)
        assert error == {"type": "error", "code": "busy", "detail": "Alice is talking right now"}
        assert closed == 4409
        a.send_json({"type": "stop"})
        until(a, "ended")
    assert len(talking.made) == 1


def test_max_length(client, app, talking):
    app.settings.talk_max_seconds = 0.2  # below the setting's minimum, to keep the test fast
    with client.websocket_connect("/talk") as ws:
        start(ws)
        ws.send_bytes(b"x")
        ended = until(ws, "ended")[-1]
    assert ended["reason"] == "max_length" and talking.made[0].finished
    assert actions(client)[0] == ("api-token", "talk", "Talked live for 0:00 (max length)")


def test_idle_timeout(client, app, talking, monkeypatch):
    monkeypatch.setattr(app, "TALK_IDLE_TIMEOUT", 0.1)
    with client.websocket_connect("/talk") as ws:
        start(ws)
        assert until(ws, "ended")[-1]["reason"] == "idle"


def test_too_much_data(client, app, talking, monkeypatch):
    monkeypatch.setattr(app, "TALK_MAX_RATE", 1)  # 120 bytes for a 120 s talk
    with client.websocket_connect("/talk") as ws:
        start(ws)
        ws.send_bytes(b"x" * 200)
        assert until(ws, "ended")[-1]["reason"] == "too_large"


def test_disconnect_cleans_up(client, app, talking):
    with client.websocket_connect("/talk") as ws:
        start(ws)
        until(ws, "live")
        ws.send_bytes(b"x")
        ws.close()
        for _ in range(200):  # the server notices on its own; leaving the block would cancel it
            if talking.finished:
                break
            time.sleep(0.01)
    assert app._talk is None and talking.made[0].finished and len(talking.finished) == 1
    assert actions(client)[0][2] == "Talked live for 0:00"


def test_speaker_error_ends_the_talk(client, app, talking, monkeypatch):
    def unreachable():
        raise OSError("down")

    monkeypatch.setattr(app.transport, "get_cast", unreachable)
    with client.websocket_connect("/talk") as ws:
        start(ws)
        ended = until(ws, "ended")[-1]
    assert ended["reason"] == "speaker_error" and "not responding" in ended["detail"]
    assert talking.made[0].finished and talking.finished == [] and app._talk_on_speaker is None


def test_transcoder_failures(client, app, talking):
    talking.fail_start = True
    with client.websocket_connect("/talk") as ws:
        ws.send_json({"type": "start", "mime": WEBM})
        ended = until(ws, "ended")[-1]
    assert ended["reason"] == "transcoder_error" and "Can't start ffmpeg" in ended["detail"]
    assert app._talk is None and not any(a[1] == "talk" for a in actions(client))

    talking.fail_start, talking.fail_write = False, True
    with client.websocket_connect("/talk") as ws:
        start(ws)
        ws.send_bytes(b"garbage")
        ended = until(ws, "ended")[-1]
    assert ended["reason"] == "transcoder_error" and "Invalid data" in ended["detail"]
    assert talking.made[-1].finished


def test_something_else_playing_interrupts(client, app, talking):
    with client.websocket_connect("/talk") as ws:
        start(ws)
        until(ws, "live")
        client.post("/stop")
        assert until(ws, "ended")[-1]["reason"] == "interrupted"
    assert talking.finished == []  # the speaker belongs to whatever took over


def test_opening_chime(client, anon, app, fake_speaker, talking):
    with client.websocket_connect("/talk") as ws:
        start(ws, chime=True)
        until(ws, "live")
        ws.send_json({"type": "stop"})
        until(ws, "ended")
    chime, live = fake_speaker.media_controller.loads[-2:]
    assert chime["url"].startswith(f"{BASE}/talk/chime.wav?") and "tone=start" in chime["url"]
    assert chime["content_type"] == "audio/wav" and live["stream_type"] == "LIVE"
    wav = anon.get(path_of(chime["url"]))
    assert wav.content.startswith(b"RIFF") and wav.headers["content-type"] == "audio/wav"


def test_stub_ffmpeg_end_to_end(client, anon, app, fake_speaker, talking, tmp_path, monkeypatch):
    stub_ffmpeg(tmp_path, monkeypatch, CAT)
    made = []

    def real(fmt):
        made.append(talk.FfmpegTranscoder(fmt))
        return made[-1]

    monkeypatch.setattr(app, "talk_transcoder", real)
    with client.websocket_connect("/talk") as ws:
        start(ws)
        until(ws, "live")
        for i in range(3):
            ws.send_bytes(f"chunk{i};".encode())
        ws.send_json({"type": "stop"})
        until(ws, "ended")
    assert made[0].proc.returncode == 0  # ffmpeg exited; nothing left running
    assert anon.get(path_of(fake_speaker.media_controller.loads[-1]["url"])).content == b"chunk0;chunk1;chunk2;"


def test_shutdown_kills_a_running_talk(app, monkeypatch):
    from fastapi.testclient import TestClient

    killed = []
    monkeypatch.setattr(app, "_talk", SimpleNamespace(transcoder=SimpleNamespace(kill=lambda: killed.append(1))))
    monkeypatch.setattr(app, "schedule_loop", asyncio.Event().wait)
    with TestClient(app.app):
        pass
    assert killed == [1]


# --- Speaker hand-over: pause, chime, resume ---

def test_music_resumes_after_the_talk(app, fake_speaker, monkeypatch):
    for name, value in {"TALK_POLL": 0.01, "TALK_CHIME_WAIT": 0.05, "TALK_END_WAIT": 1.0}.items():
        monkeypatch.setattr(app, name, value)
    mc = fake_speaker.media_controller
    mc.play_media(f"{BASE}/yt/aaaaaaaaaaa.m4a", "audio/mp4", title="Song")
    mc.status.adjusted_current_time = 40.0
    session = app.TalkSession("t1", app.Principal("operator", "Op"), True, None, None,
                              app.media_url("/talk/t1/live"))

    async def flow():
        sent = []

        async def send(message):
            sent.append(message)

        app._talk_on_speaker = session
        await app.talk_start_speaker(session, send)
        assert sent == [{"type": "live"}] and app._resume["title"] == "Song"
        assert [lo["url"].split("?")[0] for lo in mc.loads[-2:]] == [f"{BASE}/talk/chime.wav", f"{BASE}/talk/t1/live"]
        mc.finish()  # the speaker has played out the live stream
        finishing = asyncio.create_task(app.talk_finish_on_speaker(session))
        while "tone=end" not in mc.loads[-1]["url"]:
            await asyncio.sleep(0.01)
        mc.finish()  # closing chime done
        await asyncio.wait_for(finishing, 5)

    asyncio.run(flow())
    resumed = mc.loads[-1]
    assert resumed["url"] == f"{BASE}/yt/aaaaaaaaaaa.m4a" and resumed["current_time"] == 39.0
    assert app._resume is None and app._talk_on_speaker is None


def test_queue_waits_for_the_talk_then_moves_on(client, app, fake_speaker):
    pl = app.db.create_playlist("Mix")
    for name in ("a", "b"):
        app.db.add_item(pl["id"], {"kind": "url", "title": name, "source": f"https://x.example.com/{name}.mp3"}, 10)
    client.post(f"/playlists/{pl['id']}/play", json={})
    app._queue.after_say = True
    talk_url = app.media_url("/talk/t1/live")
    fake_speaker.media_controller.play_media(talk_url, "audio/mpeg")
    fake_speaker.media_controller.finish()
    app._talk_on_speaker = object()
    asyncio.run(app.queue_tick())
    assert fake_speaker.media_controller.loads[-1]["url"] == talk_url  # still the talk's
    app._talk_on_speaker = None
    asyncio.run(app.queue_tick())
    assert fake_speaker.media_controller.loads[-1]["url"] == "https://x.example.com/b.mp3"
