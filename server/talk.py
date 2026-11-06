"""Building blocks for live talk: browser microphone -> ffmpeg -> an endless MP3 stream the speaker plays.

The browser's MediaRecorder sends chunks of WebM/Opus (Chrome, Firefox), Ogg/Opus (Firefox) or fragmented
MP4/AAC (Safari) over the /talk WebSocket. One ffmpeg process per talk decodes them from stdin and writes
MP3 to stdout; `LiveStream` keeps those bytes and hands them to whoever fetches the live URL (the speaker).
No Cast or FastAPI here; app.py runs the session and drives the speaker.
"""
import asyncio
import io
import math
import os
import shutil
import struct
import wave

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
OUTPUT_BITRATE = 64_000  # bits/s of the MP3 sent to the speaker
BACKLOG_SECONDS = 8  # a listener that connects late starts this far behind the live edge
# MediaRecorder MIME type (before any ";codecs=") -> ffmpeg input format.
INPUT_FORMATS = {
    "audio/webm": "webm",
    "video/webm": "webm",  # some Chrome builds label audio-only recordings this way
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",  # Safari: fragmented MP4 with AAC
    "audio/x-m4a": "mp4",
}


class TranscoderError(Exception):
    """ffmpeg is missing, refused the input or died. str() is shown to the talker."""


def input_format(mime):
    """ffmpeg input format for a MediaRecorder MIME type such as "audio/webm;codecs=opus", or None."""
    return INPUT_FORMATS.get((mime or "").split(";")[0].strip().lower())


def ffmpeg_available():
    return shutil.which(FFMPEG) is not None


def ffmpeg_command(fmt):
    return [
        FFMPEG, "-hide_banner", "-loglevel", "error",
        # Start decoding from the first bytes instead of buffering seconds of input to probe it.
        "-fflags", "+nobuffer", "-probesize", "32768", "-analyzeduration", "0",
        "-f", fmt, "-i", "pipe:0",
        "-vn", "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", str(OUTPUT_BITRATE),
        # No Xing/ID3 headers: they describe a finished file, and this stream never is.
        "-write_xing", "0", "-id3v2_version", "0", "-flush_packets", "1", "-f", "mp3", "pipe:1",
    ]


class FfmpegTranscoder:
    """One ffmpeg process: write() recorder chunks in, read() MP3 out, finish() or kill() to end it."""

    def __init__(self, fmt):
        self.fmt = fmt
        self.proc = None
        self._errors = b""
        self._stderr_task = None

    async def start(self):
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *ffmpeg_command(self.fmt), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            raise TranscoderError(f"Can't start ffmpeg ({e.strerror or e})") from e
        self._stderr_task = asyncio.create_task(self._collect_stderr())

    async def _collect_stderr(self):
        """Keep the tail of ffmpeg's messages; reading them also stops a chatty ffmpeg from blocking."""
        while line := await self.proc.stderr.readline():
            self._errors = (self._errors + line)[-2000:]

    @property
    def errors(self):
        return self._errors.decode("utf-8", "replace").strip()

    async def write(self, data):
        if self.proc.returncode is not None:
            raise TranscoderError(f"ffmpeg stopped: {self.errors or 'exit ' + str(self.proc.returncode)}")
        try:
            self.proc.stdin.write(data)
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            raise TranscoderError(f"ffmpeg stopped: {self.errors or type(e).__name__}") from e

    async def read(self):
        """The next MP3 bytes; b"" once ffmpeg has finished."""
        return await self.proc.stdout.read(4096)

    async def finish(self, timeout):
        """Close ffmpeg's input so it flushes and exits; kill it if it takes longer than `timeout`."""
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except (BrokenPipeError, ConnectionResetError, RuntimeError):
            pass
        try:
            await asyncio.wait_for(self.proc.wait(), timeout)
        except TimeoutError:
            self.kill()
            await self.proc.wait()
        if self._stderr_task is not None:
            await asyncio.wait({self._stderr_task}, timeout=1)

    def kill(self):
        if self.proc is not None and self.proc.returncode is None:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass


class LiveStream:
    """Bytes of one talk's MP3, readable by any number of listeners while they are still being written."""

    def __init__(self, backlog=BACKLOG_SECONDS * OUTPUT_BITRATE // 8):
        self.backlog = backlog
        self.data = bytearray()
        self.closed = False
        self.listeners = 0  # listeners so far (the speaker, maybe twice if it reconnects)
        self._changed = asyncio.Condition()

    async def append(self, chunk):
        async with self._changed:
            self.data += chunk
            self._changed.notify_all()

    async def close(self):
        async with self._changed:
            self.closed = True
            self._changed.notify_all()

    async def follow(self):
        """Yield the stream from up to `backlog` bytes behind the live edge until it is closed."""
        self.listeners += 1
        pos = max(0, len(self.data) - self.backlog)
        while True:
            async with self._changed:
                while len(self.data) <= pos and not self.closed:
                    await self._changed.wait()
                chunk = bytes(self.data[pos:])
            if not chunk:
                return  # closed and fully sent
            pos += len(chunk)
            yield chunk


def chime_wav(tone):
    """A short two-note chime as WAV bytes: rising for "start", falling for "end"."""
    rate, note = 22050, 0.22
    notes = (660.0, 880.0) if tone == "start" else (880.0, 660.0)
    frames = bytearray()
    for i, freq in enumerate(notes):
        for n in range(int(rate * (note if i == 0 else note * 2))):
            t = n / rate
            level = 0.35 * math.exp(-4.0 * t) * min(1.0, n / 200)  # soft attack, bell-like decay
            frames += struct.pack("<h", int(32767 * level * math.sin(2 * math.pi * freq * t)))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return out.getvalue()


def format_seconds(seconds):
    """m:ss for the activity log."""
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"
