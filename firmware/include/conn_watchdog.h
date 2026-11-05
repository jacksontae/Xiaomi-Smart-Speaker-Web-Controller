// Connectivity watchdog: decides when the relay must kick Wi-Fi or restart itself so it never stays offline
// until someone power-cycles it. The ESP32 core's auto-reconnect gives up after some disconnect reasons
// (e.g. AUTH_FAIL or ASSOC_LEAVE while the access point reboots), and a network client can wedge.
// Pure logic on millis(): main.cpp feeds it what it sees and performs the action it returns. Builds on the
// host for tests.
//
//   Wi-Fi down 60 s      -> ReconnectWifi, then again every 60 s
//   Wi-Fi down 10 min    -> RestartNoWifi
//   MQTT down 10 min     -> RestartNoMqtt (counts only while Wi-Fi is up and a broker is configured)
#pragma once

#include <stdint.h>

namespace connwd {

constexpr uint32_t kWifiRetryMs = 60000;
constexpr uint32_t kWifiRestartMs = 600000;
constexpr uint32_t kMqttRestartMs = 600000;

enum class Action : uint8_t { None, ReconnectWifi, RestartNoWifi, RestartNoMqtt };

// What the relay sees right now.
struct View {
    bool wifiUp = false;
    bool mqttWanted = false;  // a broker is configured
    bool mqttUp = false;      // connected over either transport
};

class Watchdog {
   public:
    void begin(uint32_t now) {
        wifiOkAt_ = lastRetry_ = lastStep_ = now;
        mqttDownMs_ = 0;
    }

    // Call on every loop; returns the one thing to do now. All times wrap safely with millis().
    Action step(const View& v, uint32_t now) {
        uint32_t dt = now - lastStep_;
        lastStep_ = now;
        if (!v.wifiUp) {
            // MQTT time is paused: without Wi-Fi it can't connect, and the Wi-Fi rules cover this.
            if (now - wifiOkAt_ >= kWifiRestartMs) return Action::RestartNoWifi;
            if (now - lastRetry_ >= kWifiRetryMs) {
                lastRetry_ = now;
                return Action::ReconnectWifi;
            }
            return Action::None;
        }
        wifiOkAt_ = lastRetry_ = now;  // the next outage waits a full minute before the first kick
        if (!v.mqttWanted || v.mqttUp) {
            mqttDownMs_ = 0;
            return Action::None;
        }
        // Accumulated, so a flapping Wi-Fi can't keep a stuck MQTT client alive forever.
        mqttDownMs_ = dt >= kMqttRestartMs - mqttDownMs_ ? kMqttRestartMs : mqttDownMs_ + dt;
        return mqttDownMs_ >= kMqttRestartMs ? Action::RestartNoMqtt : Action::None;
    }

    uint32_t mqttDownMs() const { return mqttDownMs_; }

   private:
    uint32_t wifiOkAt_ = 0;   // last time Wi-Fi was up
    uint32_t lastRetry_ = 0;  // last Wi-Fi kick (or last time Wi-Fi was up)
    uint32_t lastStep_ = 0;
    uint32_t mqttDownMs_ = 0;  // Wi-Fi-up time without MQTT since MQTT was last connected
};

}  // namespace connwd
