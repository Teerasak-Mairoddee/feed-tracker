/*
  Cat feeder wall panel - ESP32-2432S028R ("Cheap Yellow Display", 2.8" ILI9341 + XPT2046 touch)

  Shows whether Goobie & Coco have had their morning and evening meal, read live from the
  Orange Pi running the cat-feeder app, and lets anyone tap a meal and pick their name to log it.

  Talks to the Pi over your home wifi:
    GET  http://PI_HOST:PI_PORT/api/status   -> today's meals + state
    POST http://PI_HOST:PI_PORT/api/feed     -> log a meal {meal, fed_by}

  Libraries needed (Arduino IDE -> Library Manager):
    - TFT_eSPI        (Bodmer)   -- use the User_Setup.h in this folder, see README
    - XPT2046_Touchscreen (Paul Stoffregen)
    - ArduinoJson     (Benoit Blanchon, v7)
  Board: "ESP32 Dev Module" (esp32 core by Espressif).
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <ArduinoJson.h>

// ===================== EDIT THESE =====================
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* PI_HOST   = "192.168.1.60";   // the Orange Pi
const int   PI_PORT   = 8000;
// ======================================================

// Touch pins (XPT2046 on its own SPI bus, standard CYD wiring)
#define XPT2046_IRQ  36
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define XPT2046_CLK  25
#define XPT2046_CS   33

// Onboard RGB LED (active LOW) - we just keep it off
#define LED_R 4
#define LED_G 16
#define LED_B 17

SPIClass touchSPI = SPIClass(VSPI);
XPT2046_Touchscreen touch(XPT2046_CS, XPT2046_IRQ);
TFT_eSPI tft = TFT_eSPI();

// Colours (match the web app)
uint16_t C_BG, C_CARD, C_TEXT, C_MUTED, C_GREEN, C_AMBER, C_RED, C_GREY, C_BTN, C_HDR;

const char* MEAL_NAMES[2] = {"Morning", "Evening"};
const char* HOUSEMATES[5] = {"Tee", "Dan", "Cole", "Liv", "Guest"};

struct Meal {
  String state;    // done / upcoming / soon / overdue
  String label;    // human text
  bool   fed;
  String fedBy;
};
Meal meals[2];
String todayStr = "";
bool   haveData = false;
bool   online   = false;

enum Screen { SCREEN_MAIN, SCREEN_PICK };
Screen screen = SCREEN_MAIN;
int    pickMeal = 0;   // which meal we are logging on the pick screen

unsigned long lastPoll = 0;
const unsigned long POLL_MS = 15000;
unsigned long lastTouch = 0;
const unsigned long TOUCH_DEBOUNCE = 350;

// ---------- touch helpers ----------
// Returns true and sets sx,sy (screen coords, 320x240) if the screen is being touched.
bool getTouch(int &sx, int &sy) {
  if (!touch.tirqTouched() || !touch.touched()) return false;
  TS_Point p = touch.getPoint();
  // Raw XPT2046 range is roughly 200..3700; tweak if taps land off (see README).
  sx = map(p.x, 200, 3700, 0, 320);
  sy = map(p.y, 240, 3800, 0, 240);
  sx = constrain(sx, 0, 319);
  sy = constrain(sy, 0, 239);
  return true;
}

uint16_t stateColour(const String &s, bool fed) {
  if (fed || s == "done") return C_GREEN;
  if (s == "soon")        return C_AMBER;
  if (s == "overdue")     return C_RED;
  return C_GREY;
}

// ---------- drawing ----------
void drawButton(int x, int y, int w, int h, const char* label, uint16_t fill, uint16_t txt) {
  tft.fillRoundRect(x, y, w, h, 8, fill);
  tft.setTextColor(txt, fill);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(label, x + w / 2, y + h / 2, 2);
}

void drawHeader(const char* title) {
  tft.fillRect(0, 0, 320, 34, C_HDR);
  tft.setTextColor(C_TEXT, C_HDR);
  tft.setTextDatum(ML_DATUM);
  tft.drawString(title, 10, 17, 4);
  // connection pip top-right
  tft.fillCircle(305, 17, 5, online ? C_GREEN : C_RED);
}

void drawMealRow(int i, int top) {
  int h = 96;
  tft.fillRoundRect(6, top, 308, h, 10, C_CARD);
  // status dot
  tft.fillCircle(34, top + h / 2, 15, stateColour(meals[i].state, meals[i].fed));
  // meal name
  tft.setTextColor(C_TEXT, C_CARD);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(MEAL_NAMES[i], 62, top + 16, 4);
  // label (small, wrap-safe: just one line)
  tft.setTextColor(C_MUTED, C_CARD);
  tft.setTextDatum(TL_DATUM);
  String lbl = meals[i].label;
  if (lbl.length() > 30) lbl = lbl.substring(0, 30);
  tft.drawString(lbl, 62, top + 52, 2);
  // FEED button if not fed
  if (!meals[i].fed) {
    drawButton(214, top + 24, 94, 48, "FEED", C_GREEN, TFT_WHITE);
  } else {
    tft.setTextColor(C_GREEN, C_CARD);
    tft.setTextDatum(MR_DATUM);
    tft.drawString("fed", 300, top + h / 2, 4);
  }
}

void drawMain() {
  screen = SCREEN_MAIN;
  tft.fillScreen(C_BG);
  drawHeader("Goobie & Coco");
  if (!haveData) {
    tft.setTextColor(C_MUTED, C_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(online ? "Loading..." : "Connecting to wifi...", 160, 120, 4);
    return;
  }
  drawMealRow(0, 42);
  drawMealRow(1, 142);
}

// pick-screen button layout: 3 cols x 2 rows (5 names + Cancel)
void pickCell(int idx, int &x, int &y, int &w, int &h) {
  w = 98; h = 70;
  int col = idx % 3, row = idx / 3;
  x = 6 + col * 103;
  y = 46 + row * 82;
}

void drawPick() {
  screen = SCREEN_PICK;
  tft.fillScreen(C_BG);
  char hdr[32];
  snprintf(hdr, sizeof(hdr), "Who fed? (%s)", MEAL_NAMES[pickMeal]);
  drawHeader(hdr);
  for (int i = 0; i < 5; i++) {
    int x, y, w, h; pickCell(i, x, y, w, h);
    drawButton(x, y, w, h, HOUSEMATES[i], C_BTN, C_TEXT);
  }
  int x, y, w, h; pickCell(5, x, y, w, h);
  drawButton(x, y, w, h, "Cancel", C_RED, TFT_WHITE);
}

// ---------- network ----------
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) { online = true; return; }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(250);
  }
  online = (WiFi.status() == WL_CONNECTED);
}

bool parseStatus(const String &body) {
  JsonDocument doc;
  if (deserializeJson(doc, body)) return false;
  todayStr = doc["date"] | "";
  for (int i = 0; i < 2; i++) { meals[i].fed = false; meals[i].state = "upcoming"; meals[i].label = ""; meals[i].fedBy = ""; }
  for (JsonObject m : doc["meals"].as<JsonArray>()) {
    const char* name = m["meal"] | "";
    for (int i = 0; i < 2; i++) {
      if (strcmp(name, MEAL_NAMES[i]) == 0) {
        meals[i].state = String((const char*)(m["state"] | "upcoming"));
        meals[i].label = String((const char*)(m["label"] | ""));
        meals[i].fed   = m["fed"] | false;
        meals[i].fedBy = String((const char*)(m["fed_by"] | ""));
      }
    }
  }
  return true;
}

bool fetchStatus() {
  if (WiFi.status() != WL_CONNECTED) { connectWiFi(); if (!online) return false; }
  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + PI_HOST + ":" + PI_PORT + "/api/status";
  http.setConnectTimeout(4000);
  http.begin(client, url);
  int code = http.GET();
  bool ok = false;
  if (code == 200) ok = parseStatus(http.getString());
  http.end();
  online = (code > 0);
  if (ok) haveData = true;
  return ok;
}

bool postFeed(int mealIdx, const char* name) {
  if (WiFi.status() != WL_CONNECTED) { connectWiFi(); if (!online) return false; }
  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + PI_HOST + ":" + PI_PORT + "/api/feed";
  http.setConnectTimeout(4000);
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  JsonDocument doc;
  doc["meal"] = MEAL_NAMES[mealIdx];
  doc["fed_by"] = name;
  String body; serializeJson(doc, body);
  int code = http.POST(body);
  bool ok = (code == 200);
  if (ok) parseStatus(http.getString());
  http.end();
  online = (code > 0);
  return ok;
}

// ---------- touch handling ----------
void handleMainTouch(int x, int y) {
  if (!haveData) return;
  // FEED buttons live at x 214..308, Morning row top 42 (btn y 66..114), Evening top 142 (btn y 166..214)
  if (x >= 214 && x <= 308) {
    if (y >= 66 && y <= 114 && !meals[0].fed) { pickMeal = 0; drawPick(); return; }
    if (y >= 166 && y <= 214 && !meals[1].fed) { pickMeal = 1; drawPick(); return; }
  }
}

void handlePickTouch(int x, int y) {
  for (int i = 0; i < 6; i++) {
    int bx, by, bw, bh; pickCell(i, bx, by, bw, bh);
    if (x >= bx && x <= bx + bw && y >= by && y <= by + bh) {
      if (i == 5) { drawMain(); return; }          // Cancel
      // show a brief "logging" flash
      tft.setTextColor(C_MUTED, C_BG);
      tft.setTextDatum(BC_DATUM);
      tft.drawString("Logging...", 160, 238, 2);
      postFeed(pickMeal, HOUSEMATES[i]);
      drawMain();
      return;
    }
  }
}

// ---------- setup / loop ----------
void setup() {
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  digitalWrite(LED_R, HIGH); digitalWrite(LED_G, HIGH); digitalWrite(LED_B, HIGH); // off (active low)

  tft.init();
  tft.setRotation(1);           // landscape, 320x240
  tft.invertDisplay(true);      // many CYD panels invert ILI9341 colours; flip if yours shows white-on-black
  touchSPI.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
  touch.begin(touchSPI);
  touch.setRotation(1);

  C_BG    = tft.color565(0x18, 0x18, 0x1b);
  C_CARD  = tft.color565(0x27, 0x27, 0x2a);
  C_HDR   = tft.color565(0x3f, 0x3f, 0x46);
  C_TEXT  = tft.color565(0xf4, 0xf4, 0xf5);
  C_MUTED = tft.color565(0xa1, 0xa1, 0xaa);
  C_GREEN = tft.color565(0x16, 0xa3, 0x4a);
  C_AMBER = tft.color565(0xd9, 0x77, 0x06);
  C_RED   = tft.color565(0xdc, 0x26, 0x26);
  C_GREY  = tft.color565(0x71, 0x71, 0x7a);
  C_BTN   = tft.color565(0x3f, 0x3f, 0x46);

  drawMain();
  connectWiFi();
  fetchStatus();
  drawMain();
  lastPoll = millis();
}

void loop() {
  // poll status periodically (only on the main screen so we don't redraw a pick in progress)
  if (screen == SCREEN_MAIN && millis() - lastPoll > POLL_MS) {
    bool before = haveData;
    String s0 = meals[0].state + meals[0].fedBy, s1 = meals[1].state + meals[1].fedBy;
    fetchStatus();
    // redraw if anything changed (or first data arrived, or connection flipped)
    if (!before || s0 != meals[0].state + meals[0].fedBy || s1 != meals[1].state + meals[1].fedBy) {
      drawMain();
    } else {
      drawHeader("Goobie & Coco");  // refresh the online pip cheaply
    }
    lastPoll = millis();
  }

  int x, y;
  if (getTouch(x, y) && millis() - lastTouch > TOUCH_DEBOUNCE) {
    lastTouch = millis();
    if (screen == SCREEN_MAIN) handleMainTouch(x, y);
    else                       handlePickTouch(x, y);
  }
  delay(20);
}
