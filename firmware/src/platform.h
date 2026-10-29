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

#else
#error "Speaker relay supports ESP32 and ESP8266"
#endif
