// MQTT over WebSocket (ws:// or wss://) for the ESP32, on ESP-IDF's esp-mqtt client. Used when the broker
// setting is a URL, e.g. a self-hosted Mosquitto behind a Cloudflare Tunnel. esp-mqtt runs in its own task and
// reconnects by itself; incoming messages are queued and handed to the callback from loop(), so commands still
// run on the main task next to the Cast client.
#pragma once

#include <Arduino.h>

#include "platform.h"

#if RELAY_HAS_MQTT_TLS

#include <functional>

class WsMqtt {
   public:
    using Handler = std::function<void(const String& topic, const String& payload)>;

    // caPem: PEM bundle to verify wss:// (may hold several certificates); must stay alive while connected.
    bool begin(const String& uri, const String& user, const String& pass, const String& clientId,
               const String& willTopic, const String& subscribeTopic, const char* caPem, Handler onMessage);
    void end();
    bool connected() const { return connected_; }
    // Thread-safe; returns false when not connected or the client refused the message.
    bool publish(const String& topic, const String& payload, bool retained);
    // Delivers queued messages to the handler; call from loop().
    void loop();
    // Set by the event task after (re)connecting; the caller publishes its status and clears it.
    bool takeJustConnected();

   private:
    static void onEvent(void* arg, const char* base, int32_t id, void* data);

    void* client_ = nullptr;  // esp_mqtt_client_handle_t
    void* queue_ = nullptr;   // QueueHandle_t of Incoming*
    Handler handler_;
    String uri_, user_, pass_, clientId_, willTopic_, subscribeTopic_;
    String partTopic_, partBody_;  // a message split over several DATA events
    volatile bool connected_ = false;
    volatile bool justConnected_ = false;
};

#endif
