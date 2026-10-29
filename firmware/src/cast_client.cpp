#include "cast_client.h"

static const char* NS_CONNECTION = "urn:x-cast:com.google.cast.tp.connection";
static const char* NS_HEARTBEAT = "urn:x-cast:com.google.cast.tp.heartbeat";
static const char* NS_RECEIVER = "urn:x-cast:com.google.cast.receiver";
static const char* NS_MEDIA = "urn:x-cast:com.google.cast.media";
static const char* SENDER_ID = "sender-0";
static const char* RECEIVER_ID = "receiver-0";
static const char* DEFAULT_MEDIA_RECEIVER = "CC1AD845";

static const uint32_t kHeartbeatMs = 5000;
static const uint32_t kDeadAfterMs = 20000;  // no frames (not even PONG) for this long = gone

bool CastClient::begin(IPAddress ip, String& err, uint16_t port) {
    if (connected() && ip == ip_ && port == port_) return true;
    end();
    ip_ = ip;
    port_ = port;
    tls_.setInsecure();  // Cast devices present a self-signed certificate; this link stays on the LAN
#if defined(ESP32)
    tls_.setHandshakeTimeout(8);
    tls_.setTimeout(3);  // seconds on arduino-esp32 (WiFiClient overrides Stream's milliseconds)
#else
    // BearSSL must buffer a whole TLS record: 16 KB unless the speaker accepts smaller records.
    if (SecureClient::probeMaxFragmentLength(ip, port, 1024))
        tls_.setBufferSizes(1024, 1024);
    else
        tls_.setBufferSizes(16384 + 325, 1024);
    tls_.setTimeout(3000);  // Stream timeout: milliseconds on ESP8266
#endif
    if (!tls_.connect(ip, port)) {
        err = "can't reach speaker at " + ip.toString();
        return false;
    }
    lastRx_ = lastPing_ = millis();
    JsonDocument doc;
    doc["type"] = "CONNECT";
    send(RECEIVER_ID, NS_CONNECTION, doc);
    return refresh(err);
}

void CastClient::end() {
    if (tls_.connected()) tls_.stop();
    appId_ = appName_ = transportId_ = sessionId_ = connectedTransport_ = "";
    mediaSessionId_ = 0;
    playerState_ = "";
}

bool CastClient::connected() { return tls_.connected(); }

bool CastClient::send(const char* dest, const char* ns, JsonDocument& doc) {
    castmsg::Message m;
    m.source = SENDER_ID;
    m.destination = dest;
    m.ns = ns;
    serializeJson(doc, m.payload);
    std::string frame = castmsg::encode(m);
    return tls_.write(reinterpret_cast<const uint8_t*>(frame.data()), frame.size()) == frame.size();
}

bool CastClient::readFrame(castmsg::Message& m, uint32_t timeoutMs) {
    uint32_t start = millis();
    // available() counts only the current TLS record, so wait for any byte and let readBytes
    // (3 s timeout) collect the rest of the header even if it straddles two records.
    while (tls_.available() <= 0) {
        if (!tls_.connected() || millis() - start > timeoutMs) return false;
        delay(2);
    }
    uint8_t header[4];
    if (tls_.readBytes(header, 4) != 4) return false;
    uint32_t len = castmsg::frameLength(header);
    if (len == 0 || len > castmsg::kMaxBody) {
        end();  // out of sync; start over on the next command
        return false;
    }
    std::string body(len, '\0');
    size_t got = 0;
    while (got < len) {
        size_t n = tls_.readBytes(reinterpret_cast<uint8_t*>(&body[got]), len - got);
        if (n == 0) {
            end();
            return false;
        }
        got += n;
    }
    return castmsg::decodeBody(reinterpret_cast<const uint8_t*>(body.data()), body.size(), m);
}

