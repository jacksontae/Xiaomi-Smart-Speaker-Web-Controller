// Minimal Cast v2 sender: keeps one TLS connection to the speaker, launches the
// Default Media Receiver and loads URLs into it. Same flow as pychromecast in app.py.
#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>

#include <functional>

#include "cast_message.h"

class CastClient {
   public:
    // Connect, or keep the current connection when it already points at ip.
    bool begin(IPAddress ip, String& err, uint16_t port = 8009);
    void end();
    bool connected();
    IPAddress ip() const { return ip_; }

    // Call from loop(): answers PINGs, sends heartbeats, absorbs status updates.
    void loop();

    // position < 0 starts from the beginning.
    bool play(const String& url, const String& contentType, const String& title, float position, String& err);
    bool setVolume(float level, String& err);
    bool stop(String& err);
    bool pause(String& err);
    bool resume(String& err);
    bool refresh(String& err);
    void status(JsonObject out) const;

   private:
    bool send(const char* dest, const char* ns, JsonDocument& doc);
    bool readFrame(castmsg::Message& m, uint32_t timeoutMs);
    void handle(const castmsg::Message& m);
    bool waitFor(const std::function<bool()>& done, uint32_t timeoutMs);
    bool request(const char* dest, const char* ns, JsonDocument& doc, uint32_t timeoutMs, String& err);
    bool ensureMediaApp(String& err);
    bool ensureMediaSession(String& err);

    WiFiClientSecure tls_;
    IPAddress ip_;
    uint16_t port_ = 0;
    uint32_t nextId_ = 1;
    uint32_t lastRx_ = 0;
    uint32_t lastPing_ = 0;

    // Replies to our requests
    uint32_t replyId_ = 0;
    String replyType_;

    // Receiver state
    String appId_;
    String appName_;
    String transportId_;
    String sessionId_;
    String connectedTransport_;
    float volume_ = -1;
    bool muted_ = false;

    // Media state
    int32_t mediaSessionId_ = 0;
    String playerState_;
    String idleReason_;
    String title_;
    String contentId_;
    float position_ = 0;
    uint32_t positionAt_ = 0;
};
