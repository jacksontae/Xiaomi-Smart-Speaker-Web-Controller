// Speaker relay: drives a Google Cast speaker on this LAN for a server elsewhere.
//
// Commands arrive over HTTP (POST /api/<cmd>, Bearer token) or MQTT (<base>/cmd) and use one
// JSON shape: {"cmd": "play", "url": "...", "content_type": "audio/mpeg", "title": "...",
//              "volume": 0.4, "position": 12.5} · {"cmd": "volume", "level": 0.3}
//             · {"cmd": "stop" | "pause" | "resume" | "status"}
// Audio URLs must be reachable by the speaker; this board never touches the audio itself.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>

#include "cast_client.h"
#include "config.h"
#include "platform.h"

#if defined(ESP8266)
#include <ESP8266HTTPClient.h>
#endif

#ifndef RELAY_VERSION
#define RELAY_VERSION "dev"
#endif

static const int kResetPin = 0;  // BOOT button: hold while powering on to wipe settings
static const uint32_t kWifiTimeoutMs = 20000;
static const uint32_t kStatusEveryMs = 30000;

Config config;
CastClient cast;
WebServer server(80);
WiFiClient mqttPlain;
#if RELAY_HAS_MQTT_TLS
SecureClient mqttSecure;
#endif
PubSubClient mqtt;
String mqttCa;  // PEM kept alive for WiFiClientSecure, which stores only the pointer
bool setupMode = false;
uint32_t lastMqttTry = 0;
uint32_t lastStatus = 0;

// ---------- speaker ----------

#if defined(ESP8266)
// LEAmDNS can't read TXT records from a one-shot query, so ask the speaker for its name instead.
static String castFriendlyName(IPAddress ip) {
    WiFiClient client;
    HTTPClient http;
    http.setTimeout(2000);
    if (!http.begin(client, "http://" + ip.toString() + ":8008/setup/eureka_info?params=name")) return "";
    String name;
    if (http.GET() == 200) {
        JsonDocument doc;
        if (!deserializeJson(doc, http.getString())) name = doc["name"] | "";
    }
    http.end();
    return name;
}
#endif

static bool matchesName(int i) {
    if (!config.speakerName.length()) return true;
#if defined(ESP32)
    return MDNS.txt(i, "fn") == config.speakerName;
#else
    return castFriendlyName(MDNS.IP(i)) == config.speakerName;
#endif
}

static bool resolveSpeaker(IPAddress& ip, uint16_t& port, String& err) {
    port = 8009;
    if (config.speakerHost.length()) {
        if (ip.fromString(config.speakerHost) || WiFi.hostByName(config.speakerHost.c_str(), ip)) return true;
        err = "can't resolve speaker_host " + config.speakerHost;
        return false;
    }
    int n = MDNS.queryService("googlecast", "tcp");
    for (int i = 0; i < n; i++) {
        if (MDNS.IP(i) == IPAddress(0, 0, 0, 0)) continue;  // answer without an A record
        if (matchesName(i)) {
            ip = MDNS.IP(i);
            port = MDNS.port(i);  // groups and stereo pairs use a port other than 8009
            return true;
        }
    }
    err = config.speakerName.length() ? "speaker \"" + config.speakerName + "\" not found on this network"
                                      : "no Cast speaker found on this network";
    return false;
}

static bool ensureSpeaker(String& err) {
    if (WiFi.status() != WL_CONNECTED) {
        err = "relay is not connected to Wi-Fi";
        return false;
    }
    if (cast.connected()) return true;
    IPAddress ip;
    uint16_t port;
    return resolveSpeaker(ip, port, err) && cast.begin(ip, err, port);
}

static void speakerStatus(JsonObject out) {
    String err;
    if (ensureSpeaker(err)) cast.refresh(err);
    cast.status(out);
    if (err.length()) out["error"] = err;
}

// ---------- commands (shared by HTTP and MQTT) ----------

