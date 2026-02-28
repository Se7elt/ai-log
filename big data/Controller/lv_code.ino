#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <lvgl.h>

const char* ssid     = "TECNO CAMON 30";
const char* password = "6y5t4r3e";
const char* log_url  = "http://10.64.29.62:8000/api/logs";

#define MAX_LOGS 20
struct LogEntry {
  int id;
  String timestamp;
  String ip_address;
  float cpu_load;
  float ram_usage;
  float temperature;
  String log_message;
};
LogEntry logs[MAX_LOGS];
int logCount = 0;

int count_1 = 0, count_15 = 0, count_60 = 0;
lv_obj_t *detail_window = nullptr;

static unsigned long lastUpdate = 0;
const unsigned long updateInterval = 10000;

// ---------- GUI ----------
static void close_detail_cb(lv_event_t * e);
static void show_log_detail(lv_event_t * e);
static void create_counters();
static void create_log_buttons();
static void show_error(const char* message);
static void parseLogs(const String& jsonString);
void fetchLogs();

// ===============================================================
// =============== LVGL SETUP ====================================
// ===============================================================
void lv_my_setup() {
  lv_obj_t *label = lv_label_create(lv_screen_active());
  lv_label_set_text(label, "Connecting Wi-Fi...");
  lv_obj_center(label);

  WiFi.begin(ssid, password);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(300);
    lv_label_set_text(label, "Connecting...");
  }

  if (WiFi.status() == WL_CONNECTED) {
    lv_label_set_text(label, "Wi-Fi Connected!");
    delay(500);
    lv_obj_clean(lv_screen_active());
    fetchLogs();
  } else {
    show_error("Wi-Fi connection failed!");
  }
}

// ===============================================================
// ================= GUI FUNCTIONS ================================
// ===============================================================

static void close_detail_cb(lv_event_t * e) {
  if (detail_window) {
    lv_obj_delete(detail_window);
    detail_window = nullptr;
  }
}

static void show_log_detail(lv_event_t * e) {
  int index = (int)(uintptr_t)lv_event_get_user_data(e);
  LogEntry log = logs[index];

  if (detail_window) lv_obj_delete(detail_window);
  detail_window = lv_obj_create(lv_layer_top());
  lv_obj_set_size(detail_window, 400, 300);
  lv_obj_center(detail_window);

  lv_obj_t * label = lv_label_create(detail_window);
  String text =
    "ID: " + String(log.id) + "\n" +
    "IP: " + log.ip_address + "\n" +
    "Time:\n" + log.timestamp + "\n" +
    "CPU: " + String(log.cpu_load) + "%\n" +
    "RAM: " + String(log.ram_usage) + "%\n" +
    "Temp: " + String(log.temperature) + "°C\n" +
    "Msg:\n" + log.log_message;
  lv_label_set_text(label, text.c_str());
  lv_obj_align(label, LV_ALIGN_TOP_LEFT, 10, 10);

  lv_obj_t * close_btn = lv_button_create(detail_window);
  lv_obj_set_size(close_btn, 100, 40);
  lv_obj_align(close_btn, LV_ALIGN_BOTTOM_MID, 0, -10);
  lv_obj_add_event_cb(close_btn, close_detail_cb, LV_EVENT_CLICKED, NULL);

  lv_obj_t * close_label = lv_label_create(close_btn);
  lv_label_set_text(close_label, "Close");
  lv_obj_center(close_label);
}

static void create_counters() {
  lv_obj_t *label;

  lv_obj_t * box1 = lv_obj_create(lv_screen_active());
  lv_obj_set_size(box1, 120, 40);
  lv_obj_align(box1, LV_ALIGN_TOP_RIGHT, -10, 10);
  label = lv_label_create(box1);
  lv_label_set_text_fmt(label, "1m:\n%d", count_1);
  lv_obj_center(label);

  lv_obj_t * box15 = lv_obj_create(lv_screen_active());
  lv_obj_set_size(box15, 120, 40);
  lv_obj_align(box15, LV_ALIGN_TOP_RIGHT, -10, 60);
  label = lv_label_create(box15);
  lv_label_set_text_fmt(label, "15m:\n%d", count_15);
  lv_obj_center(label);

  lv_obj_t * box60 = lv_obj_create(lv_screen_active());
  lv_obj_set_size(box60, 120, 40);
  lv_obj_align(box60, LV_ALIGN_TOP_RIGHT, -10, 110);
  label = lv_label_create(box60);
  lv_label_set_text_fmt(label, "60m:\n%d", count_60);
  lv_obj_center(label);
}

static void show_error(const char* message) {
  lv_obj_clean(lv_screen_active());
  lv_obj_t* msg_box = lv_obj_create(lv_screen_active());
  lv_obj_set_size(msg_box, 300, 200);
  lv_obj_center(msg_box);
  lv_obj_t* label = lv_label_create(msg_box);
  lv_label_set_text(label, message);
  lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(label, 260);
  lv_obj_center(label);
}

static void create_log_buttons() {
  lv_obj_t * scr = lv_screen_active();
  if (!detail_window) lv_obj_clean(scr);
  for (int i = 0; i < logCount; i++) {
    lv_obj_t * btn = lv_button_create(scr);
    lv_obj_align(btn, LV_ALIGN_TOP_LEFT, 10, 10 + i * 45);
    lv_obj_set_size(btn, 300, 40);
    lv_obj_add_event_cb(btn, show_log_detail, LV_EVENT_CLICKED, (void*)(uintptr_t)i);
    String text = "ID:" + String(logs[i].id) + " IP:" + logs[i].ip_address;
    lv_obj_t * label = lv_label_create(btn);
    lv_label_set_text(label, text.c_str());
    lv_obj_center(label);
  }
}

// ===============================================================
// ================= JSON + HTTP ================================
// ===============================================================
static void parseLogs(const String& jsonString) {
  StaticJsonDocument<5120> doc;
  auto error = deserializeJson(doc, jsonString);
  if (error) { Serial.println(error.c_str()); return; }

  JsonObject counts = doc["counts"];
  count_1  = counts["1"]  | 0;
  count_15 = counts["15"] | 0;
  count_60 = counts["60"] | 0;

  JsonArray arr = doc["logs"];
  logCount = min((int)arr.size(), MAX_LOGS);
  for (int i = 0; i < logCount; i++) {
    JsonObject o = arr[i];
    logs[i].id           = o["id"];
    logs[i].timestamp    = o["timestamp"].as<const char*>();
    logs[i].ip_address   = o["ip_address"].as<const char*>();
    logs[i].cpu_load     = o["cpu_load"]     | 0.0;
    logs[i].ram_usage    = o["ram_usage"]    | 0.0;
    logs[i].temperature  = o["temperature"]  | 0.0;
    logs[i].log_message  = o["log_message"].as<const char*>();
  }

  create_log_buttons();
  create_counters();
}

void fetchLogs() {
  if (WiFi.status() != WL_CONNECTED) {
    show_error("Wi-Fi not connected");
    return;
  }
  HTTPClient http;
  http.begin(log_url);
  int httpCode = http.GET();
  if (httpCode == 200) {
    parseLogs(http.getString());
  } else {
    String msg = "HTTP error " + String(httpCode);
    show_error(msg.c_str());
  }
  http.end();
}

// ===============================================================
// ================= LOOP REFRESH ================================
// ===============================================================
void lv_my_loop() {
  if (!detail_window && millis() - lastUpdate > updateInterval) {
    fetchLogs();
    lastUpdate = millis();
  }
}