void CastClient::handle(const castmsg::Message& m) {
    lastRx_ = millis();
    JsonDocument doc;
    if (deserializeJson(doc, m.payload)) return;
    String type = doc["type"] | "";

    if (type == "PING") {
        JsonDocument pong;
        pong["type"] = "PONG";
        send(m.source.c_str(), NS_HEARTBEAT, pong);
        return;
    }
    if (type == "CLOSE" && m.source == connectedTransport_.c_str()) {
        connectedTransport_ = "";
        return;
    }
    if (type == "RECEIVER_STATUS") {
        JsonVariantConst st = doc["status"];
        if (!st["volume"]["level"].isNull()) volume_ = st["volume"]["level"].as<float>();
        muted_ = st["volume"]["muted"] | false;
        JsonArrayConst apps = st["applications"].as<JsonArrayConst>();
        if (apps.size()) {
            String newApp = apps[0]["appId"] | "";
            if (newApp != appId_) mediaSessionId_ = 0;
            appId_ = newApp;
            appName_ = apps[0]["displayName"] | "";
            transportId_ = apps[0]["transportId"] | "";
            sessionId_ = apps[0]["sessionId"] | "";
        } else {
            appId_ = appName_ = transportId_ = sessionId_ = connectedTransport_ = "";
            mediaSessionId_ = 0;
            playerState_ = "";
        }
    } else if (type == "MEDIA_STATUS") {
        JsonArrayConst list = doc["status"].as<JsonArrayConst>();
        if (!list.size()) {
            mediaSessionId_ = 0;  // the session ended
            playerState_ = "IDLE";
        } else {
            JsonVariantConst s = list[0];
            mediaSessionId_ = s["mediaSessionId"] | mediaSessionId_;
            playerState_ = s["playerState"] | playerState_.c_str();
            idleReason_ = s["idleReason"] | "";
            if (!s["currentTime"].isNull()) {
                position_ = s["currentTime"].as<float>();
                positionAt_ = millis();
            }
            if (!s["media"].isNull()) {
                contentId_ = s["media"]["contentId"] | contentId_.c_str();
                title_ = s["media"]["metadata"]["title"] | title_.c_str();
            }
        }
    }
    uint32_t id = doc["requestId"] | 0;
    if (id) {
        replyId_ = id;
        replyType_ = type;
    }
}

bool CastClient::waitFor(const std::function<bool()>& done, uint32_t timeoutMs) {
    uint32_t start = millis();
    castmsg::Message m;
    while (!done()) {
        uint32_t elapsed = millis() - start;
        if (elapsed >= timeoutMs || !tls_.connected()) return false;
        if (readFrame(m, timeoutMs - elapsed)) handle(m);
    }
    return true;
}

bool CastClient::request(const char* dest, const char* ns, JsonDocument& doc, uint32_t timeoutMs, String& err) {
    uint32_t id = nextId_++;
    doc["requestId"] = id;
    if (!send(dest, ns, doc)) {
        end();
        err = "lost connection to speaker";
        return false;
    }
    if (!waitFor([&] { return replyId_ == id; }, timeoutMs)) {
        err = String("speaker did not answer ") + (doc["type"] | "request");
        return false;
    }
    if (replyType_ == "LOAD_FAILED" || replyType_ == "LOAD_CANCELLED" || replyType_ == "INVALID_REQUEST" ||
        replyType_ == "LAUNCH_ERROR") {
        err = "speaker replied " + replyType_;
        return false;
    }
    return true;
}

bool CastClient::refresh(String& err) {
    JsonDocument doc;
    doc["type"] = "GET_STATUS";
    if (!request(RECEIVER_ID, NS_RECEIVER, doc, 5000, err)) return false;
    if (appId_ != DEFAULT_MEDIA_RECEIVER || !transportId_.length()) return true;
    if (!ensureMediaApp(err)) return false;
    JsonDocument media;
    media["type"] = "GET_STATUS";
    return request(transportId_.c_str(), NS_MEDIA, media, 5000, err);
}

bool CastClient::ensureMediaApp(String& err) {
    if (appId_ != DEFAULT_MEDIA_RECEIVER || !transportId_.length()) {
        JsonDocument doc;
        doc["type"] = "LAUNCH";
        doc["appId"] = DEFAULT_MEDIA_RECEIVER;
        if (!request(RECEIVER_ID, NS_RECEIVER, doc, 10000, err)) return false;
        // The LAUNCH reply can arrive before the app is up; wait for its transport.
        if (!waitFor([&] { return appId_ == DEFAULT_MEDIA_RECEIVER && transportId_.length(); }, 10000)) {
            err = "Default Media Receiver did not start";
            return false;
        }
    }
    if (connectedTransport_ != transportId_) {
        JsonDocument doc;
        doc["type"] = "CONNECT";
        if (!send(transportId_.c_str(), NS_CONNECTION, doc)) {
            err = "lost connection to speaker";
            return false;
        }
        connectedTransport_ = transportId_;
    }
    return true;
}