static bool runCommand(JsonVariantConst in, JsonDocument& out, String& err) {
    String cmd = in["cmd"] | "";
    if (cmd == "status") {
        speakerStatus(out["speaker"].to<JsonObject>());
        return true;
    }
    if (!ensureSpeaker(err)) return false;
    bool ok;
    if (cmd == "play") {
        String url = in["url"] | "";
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            err = "url must be an http(s) URL";
            return false;
        }
        if (!in["volume"].isNull() && !cast.setVolume(in["volume"].as<float>(), err)) return false;
        ok = cast.play(url, in["content_type"] | "audio/mpeg", in["title"] | "", in["position"] | -1.0f, err);
    } else if (cmd == "volume") {
        float level = in["level"] | -1.0f;
        if (level < 0 || level > 1) {
            err = "level must be between 0 and 1";
            return false;
        }
        ok = cast.setVolume(level, err);
    } else if (cmd == "stop") {
        ok = cast.stop(err);
    } else if (cmd == "pause") {
        ok = cast.pause(err);
    } else if (cmd == "resume") {
        ok = cast.resume(err);
    } else {
        err = "unknown cmd \"" + cmd + "\"";
        return false;
    }
    if (ok) cast.status(out["speaker"].to<JsonObject>());
    return ok;
}

// ---------- HTTP ----------

static void sendJson(int code, JsonDocument& doc) {
    String body;
    serializeJson(doc, body);
    server.send(code, "application/json", body);
}

static void sendError(int code, const String& msg) {
    JsonDocument doc;
    doc["ok"] = false;
    doc["error"] = msg;
    sendJson(code, doc);
}

static bool tokenMatches(const String& given) {
    const String& want = config.apiToken;
    if (!want.length() || given.length() != want.length()) return false;
    uint8_t diff = 0;
    for (size_t i = 0; i < want.length(); i++) diff |= given[i] ^ want[i];
    return diff == 0;
}

static bool authorized() {
    String h = server.header("Authorization");
    if (h.startsWith("Bearer ") && tokenMatches(h.substring(7))) return true;
    server.sendHeader("WWW-Authenticate", "Bearer");
    sendError(401, "Missing or invalid API token");
    return false;
}

static bool readBody(JsonDocument& doc) {
    if (!server.hasArg("plain")) {
        // WebServer parses form-encoded bodies (curl -d's default) into args and drops "plain".
        if (server.args() == 0) return true;  // no body is fine for stop/pause/...
        sendError(415, "send the body as JSON with Content-Type: application/json");
        return false;
    }
    if (deserializeJson(doc, server.arg("plain"))) {
        sendError(400, "body must be JSON");
        return false;
    }
    return true;
}

static void handleCommand(const char* cmd) {
    if (!authorized()) return;
    JsonDocument in;
    if (!readBody(in)) return;
    in["cmd"] = cmd;
    JsonDocument out;
    String err;
    bool ok = runCommand(in.as<JsonVariantConst>(), out, err);
    out["ok"] = ok;
    if (!ok) out["error"] = err;
    sendJson(ok ? 200 : 503, out);
}

static void handleGetConfig() {
    if (!authorized()) return;
    JsonDocument doc;
    publicConfig(config, doc.to<JsonObject>());
    doc["version"] = RELAY_VERSION;
    sendJson(200, doc);
}

static void handleSetConfig() {
    if (!authorized()) return;
    JsonDocument in;
    if (!readBody(in)) return;
    if (!in["api_token"].isNull()) return sendError(400, "rotate the token with POST /api/token/rotate");
    Config next = config;
    String err;
    if (!applyConfig(next, in.as<JsonVariantConst>(), err)) return sendError(422, err);
    bool restart = next.wifiSsid != config.wifiSsid || next.wifiPass != config.wifiPass ||
                   next.deviceName != config.deviceName || next.mqttHost != config.mqttHost ||
                   next.mqttPort != config.mqttPort || next.mqttTls != config.mqttTls ||
                   next.mqttUser != config.mqttUser || next.mqttPass != config.mqttPass ||
                   next.mqttTopic != config.mqttTopic;
    if (!saveConfig(next)) return sendError(500, "could not save settings");
    if (next.speakerHost != config.speakerHost || next.speakerName != config.speakerName) cast.end();
    config = next;
    JsonDocument out;
    out["ok"] = true;
    out["restart"] = restart;
    sendJson(200, out);
    if (restart) {
        delay(300);
        ESP.restart();
    }
}

