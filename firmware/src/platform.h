// The few places where the ESP32 and ESP8266 Arduino cores differ.
#pragma once

#include <Arduino.h>
#include <LittleFS.h>

#if defined(ESP32)
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

using SecureClient = WiFiClientSecure;
#define RELAY_HAS_MQTT_TLS 1  // enough RAM for TLS to the speaker and to the broker at once

inline uint32_t chipId() { return static_cast<uint32_t>(ESP.getEfuseMac()); }
inline void setStationHostname(const char* name) { WiFi.setHostname(name); }
inline bool mountFs() { return LittleFS.begin(true); }  // format on first boot
inline void mdnsUpdate() {}

// Why the chip last reset, in the words of the status JSON's `reset_reason`.
inline const char* resetReasonName() {
    switch (esp_reset_reason()) {
        case ESP_RST_POWERON: return "power_on";
        case ESP_RST_EXT: return "external";
        case ESP_RST_SW: return "software";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT:
        case ESP_RST_TASK_WDT:
        case ESP_RST_WDT: return "hw_watchdog";
        case ESP_RST_DEEPSLEEP: return "deep_sleep";
        case ESP_RST_BROWNOUT: return "brownout";
        default: return "unknown";
    }
}
// A word kept across ESP.restart() (not across power loss), to tell the next boot why we restarted.
inline uint32_t& restartNoteSlot() {
    static RTC_NOINIT_ATTR uint32_t note;
    return note;
}
inline void writeRestartNote(uint32_t v) { restartNoteSlot() = v; }
inline uint32_t readRestartNote() { return restartNoteSlot(); }

#elif defined(ESP8266)
#include <ESP8266WebServer.h>
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <WiFiClientSecureBearSSL.h>

using WebServer = ESP8266WebServer;
using SecureClient = BearSSL::WiFiClientSecure;
#define RELAY_HAS_MQTT_TLS 0  // ~40 KB free heap: one TLS session (the speaker) at a time

inline uint32_t chipId() { return ESP.getChipId(); }
inline void setStationHostname(const char* name) { WiFi.hostname(name); }
inline bool mountFs() { return LittleFS.begin(); }  // FSConfig auto-formats by default
inline void mdnsUpdate() { MDNS.update(); }         // LEAmDNS runs from loop()

inline const char* resetReasonName() {
    switch (ESP.getResetInfoPtr()->reason) {
        case REASON_DEFAULT_RST: return "power_on";
        case REASON_EXT_SYS_RST: return "external";
        case REASON_SOFT_RESTART: return "software";
        case REASON_EXCEPTION_RST: return "panic";
        case REASON_WDT_RST:
        case REASON_SOFT_WDT_RST: return "hw_watchdog";
        case REASON_DEEP_SLEEP_AWAKE: return "deep_sleep";
        default: return "unknown";
    }
}
inline void writeRestartNote(uint32_t v) { ESP.rtcUserMemoryWrite(0, &v, sizeof(v)); }
inline uint32_t readRestartNote() {
    uint32_t v = 0;
    ESP.rtcUserMemoryRead(0, &v, sizeof(v));
    return v;
}

#else
#error "Speaker relay supports ESP32 and ESP8266"
#endif
