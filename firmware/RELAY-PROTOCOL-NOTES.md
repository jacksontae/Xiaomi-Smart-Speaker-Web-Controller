# Relay protocol: gaps seen from the server side (proposals)

The server's `MqttRelayTransport` (transport.py) works with the firmware as it is. These changes would
make it cheaper and more precise. None is required for the current server code.

## What the server relies on today

- `<base>/cmd` with `"id"`, answered on `<base>/result` with the same `id`, `ok`, `error` and `speaker`.
- `<base>/online`: retained `true`, last will `false` (QoS 1). Good: no server-side change needed.
- `<base>/status`: retained, every 30 s, with `version`. The server also treats 90 s without any
  message as offline, because a last will only fires after the broker's keepalive timeout (~90 s at
  keepalive 60) and a hung relay that still holds its TCP session never triggers it.

## Gaps and proposed firmware changes

1. **No status push on media changes.** Status is only published every 30 s, so the server has to poll
   with `{"cmd":"status"}` every ~2 s while the queue or an announcement-resume is waiting for a track
   to end (each poll is also a GET_STATUS to the speaker).
   *Proposal:* publish `<base>/status` (non-retained, or retained but rate-limited to 1 per second)
   whenever `CastClient::handle()` sees a MEDIA_STATUS that changes `state`, `idle_reason` or
   `content_id`. The server would then only need a slow safety poll.
2. **`content_type` and `duration` are not reported.** `CastClient::status()` drops them. The server
   remembers the content type of URLs it loaded itself (needed to resume a track), and `/status` shows
   no duration in relay mode.
   *Proposal:* keep `media.contentType` and `media.duration` from MEDIA_STATUS and add
   `content_type` and `duration` to the `media` object.
3. **Retained status has no age.** On (re)connect the server receives an old retained status and can't
   tell how old it is, so it ignores it for freshness and asks again.
   *Proposal:* add `"uptime": millis()/1000` and a `"seq"` counter to the status payload.
4. **Commands block the MQTT loop.** A cold `play` can block ~40 s (see `setKeepAlive(60)` in main.cpp);
   meanwhile no other command or status is processed. The server uses a 45 s timeout for `play` and
   10 s for others and holds its own lock, so commands are never sent concurrently.
   *Proposal (later):* acknowledge immediately (`"accepted": true`) and publish the final result when
   the LOAD reply arrives.
5. **`status` result lacks relay info.** Only the periodic status carries `version`/`rssi`.
   *Proposal:* include `version` in every result (cheap, lets the server show it right after boot).
6. **No protocol version.** *Proposal:* add `"proto": 1` to status so the server can adapt if the JSON
   shape changes.