static void handleRotateToken() {
    if (!authorized()) return;
    Config next = config;
    next.apiToken = randomToken();
    if (!saveConfig(next)) return sendError(500, "could not save settings");
    config = next;
    JsonDocument out;
    out["ok"] = true;
    out["api_token"] = config.apiToken;  // shown once; the old token stops working now
    sendJson(200, out);
}

static void handleMqttCa() {
    if (!authorized()) return;
#if !RELAY_HAS_MQTT_TLS
    return sendError(400, "MQTT over TLS needs an ESP32");
#endif
    String pem = server.arg("plain");
    File f = LittleFS.open("/mqtt_ca.pem", "w");
    if (!f) return sendError(500, "could not save certificate");
    f.print(pem);
    f.close();
    JsonDocument out;
    out["ok"] = true;
    out["restart"] = true;
    sendJson(200, out);
    delay(300);
    ESP.restart();
}

static const char kInfoPage[] PROGMEM = R"HTML(<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Speaker Relay</title>
<body style="font:16px/1.5 system-ui;max-width:560px;margin:24px auto;padding:0 16px">
<h1>Speaker Relay</h1><p>This board controls a Cast speaker for the speaker service.
Send commands to <code>/api/&lt;cmd&gt;</code> with <code>Authorization: Bearer &lt;token&gt;</code>.</p>
<pre style="background:#eee;padding:12px;overflow:auto">curl -X POST http://THIS-IP/api/play \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url":"http://.../a.mp3","content_type":"audio/mpeg"}'</pre></body></html>)HTML";

static void startApi() {
#if defined(ESP8266)
    server.collectHeaders("Authorization");  // the array overload loses to the variadic template here
#else
    const char* headers[] = {"Authorization"};
    server.collectHeaders(headers, 1);
#endif
    server.on("/", HTTP_GET, [] { server.send_P(200, "text/html", kInfoPage); });
    server.on("/api/status", HTTP_GET, [] { handleCommand("status"); });
    server.on("/api/play", HTTP_POST, [] { handleCommand("play"); });
    server.on("/api/volume", HTTP_POST, [] { handleCommand("volume"); });
    server.on("/api/stop", HTTP_POST, [] { handleCommand("stop"); });
    server.on("/api/pause", HTTP_POST, [] { handleCommand("pause"); });
    server.on("/api/resume", HTTP_POST, [] { handleCommand("resume"); });
    server.on("/api/config", HTTP_GET, handleGetConfig);
    server.on("/api/config", HTTP_POST, handleSetConfig);
    server.on("/api/token/rotate", HTTP_POST, handleRotateToken);
    server.on("/api/mqtt-ca", HTTP_POST, handleMqttCa);
    server.on("/api/reboot", HTTP_POST, [] {
        if (!authorized()) return;
        server.send(200, "application/json", "{\"ok\":true}");
        delay(300);
        ESP.restart();
    });
    server.onNotFound([] { sendError(404, "not found"); });
    server.begin();
}

// ---------- first-time setup (access point) ----------

static String htmlEscape(const String& s) {
    String o;
    for (char ch : s) {
        if (ch == '<') o += "&lt;";
        else if (ch == '>') o += "&gt;";
        else if (ch == '&') o += "&amp;";
        else if (ch == '"') o += "&quot;";
        else o += ch;
    }
    return o;
}

static String field(const char* name, const char* label, const String& value, const char* type = "text") {
    return String("<label>") + label + "<br><input name=\"" + name + "\" type=\"" + type + "\" value=\"" +
           htmlEscape(value) + "\" style=\"width:100%;padding:8px;margin:4px 0 12px\"></label>";
}

