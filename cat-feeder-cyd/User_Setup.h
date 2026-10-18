// TFT_eSPI setup for the ESP32-2432S028R "Cheap Yellow Display" (2.8" ILI9341).
// Replace the User_Setup.h in your TFT_eSPI library folder with this file
// (see README.md for exactly where that is), then rebuild.

#define USER_SETUP_INFO "CYD ESP32-2432S028R"

#define ILI9341_2_DRIVER      // the CYD panel (note the _2 variant; plain ILI9341 shows wrong colours on some units)

// Display SPI pins (CYD wiring - do not change)
#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST  -1           // tied to EN, no dedicated reset pin
#define TFT_BL   21           // backlight
#define TFT_BACKLIGHT_ON HIGH

// Fonts
#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define LOAD_FONT6
#define LOAD_FONT7
#define LOAD_FONT8
#define LOAD_GFXFF
#define SMOOTH_FONT

// SPI speed
#define SPI_FREQUENCY       55000000
#define SPI_READ_FREQUENCY  20000000
#define SPI_TOUCH_FREQUENCY  2500000

// NOTE: touch (XPT2046) is driven by the XPT2046_Touchscreen library on a
// separate SPI bus in the sketch, NOT through TFT_eSPI, so no TOUCH_CS here.
