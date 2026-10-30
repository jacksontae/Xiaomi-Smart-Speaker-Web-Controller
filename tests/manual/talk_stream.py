"""Manual check for live talk: stream a local audio file through WebSocket /talk as if it were a microphone.

Not collected by pytest. Run it against a local test server (never someone's real speaker unless you mean to):

    python tests/manual/talk_stream.py --url ws://127.0.0.1:8105/talk --token change-me --file clip.webm

The file is sent in chunks at roughly real-time pace, like MediaRecorder with a 250 ms timeslice.
Use a recording the browser would produce: WebM/Opus (Chrome, Firefox), Ogg/Opus, or fragmented MP4/AAC
(Safari). Every server message is printed. Needs the `websockets` package (in requirements.txt).
"""
import argparse
import json
import os
import threading
import time
from pathlib import Path

from websockets.sync.client import connect

MIMES = {".webm": "audio/webm;codecs=opus", ".ogg": "audio/ogg;codecs=opus", ".opus": "audio/ogg;codecs=opus",
         ".m4a": "audio/mp4", ".mp4": "audio/mp4"}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="ws://127.0.0.1:8105/talk")
    parser.add_argument("--token", default=os.environ.get("SPEAKER_TOKEN"), help="API token (or $SPEAKER_TOKEN)")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--mime", help="MediaRecorder MIME type; guessed from the file extension")
    parser.add_argument("--chunk", type=int, default=4000, help="bytes per chunk (default 4000 = 128 kbit/s)")
    parser.add_argument("--interval", type=float, default=0.25, help="seconds between chunks")
    parser.add_argument("--chime", action="store_true")
    parser.add_argument("--volume", type=float)
    args = parser.parse_args()
    if not args.token:
        parser.error("--token or $SPEAKER_TOKEN is required")
    mime = args.mime or MIMES.get(args.file.suffix.lower())
    if not mime:
        parser.error("can't guess the MIME type; pass --mime")
    data = args.file.read_bytes()

    with connect(args.url, additional_headers={"Authorization": f"Bearer {args.token}"}) as ws:
        ws.send(json.dumps({"type": "start", "mime": mime, "chime": args.chime, "volume": args.volume}))
        first = json.loads(ws.recv())
        print("<-", first)
        if first["type"] != "ready":
            return
        done = threading.Event()

        def listen():
            try:
                for message in ws:
                    print("<-", message)
            finally:
                done.set()

        threading.Thread(target=listen, daemon=True).start()
        started = time.monotonic()
        for offset in range(0, len(data), args.chunk):
            if done.is_set():
                break
            ws.send(data[offset:offset + args.chunk])
            time.sleep(args.interval)
        print(f"-> sent {len(data)} bytes in {time.monotonic() - started:.1f} s; stopping")
        if not done.is_set():
            ws.send(json.dumps({"type": "stop"}))
        done.wait(10)


if __name__ == "__main__":
    main()
