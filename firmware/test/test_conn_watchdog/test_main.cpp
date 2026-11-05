// Host tests for the connectivity watchdog: `pio test -e native`
#include <unity.h>

#include "conn_watchdog.h"

using connwd::Action;
using connwd::View;
using connwd::Watchdog;

void setUp() {}
void tearDown() {}

static View view(bool wifi, bool mqtt, bool wanted = true) {
    View v;
    v.wifiUp = wifi;
    v.mqttUp = mqtt;
    v.mqttWanted = wanted;
    return v;
}

// Steps every second from `from` to `to` (inclusive) and returns the first action other than None.
static Action run(Watchdog& wd, const View& v, uint32_t from, uint32_t to, uint32_t* at = nullptr) {
    for (uint32_t t = from;; t += 1000) {
        Action a = wd.step(v, t);
        if (a != Action::None) {
            if (at) *at = t;
            return a;
        }
        if (t == to) return Action::None;
    }
}

static void test_all_up_does_nothing() {
    Watchdog wd;
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::None, run(wd, view(true, true), 0, 3600000));
}

static void test_no_broker_configured_never_restarts() {
    Watchdog wd;
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::None, run(wd, view(true, false, false), 0, 3600000));
}

static void test_wifi_down_kicks_every_minute() {
    Watchdog wd;
    wd.begin(0);
    uint32_t at = 0;
    TEST_ASSERT_EQUAL(Action::ReconnectWifi, run(wd, view(false, false), 0, 120000, &at));
    TEST_ASSERT_EQUAL_UINT32(60000, at);
    TEST_ASSERT_EQUAL(Action::ReconnectWifi, run(wd, view(false, false), at + 1000, 200000, &at));
    TEST_ASSERT_EQUAL_UINT32(120000, at);
}

static void test_wifi_down_ten_minutes_restarts() {
    Watchdog wd;
    wd.begin(0);
    uint32_t at = 0;
    int kicks = 0;
    Action a;
    while ((a = run(wd, view(false, false), at ? at + 1000 : 0, 700000, &at)) == Action::ReconnectWifi) kicks++;
    TEST_ASSERT_EQUAL(Action::RestartNoWifi, a);
    TEST_ASSERT_EQUAL_UINT32(600000, at);
    TEST_ASSERT_EQUAL(9, kicks);  // at 1..9 min; at 10 min the restart wins
}

static void test_wifi_back_resets_the_clock() {
    Watchdog wd;
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::None, run(wd, view(false, true), 0, 50000));
    TEST_ASSERT_EQUAL(Action::None, wd.step(view(true, true), 51000));
    uint32_t at = 0;
    TEST_ASSERT_EQUAL(Action::ReconnectWifi, run(wd, view(false, true), 52000, 200000, &at));
    TEST_ASSERT_EQUAL_UINT32(111000, at);  // a full minute after Wi-Fi was last up
}

static void test_mqtt_down_ten_minutes_restarts() {
    Watchdog wd;
    wd.begin(0);
    uint32_t at = 0;
    TEST_ASSERT_EQUAL(Action::RestartNoMqtt, run(wd, view(true, false), 0, 700000, &at));
    TEST_ASSERT_EQUAL_UINT32(600000, at);
}

static void test_mqtt_reconnect_resets_the_clock() {
    Watchdog wd;
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::None, run(wd, view(true, false), 0, 590000));
    TEST_ASSERT_EQUAL(Action::None, wd.step(view(true, true), 591000));
    uint32_t at = 0;
    TEST_ASSERT_EQUAL(Action::RestartNoMqtt, run(wd, view(true, false), 592000, 1300000, &at));
    TEST_ASSERT_EQUAL_UINT32(1191000, at);  // counted from the last step that saw MQTT up
}

static void test_mqtt_clock_pauses_while_wifi_is_down() {
    Watchdog wd;
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::None, run(wd, view(true, false), 0, 300000));  // 5 min without MQTT
    TEST_ASSERT_EQUAL(Action::ReconnectWifi, run(wd, view(false, false), 301000, 361000));
    TEST_ASSERT_EQUAL(Action::None, run(wd, view(false, false), 362000, 400000));
    // Wi-Fi back: about 5 more minutes of MQTT-less Wi-Fi time before a restart
    uint32_t at = 0;
    TEST_ASSERT_EQUAL(Action::RestartNoMqtt, run(wd, view(true, false), 401000, 1000000, &at));
    TEST_ASSERT_UINT32_WITHIN(2000, 701000, at);
}

static void test_flapping_wifi_still_restarts_stuck_mqtt() {
    Watchdog wd;
    wd.begin(0);
    uint32_t t = 0;
    Action a = Action::None;
    for (int i = 0; i < 20 && a == Action::None; i++) {
        a = run(wd, view(true, false), t, t + 120000);  // 2 min up
        t += 121000;
        if (a == Action::None) a = run(wd, view(false, false), t, t + 30000);  // 30 s down: no kick yet
        t += 31000;
    }
    TEST_ASSERT_EQUAL(Action::RestartNoMqtt, a);
}

static void test_survives_millis_wraparound() {
    Watchdog wd;
    uint32_t start = 0xFFFFFFFFu - 30000;
    wd.begin(start);
    uint32_t at = 0;
    TEST_ASSERT_EQUAL(Action::ReconnectWifi, run(wd, view(false, false), start, start + 120000, &at));
    TEST_ASSERT_EQUAL_UINT32(start + 60000, at);  // wrapped past zero
    wd.begin(start);
    TEST_ASSERT_EQUAL(Action::RestartNoMqtt, run(wd, view(true, false), start, start + 700000, &at));
    TEST_ASSERT_EQUAL_UINT32(start + 600000, at);
}

static void test_long_gap_between_steps() {
    // loop() can stall (an HTTP play waits up to ~40 s); one big step still counts in full
    Watchdog wd;
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::None, wd.step(view(true, false), 0));
    TEST_ASSERT_EQUAL(Action::RestartNoMqtt, wd.step(view(true, false), 4000000000u));
    wd.begin(0);
    TEST_ASSERT_EQUAL(Action::RestartNoWifi, wd.step(view(false, false), 650000));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_all_up_does_nothing);
    RUN_TEST(test_no_broker_configured_never_restarts);
    RUN_TEST(test_wifi_down_kicks_every_minute);
    RUN_TEST(test_wifi_down_ten_minutes_restarts);
    RUN_TEST(test_wifi_back_resets_the_clock);
    RUN_TEST(test_mqtt_down_ten_minutes_restarts);
    RUN_TEST(test_mqtt_reconnect_resets_the_clock);
    RUN_TEST(test_mqtt_clock_pauses_while_wifi_is_down);
    RUN_TEST(test_flapping_wifi_still_restarts_stuck_mqtt);
    RUN_TEST(test_survives_millis_wraparound);
    RUN_TEST(test_long_gap_between_steps);
    return UNITY_END();
}