bool CastClient::ensureMediaSession(String& err) {
    // Only play() may launch the Default Media Receiver; launching here would kill e.g. Spotify.
    if (appId_ != DEFAULT_MEDIA_RECEIVER) {
        err = appName_.length() ? "the speaker is playing " + appName_ + ", not media from this relay"
                                : "nothing is playing";
        return false;
    }
    if (!ensureMediaApp(err)) return false;
    if (mediaSessionId_) return true;
    JsonDocument doc;
    doc["type"] = "GET_STATUS";
    if (!request(transportId_.c_str(), NS_MEDIA, doc, 5000, err)) return false;
    if (!mediaSessionId_) {
        err = "nothing is playing";
        return false;
    }
    return true;
}

bool CastClient::play(const String& url, const String& contentType, const String& title, float position,
                      String& err) {
    if (!ensureMediaApp(err)) return false;
    JsonDocument doc;
    doc["type"] = "LOAD";
    doc["sessionId"] = sessionId_;
    doc["autoplay"] = true;
    if (position > 0) doc["currentTime"] = position;
    JsonObject media = doc["media"].to<JsonObject>();
    media["contentId"] = url;
    media["contentType"] = contentType;
    media["streamType"] = "BUFFERED";  // not LIVE, so currentTime and seeking work
    JsonObject meta = media["metadata"].to<JsonObject>();
    meta["metadataType"] = 0;
    meta["title"] = title;
    return request(transportId_.c_str(), NS_MEDIA, doc, 15000, err);
}

bool CastClient::setVolume(float level, String& err) {
    JsonDocument doc;
    doc["type"] = "SET_VOLUME";
    doc["volume"]["level"] = constrain(level, 0.0f, 1.0f);
    return request(RECEIVER_ID, NS_RECEIVER, doc, 5000, err);
}

bool CastClient::stop(String& err) {
    if (!sessionId_.length()) return true;
    JsonDocument doc;
    doc["type"] = "STOP";
    doc["sessionId"] = sessionId_;
    return request(RECEIVER_ID, NS_RECEIVER, doc, 5000, err);
}

bool CastClient::pause(String& err) {
    if (!ensureMediaSession(err)) return false;
    JsonDocument doc;
    doc["type"] = "PAUSE";
    doc["mediaSessionId"] = mediaSessionId_;
    return request(transportId_.c_str(), NS_MEDIA, doc, 5000, err);
}

bool CastClient::resume(String& err) {
    if (!ensureMediaSession(err)) return false;
    JsonDocument doc;
    doc["type"] = "PLAY";
    doc["mediaSessionId"] = mediaSessionId_;
    return request(transportId_.c_str(), NS_MEDIA, doc, 5000, err);
}

void CastClient::loop() {
    if (!tls_.connected()) return;
    castmsg::Message m;
    while (tls_.available() > 0) {
        if (!readFrame(m, 1000)) break;
        handle(m);
    }
    uint32_t now = millis();
    if (now - lastRx_ > kDeadAfterMs) {
        end();
        return;
    }
    if (now - lastPing_ > kHeartbeatMs) {
        lastPing_ = now;
        JsonDocument doc;
        doc["type"] = "PING";
        send(RECEIVER_ID, NS_HEARTBEAT, doc);
    }
}

void CastClient::status(JsonObject out) const {
    out["connected"] = const_cast<SecureClient&>(tls_).connected() != 0;
    out["ip"] = ip_.toString();
    out["app"] = appName_;
    if (volume_ >= 0) out["volume"] = volume_;
    out["muted"] = muted_;
    JsonObject media = out["media"].to<JsonObject>();
    media["title"] = title_;
    media["state"] = playerState_;
    if (idleReason_.length()) media["idle_reason"] = idleReason_;
    float pos = position_;
    if (playerState_ == "PLAYING") pos += (millis() - positionAt_) / 1000.0f;
    media["position"] = pos;
    media["content_id"] = contentId_;
}