static void handleSetupPage() {
    String page =
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Speaker Relay setup</title><body style='font:16px/1.5 system-ui;max-width:480px;margin:24px "
        "auto;padding:0 16px'><h1>Speaker Relay setup</h1><form method=post action=/setup>";
    page += field("wifi_ssid", "Wi-Fi name (2.4 GHz)", config.wifiSsid);
    page += field("wifi_pass", "Wi-Fi password", "", "password");
    page += field("device_name", "Device name", config.deviceName);
    page += field("speaker_host", "Speaker IP (blank = find automatically)", config.speakerHost);
    page += field("speaker_name", "Speaker name to pick (blank = first found)", config.speakerName);
    page += field("mqtt_host", "MQTT broker host (blank = off)", config.mqttHost);
    page += field("mqtt_port", "MQTT port", String(config.mqttPort));
    page += field("mqtt_user", "MQTT user", config.mqttUser);
    page += field("mqtt_pass", "MQTT password", "", "password");
    page += field("mqtt_topic", "MQTT base topic (blank = speaker-relay/&lt;device&gt;)", config.mqttTopic);
    page += "<label><input type=checkbox name=mqtt_tls value=1";
    page += config.mqttTls ? " checked" : "";
    page += "> MQTT over TLS</label><p>API token (copy it now; it is needed for every API call):<br><code>";
    page += config.apiToken;
    page += "</code></p><button style='padding:10px 20px'>Save and connect</button></form></body>";
    server.send(200, "text/html", page);
}

static void handleSetupSave() {
    JsonDocument in;
    const char* keys[] = {"wifi_ssid", "device_name", "speaker_host", "speaker_name", "mqtt_host", "mqtt_user",
                          "mqtt_topic"};
    for (const char* k : keys) in[k] = server.arg(k);
    if (server.arg("wifi_pass").length()) in["wifi_pass"] = server.arg("wifi_pass");
    if (server.arg("mqtt_pass").length()) in["mqtt_pass"] = server.arg("mqtt_pass");
    in["mqtt_port"] = server.arg("mqtt_port").toInt();
    in["mqtt_tls"] = server.hasArg("mqtt_tls");
    String err;
    Config next = config;
    if (!applyConfig(next, in.as<JsonVariantConst>(), err) || !next.wifiSsid.length()) {
        server.send(422, "text/plain", err.length() ? err : "Wi-Fi name is required");
        return;
    }
    if (!saveConfig(next)) {
        server.send(500, "text/plain", "could not save settings");
        return;
    }
    server.send(200, "text/plain", "Saved. The relay restarts and joins " + next.wifiSsid + ".");
    delay(500);
    ESP.restart();
}

static void startSetupMode() {
    setupMode = true;
    String ap = "SpeakerRelay-" + String(chipId(), HEX).substring(0, 4);
    WiFi.mode(WIFI_AP);
    WiFi.softAP(ap.c_str());
    Serial.printf("[setup] join Wi-Fi \"%s\" and open http://%s/\n", ap.c_str(), WiFi.softAPIP().toString().c_str());
    server.on("/", HTTP_GET, handleSetupPage);
    server.on("/setup", HTTP_POST, handleSetupSave);
    server.onNotFound(handleSetupPage);  // captive-portal style: every path shows the form
    server.begin();
}

// ---------- MQTT ----------

static void publishJson(const String& topic, JsonDocument& doc, bool retained = false) {
    String body;
    serializeJson(doc, body);
    if (!mqtt.publish(topic.c_str(), body.c_str(), retained))
        Serial.printf("[mqtt] publish to %s failed (%u bytes, connected=%d)\n", topic.c_str(), body.length(),
                      mqtt.connected());
}

static void onMqtt(char* topic, byte* payload, unsigned int len) {
    JsonDocument in;
    JsonDocument out;
    String err;
    if (deserializeJson(in, payload, len)) {
        out["ok"] = false;
        out["error"] = "payload must be JSON";
    } else {
        out["id"] = in["id"];
        bool ok = runCommand(in.as<JsonVariantConst>(), out, err);
        out["ok"] = ok;
        if (!ok) out["error"] = err;
    }
    publishJson(config.baseTopic() + "/result", out);
}

static void setupMqtt() {
    if (!config.mqttHost.length()) return;
    if (config.mqttTls) {
#if RELAY_HAS_MQTT_TLS
        File f = LittleFS.open("/mqtt_ca.pem", "r");
        if (f) {
            mqttCa = f.readString();
            f.close();
            mqttSecure.setCACert(mqttCa.c_str());
        } else {
            Serial.println("[mqtt] WARNING: TLS without a CA certificate; server identity is not verified");
            mqttSecure.setInsecure();
        }
        mqttSecure.setHandshakeTimeout(10);  // default 120 s would freeze loop() and starve Cast heartbeats
        mqtt.setClient(mqttSecure);
#else
        Serial.println("[mqtt] MQTT over TLS needs an ESP32; MQTT disabled");
        config.mqttHost = "";
        return;
#endif
    } else {
        mqtt.setClient(mqttPlain);
    }
    mqtt.setServer(config.mqttHost.c_str(), config.mqttPort);
    mqtt.setBufferSize(2048);
    mqtt.setKeepAlive(60);  // a cold play can block the callback ~40 s; the 15 s default drops the session
    mqtt.setCallback(onMqtt);
}

