// Relay settings, stored as /config.json in LittleFS.
#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

struct Config {
    String wifiSsid;
    String wifiPass;
    String deviceName = "speaker-relay";
    String apiToken;     // Bearer token for the HTTP API; generated on first boot
    String speakerHost;  // IP or hostname; empty = discover over mDNS
    String speakerName;  // with discovery: pick this Cast friendly name, empty = first found
    String mqttHost;     // empty = MQTT off
    uint16_t mqttPort = 1883;
    String mqttUser;
    String mqttPass;
    String mqttTopic;  // base topic; empty = "speaker-relay/<deviceName>"
    bool mqttTls = false;

    String baseTopic() const { return mqttTopic.length() ? mqttTopic : "speaker-relay/" + deviceName; }
};

bool loadConfig(Config& c);
bool saveConfig(const Config& c);
void wipeConfig();
String randomToken();

// Copy known fields from JSON into c. Returns false with err set on a bad value.
// Secrets (passwords, token) are only written when present in the input.
bool applyConfig(Config& c, JsonVariantConst in, String& err);

// Settings safe to show over the API: secrets reduced to "set" flags.
void publicConfig(const Config& c, JsonObject out);
