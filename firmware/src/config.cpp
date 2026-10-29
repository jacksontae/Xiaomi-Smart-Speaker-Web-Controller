#include "config.h"

#include <LittleFS.h>

#if defined(ESP32)
#include <esp_random.h>
#endif

static const char* kPath = "/config.json";

bool loadConfig(Config& c) {
    File f = LittleFS.open(kPath, "r");
    if (!f) return false;
    JsonDocument doc;
    DeserializationError e = deserializeJson(doc, f);
    f.close();
    if (e) return false;
    String err;
    return applyConfig(c, doc.as<JsonVariantConst>(), err);
}

bool saveConfig(const Config& c) {
    JsonDocument doc;
    doc["wifi_ssid"] = c.wifiSsid;
    doc["wifi_pass"] = c.wifiPass;
    doc["device_name"] = c.deviceName;
    doc["api_token"] = c.apiToken;
    doc["speaker_host"] = c.speakerHost;
    doc["speaker_name"] = c.speakerName;
    doc["mqtt_host"] = c.mqttHost;
    doc["mqtt_port"] = c.mqttPort;
    doc["mqtt_user"] = c.mqttUser;
    doc["mqtt_pass"] = c.mqttPass;
    doc["mqtt_topic"] = c.mqttTopic;
    doc["mqtt_tls"] = c.mqttTls;
    File f = LittleFS.open(kPath, "w");
    if (!f) return false;
    bool ok = serializeJson(doc, f) > 0;
    f.close();
    return ok;
}

void wipeConfig() { LittleFS.remove(kPath); }

String randomToken() {
    uint8_t buf[24];
#if defined(ESP32)
    esp_fill_random(buf, sizeof(buf));
#else
    for (size_t i = 0; i < sizeof(buf); i += 4) {
        uint32_t r = RANDOM_REG32;  // ESP8266 hardware RNG
        memcpy(buf + i, &r, min(sizeof(r), sizeof(buf) - i));
    }
#endif
    static const char hex[] = "0123456789abcdef";
    String s;
    s.reserve(sizeof(buf) * 2);
    for (uint8_t b : buf) {
        s += hex[b >> 4];
        s += hex[b & 15];
    }
    return s;
}

static bool takeString(JsonVariantConst in, const char* key, String& dst, size_t maxLen, String& err,
                       bool trim = true) {
    JsonVariantConst v = in[key];
    if (v.isNull()) return true;
    if (!v.is<const char*>()) {
        err = String(key) + " must be a string";
        return false;
    }
    String s = v.as<const char*>();
    if (trim) s.trim();  // never for SSIDs and passwords: leading/trailing spaces are legal there
    if (s.length() > maxLen) {
        err = String(key) + " is too long";
        return false;
    }
    dst = s;
    return true;
}

bool applyConfig(Config& c, JsonVariantConst in, String& err) {
    Config next = c;
    bool ok = takeString(in, "wifi_ssid", next.wifiSsid, 32, err, false) &&
              takeString(in, "wifi_pass", next.wifiPass, 64, err, false) &&
              takeString(in, "device_name", next.deviceName, 32, err) &&
              takeString(in, "api_token", next.apiToken, 128, err) &&
              takeString(in, "speaker_host", next.speakerHost, 64, err) &&
              takeString(in, "speaker_name", next.speakerName, 64, err) &&
              takeString(in, "mqtt_host", next.mqttHost, 128, err) &&
              takeString(in, "mqtt_user", next.mqttUser, 64, err) &&
              takeString(in, "mqtt_pass", next.mqttPass, 128, err, false) &&
              takeString(in, "mqtt_topic", next.mqttTopic, 128, err);
    if (!ok) return false;
    if (!in["mqtt_port"].isNull()) {
        long port = in["mqtt_port"].as<long>();
        if (port < 1 || port > 65535) {
            err = "mqtt_port must be 1-65535";
            return false;
        }
        next.mqttPort = static_cast<uint16_t>(port);
    }
    if (!in["mqtt_tls"].isNull()) next.mqttTls = in["mqtt_tls"].as<bool>();
#if defined(ESP8266)
    if (next.mqttTls) {
        err = "MQTT over TLS needs an ESP32 (ESP8266 has RAM for only the speaker's TLS session)";
        return false;
    }
#endif
    if (!next.deviceName.length()) {
        err = "device_name can't be empty";
        return false;
    }
    for (char ch : next.deviceName) {
        if (!isalnum(static_cast<unsigned char>(ch)) && ch != '-') {
            err = "device_name may contain only letters, digits and '-'";
            return false;
        }
    }
    c = next;
    return true;
}

void publicConfig(const Config& c, JsonObject out) {
    out["wifi_ssid"] = c.wifiSsid;
    out["wifi_pass_set"] = c.wifiPass.length() > 0;
    out["device_name"] = c.deviceName;
    out["speaker_host"] = c.speakerHost;
    out["speaker_name"] = c.speakerName;
    out["mqtt_host"] = c.mqttHost;
    out["mqtt_port"] = c.mqttPort;
    out["mqtt_user"] = c.mqttUser;
    out["mqtt_pass_set"] = c.mqttPass.length() > 0;
    out["mqtt_topic"] = c.baseTopic();
    out["mqtt_tls"] = c.mqttTls;
}