static void loopMqtt() {
    if (!config.mqttHost.length() || WiFi.status() != WL_CONNECTED) return;
    if (mqtt.connected()) {
        mqtt.loop();
        return;
    }
    if (millis() - lastMqttTry < 5000) return;
    lastMqttTry = millis();
    String base = config.baseTopic();
    String willTopic = base + "/online";
    bool ok = mqtt.connect(config.deviceName.c_str(), config.mqttUser.length() ? config.mqttUser.c_str() : nullptr,
                           config.mqttPass.length() ? config.mqttPass.c_str() : nullptr, willTopic.c_str(), 1, true,
                           "false");
    if (!ok) {
        Serial.printf("[mqtt] connect to %s:%u failed (state %d)\n", config.mqttHost.c_str(), config.mqttPort,
                      mqtt.state());
        return;
    }
    mqtt.publish(willTopic.c_str(), "true", true);
    mqtt.subscribe((base + "/cmd").c_str(), 1);
    Serial.printf("[mqtt] connected; listening on %s/cmd\n", base.c_str());
    lastStatus = 0;  // publish status right away
}

static void publishStatus() {
    if (!mqtt.connected() || millis() - lastStatus < kStatusEveryMs) return;
    lastStatus = millis();
    JsonDocument doc;
    doc["version"] = RELAY_VERSION;
    doc["ip"] = WiFi.localIP().toString();
    doc["rssi"] = WiFi.RSSI();
    doc["heap"] = ESP.getFreeHeap();
    cast.status(doc["speaker"].to<JsonObject>());  // cached; never blocks the loop on the speaker
    publishJson(config.baseTopic() + "/status", doc, true);
}

// ---------- boot ----------

static bool resetRequested() {
    pinMode(kResetPin, INPUT_PULLUP);
    uint32_t start = millis();
    while (digitalRead(kResetPin) == LOW) {
        if (millis() - start > 3000) return true;
        delay(10);
    }
    return false;
}

void setup() {
    Serial.begin(115200);
    Serial.printf("\nSpeaker Relay %s\n", RELAY_VERSION);
    if (!mountFs()) Serial.println("[fs] LittleFS mount failed");
    if (resetRequested()) {
        Serial.println("[setup] BOOT held: settings wiped");
        wipeConfig();
        LittleFS.remove("/mqtt_ca.pem");
    }
    loadConfig(config);
    if (!config.apiToken.length()) {
        config.apiToken = randomToken();
        saveConfig(config);
    }
    if (!config.wifiSsid.length()) return startSetupMode();

    // Once configured, never fall back to the open setup AP (it would expose the token and accept new
    // settings from anyone nearby). Keep retrying the saved network; hold BOOT at power-on to reconfigure.
    setStationHostname(config.deviceName.c_str());  // must precede WiFi.mode() to reach DHCP
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(config.wifiSsid.c_str(), config.wifiPass.c_str());
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < kWifiTimeoutMs) delay(200);
    if (WiFi.status() != WL_CONNECTED)
        Serial.printf("[wifi] can't join \"%s\" yet; retrying in the background\n", config.wifiSsid.c_str());
    startApi();
    setupMqtt();
}

void loop() {
    if (setupMode) {
        server.handleClient();
        return;
    }
    static bool online = false;
    if (WiFi.status() == WL_CONNECTED) {
        if (!online) {
            online = true;
            Serial.printf("[wifi] %s  http://%s/\n", config.wifiSsid.c_str(), WiFi.localIP().toString().c_str());
            if (MDNS.begin(config.deviceName.c_str())) MDNS.addService("http", "tcp", 80);
        }
    } else if (online) {
        online = false;
        Serial.println("[wifi] disconnected; reconnecting");
        cast.end();
    }
    mdnsUpdate();
    server.handleClient();
    cast.loop();
    loopMqtt();
    publishStatus();
}
