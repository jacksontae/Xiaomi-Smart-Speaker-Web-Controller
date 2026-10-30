#include "mqtt_ws.h"

#if RELAY_HAS_MQTT_TLS

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <mqtt_client.h>

namespace {
struct Incoming {
    String topic;
    String payload;
};
const size_t kMaxMessage = 4096;  // commands are small; anything bigger is dropped
}  // namespace

bool WsMqtt::begin(const String& uri, const String& user, const String& pass, const String& clientId,
                   const String& willTopic, const String& subscribeTopic, const char* caPem, Handler onMessage) {
    end();
    // esp-mqtt keeps pointers to these strings, so they live in members.
    uri_ = uri;
    user_ = user;
    pass_ = pass;
    clientId_ = clientId;
    willTopic_ = willTopic;
    subscribeTopic_ = subscribeTopic;
    handler_ = onMessage;
    queue_ = xQueueCreate(8, sizeof(Incoming*));

    esp_mqtt_client_config_t cfg = {};
    cfg.uri = uri_.c_str();
    cfg.client_id = clientId_.c_str();
    if (user_.length()) cfg.username = user_.c_str();
    if (pass_.length()) cfg.password = pass_.c_str();
    cfg.lwt_topic = willTopic_.c_str();
    cfg.lwt_msg = "false";
    cfg.lwt_qos = 1;
    cfg.lwt_retain = 1;
    cfg.keepalive = 60;  // under Cloudflare's 100 s idle limit for WebSockets
    cfg.buffer_size = 2048;
    cfg.reconnect_timeout_ms = 5000;
    cfg.network_timeout_ms = 10000;
    if (uri_.startsWith("wss://")) cfg.cert_pem = caPem;

    auto client = esp_mqtt_client_init(&cfg);
    if (!client) return false;
    client_ = client;
    esp_mqtt_client_register_event(client, MQTT_EVENT_ANY, onEvent, this);
    return esp_mqtt_client_start(client) == ESP_OK;
}

void WsMqtt::end() {
    if (client_) {
        auto client = static_cast<esp_mqtt_client_handle_t>(client_);
        esp_mqtt_client_stop(client);
        esp_mqtt_client_destroy(client);
        client_ = nullptr;
    }
    if (queue_) {
        Incoming* msg;
        while (xQueueReceive(static_cast<QueueHandle_t>(queue_), &msg, 0) == pdTRUE) delete msg;
        vQueueDelete(static_cast<QueueHandle_t>(queue_));
        queue_ = nullptr;
    }
    connected_ = justConnected_ = false;
}

bool WsMqtt::publish(const String& topic, const String& payload, bool retained) {
    if (!client_ || !connected_) return false;
    return esp_mqtt_client_publish(static_cast<esp_mqtt_client_handle_t>(client_), topic.c_str(), payload.c_str(),
                                   payload.length(), 1, retained) >= 0;
}

void WsMqtt::loop() {
    if (!queue_) return;
    Incoming* msg;
    while (xQueueReceive(static_cast<QueueHandle_t>(queue_), &msg, 0) == pdTRUE) {
        if (handler_) handler_(msg->topic, msg->payload);
        delete msg;
    }
}

bool WsMqtt::takeJustConnected() {
    if (!justConnected_) return false;
    justConnected_ = false;
    return true;
}

// Runs in the esp-mqtt task.
void WsMqtt::onEvent(void* arg, const char*, int32_t id, void* data) {
    auto self = static_cast<WsMqtt*>(arg);
    auto ev = static_cast<esp_mqtt_event_handle_t>(data);
    switch (id) {
        case MQTT_EVENT_CONNECTED:
            esp_mqtt_client_publish(ev->client, self->willTopic_.c_str(), "true", 4, 1, 1);
            esp_mqtt_client_subscribe(ev->client, self->subscribeTopic_.c_str(), 1);
            self->connected_ = true;
            self->justConnected_ = true;
            break;
        case MQTT_EVENT_DISCONNECTED:
            self->connected_ = false;
            break;
        case MQTT_EVENT_DATA: {
            if (ev->total_data_len > (int)kMaxMessage) break;
            if (ev->current_data_offset == 0) {
                self->partTopic_ = String(ev->topic, ev->topic_len);
                self->partBody_ = "";
                self->partBody_.reserve(ev->total_data_len);
            }
            self->partBody_.concat(ev->data, ev->data_len);
            if (ev->current_data_offset + ev->data_len < ev->total_data_len) break;  // more parts follow
            auto msg = new Incoming{self->partTopic_, self->partBody_};
            if (xQueueSend(static_cast<QueueHandle_t>(self->queue_), &msg, 0) != pdTRUE) delete msg;  // full: drop
            break;
        }
        case MQTT_EVENT_ERROR:
            if (ev->error_handle && ev->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT)
                Serial.printf("[mqtt] transport error (tls 0x%x, errno %d)\n", ev->error_handle->esp_tls_last_esp_err,
                              ev->error_handle->esp_transport_sock_errno);
            else if (ev->error_handle && ev->error_handle->error_type == MQTT_ERROR_TYPE_CONNECTION_REFUSED)
                Serial.printf("[mqtt] broker refused the connection (code %d)\n",
                              ev->error_handle->connect_return_code);
            break;
        default:
            break;
    }
}

#endif
