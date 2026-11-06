// Minimal Cast v2 sender: keeps one TLS connection to the speaker, launches the
// Default Media Receiver and loads URLs into it. Same flow as pychromecast in server/transport.py.
#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

#include <functional>

#include "cast_message.h"
#include "platform.h"
#include "play_job.h"

class CastClient {
   public:
    // Connect, or keep the current connection when it already points at ip.
    bool begin(IPAddress ip, String& err, uint16_t port = 8009);
    void end();
    bool connected();
    IPAddress ip() const { return ip_; }

    // Call from loop(): answers PINGs, sends heartbeats, absorbs status updates, drives a pending play.
    void loop();

    // Starts a play without blocking; loop() drives it (launch the Default Media Receiver if needed, wait for
    // its transport, connect, LOAD) and takePlayResult() reports the outcome. position < 0 starts from the
    // beginning, volume < 0 leaves the volume alone. False (with err) when a play is already pending.
    bool startPlay(const String& url, const String& contentType, const String& title, float position, float volume,
                   String& err);
    bool playPending() const { return job_.active(); }
    // True once, when the started play has finished; ok and err tell how.
    bool takePlayResult(bool& ok, String& err);
    // A pending play ends with err = why at the next loop().
    void cancelPlay(const char* why);
    bool setVolume(float level, String& err);
    bool stop(String& err);
    bool pause(String& err);
    bool resume(String& err);
    bool seek(float position, String& err);
    bool refresh(String& err);
    void status(JsonObject out) const;
    // Bumped whenever the app, player state, idle reason, track or volume changes; lets the
    // caller publish status on change instead of polling.
    uint32_t changes() const { return changes_; }

   private:
    bool send(const char* dest, const char* ns, JsonDocument& doc);
    bool readFrame(castmsg::Message& m, uint32_t timeoutMs);
    void handle(const castmsg::Message& m);
    bool waitFor(const std::function<bool()>& done, uint32_t timeoutMs);
    bool request(const char* dest, const char* ns, JsonDocument& doc, uint32_t timeoutMs, String& err);
    bool ensureMediaApp(String& err);
    bool ensureMediaSession(String& err);
    void drivePlay();
    bool sendJobRequest(const char* dest, const char* ns, JsonDocument& doc);
    bool sendLoad();
    void finishPlay(bool ok, const String& err);

    SecureClient tls_;
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
    String contentType_;
    float duration_ = -1;
    float position_ = 0;
    uint32_t positionAt_ = 0;
    uint32_t changes_ = 0;

    // Pending play; its strings are released when it finishes.
    playjob::Job job_;
    String playUrl_, playType_, playTitle_, cancelWhy_;
    float playPosition_ = -1;
    float playVolume_ = -1;
    uint32_t jobRequestId_ = 0;  // the request the job waits on; its reply is kept apart from request()'s
    bool jobReplied_ = false;
    String jobReplyType_;
    bool resultReady_ = false;
    bool resultOk_ = false;
    String resultErr_;
};
