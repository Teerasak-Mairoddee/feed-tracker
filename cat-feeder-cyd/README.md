# Cat feeder wall panel (CYD / ESP32-2432S028R)

A little always-on touchscreen that shows whether Goobie & Coco have had their morning and
evening meal, and lets anyone tap a meal and pick their name to log it. It reads live from the
Orange Pi (`http://192.168.1.60:8000`) over your home wifi.

## What it shows
- Header with the cats' name and a small **green/red pip** (green = talking to the Pi, red = can't reach it).
- Two cards, **Morning** and **Evening**, each with a status dot:
  - **green** fed (shows "fed")
  - **amber** due soon
  - **red** overdue
  - **grey** not due yet
- An unfed meal has a green **FEED** button. Tap it, pick who fed from the five names, done. It
  posts straight to the Pi, so the web app and the panel always agree.

It polls the Pi every 15 seconds, so if someone logs a meal on their phone the panel catches up on its own.

---

## 1. Install the Arduino IDE + ESP32 support
1. Install the **Arduino IDE** (2.x).
2. File > Preferences > *Additional boards manager URLs*, add:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Tools > Board > Boards Manager, search **esp32** (by Espressif), install it.
4. Tools > Board > ESP32 Arduino > **ESP32 Dev Module**.

## 2. Install the three libraries
Sketch > Include Library > Manage Libraries, install:
- **TFT_eSPI** (by Bodmer)
- **XPT2046_Touchscreen** (by Paul Stoffregen)
- **ArduinoJson** (by Benoit Blanchon) - version 7.x

## 3. Point TFT_eSPI at the CYD (the important bit)
TFT_eSPI needs to know the exact pins or you'll get a white or garbled screen. Replace its
`User_Setup.h` with the one in this folder:

- Find your libraries folder (Arduino IDE > File > Preferences shows the *Sketchbook location*;
  libraries are in `<sketchbook>/libraries/TFT_eSPI/`).
- Copy **`User_Setup.h`** from this folder into `TFT_eSPI/`, overwriting the one there.
  (Back up the original first if you like.)

That's the single most common reason a CYD screen looks wrong, so don't skip it.

## 4. Fill in your wifi
Open **`cat_feeder_cyd.ino`** and edit the block near the top:
```c
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* PI_HOST   = "192.168.1.60";   // leave unless the Pi's IP changed
const int   PI_PORT   = 8000;
```
Note: the ESP32 only joins **2.4 GHz** wifi, not 5 GHz. On a BT Hub the 2.4 and 5 GHz networks
usually share one name, which is fine - it'll pick the 2.4 GHz band.

## 5. Flash it
1. Plug the CYD into your PC with a USB data cable (not a charge-only one).
2. Tools > Port, pick the COM port that appears.
3. Click **Upload**. If it hangs at "Connecting...", hold the **BOOT** button on the board while it starts, then release.
4. The screen shows "Connecting to wifi..." then the two meal cards. Tap FEED to test, and check
   the web app updates.

---

## Make sure the Pi app is up to date
The panel needs the `/api/status` and `/api/feed` endpoints, which are in the current `app.py`
(cat-feeder-app folder). If you haven't deployed that version yet:
```
scp app.py tee@192.168.1.60:/opt/catfeeder/app.py
ssh tee@192.168.1.60 'sudo systemctl restart catfeeder'
```

## If colours are inverted (white background instead of dark)
Some CYD batches invert the ILI9341 colours, so the dark theme shows as white-on-black. The sketch
already calls `tft.invertDisplay(true);` in `setup()` to correct it. If *your* board shows up
inverted the other way (white when it should be dark), flip that to `tft.invertDisplay(false);`
and re-upload.

## If taps land in the wrong place
Touch calibration varies slightly per board. In `cat_feeder_cyd.ino`, `getTouch()` maps the raw
touch range with:
```c
sx = map(p.x, 200, 3700, 0, 320);
sy = map(p.y, 240, 3800, 0, 240);
```
If a tap registers offset, nudge those min/max numbers (e.g. 200 -> 300). A quick way to find your
board's real range is to `Serial.println(p.x); Serial.println(p.y);` inside `getTouch()` and watch
the Serial Monitor while you tap the corners.

## Power it as a wall panel
Once flashed it needs no PC - any 5V USB phone charger into the board's USB port runs it. Mount it
wherever the cats get fed and it'll stay in sync with everyone's phones.
