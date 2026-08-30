#include "pico/stdlib.h"

#include <cstdio>
#include <cstring>
#include <ctime>

// Pico W devices use a GPIO on the WIFI chip for the LED,
// so when building for Pico W, CYW43_WL_GPIO_LED_PIN will be defined
#if defined(CYW43_WL_GPIO_LED_PIN) && __has_include("pico/cyw43_arch.h") && __has_include("lwip/apps/sntp.h")
#define HUB75_HAS_WIFI 1
#include "pico/cyw43_arch.h"
#include "lwip/apps/sntp.h"
#else
#define HUB75_HAS_WIFI 0
#endif

#include "hardware/clocks.h"

#include "hub75.hpp"

#if HUB75_MULTICORE == true
#include "pico/multicore.h"
#endif

#if USE_PICO_GRAPHICS == true
using namespace pimoroni;
#endif

static_assert(DISPLAY_WIDTH == 64 && DISPLAY_HEIGHT == 32,
              "This application is configured for a fixed 64x32 panel.");

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#ifndef WIFI_AUTH
#if HUB75_HAS_WIFI
#define WIFI_AUTH CYW43_AUTH_WPA2_AES_PSK
#else
#define WIFI_AUTH 0
#endif
#endif

#ifndef NTP_SERVER
#define NTP_SERVER "fritz.box"
#endif

constexpr time_t MIN_VALID_UNIX_TIME = 1700000000;
constexpr uint32_t VIEW_SWITCH_MS = 10000;
constexpr bool ENABLE_VIEW_ROTATION = false;

enum class ViewId : uint8_t
{
    Clock = 0,
    Weather,
    HomeAssistant,
    Nina,
    Count
};

struct AppState
{
    bool wifi_supported = HUB75_HAS_WIFI;
    bool wifi_connected = false;
    int wifi_error = 0;
    bool time_synced = false;
    time_t now = 0;
};

static void format_wifi_error_text(char *out, size_t out_size, int wifi_error)
{
    int code = wifi_error;
    if (code < 0)
    {
        code = -code;
    }
    std::snprintf(out, out_size, "E%03d", code);
}

// Perform initialisation
int pico_led_init(void)
{
#if defined(PICO_DEFAULT_LED_PIN)
    // A device like Pico that uses a GPIO for the LED will define PICO_DEFAULT_LED_PIN
    // so we can use normal GPIO functionality to turn the led on and off
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
    return PICO_OK;
#elif HUB75_HAS_WIFI
    // For Pico W devices we need to initialise the driver etc
    return cyw43_arch_init();
#else
    return PICO_OK;
#endif
}

// Turn the led on or off
void pico_set_led(bool led_on)
{
#if defined(PICO_DEFAULT_LED_PIN)
    // Just set the GPIO on or off
    gpio_put(PICO_DEFAULT_LED_PIN, led_on);
#elif HUB75_HAS_WIFI
    // Ask the wifi "driver" to set the GPIO on or off
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, led_on);
#endif
}

// Pico - please, blink LED when program starts
int led_init(void)
{
    int rc = pico_led_init(); // Initialize the LED
    hard_assert(rc == PICO_OK);

    for (int i = 0; i < 8; i++)
    {
        pico_set_led(true);
        sleep_ms(250); // Wait 250ms
        pico_set_led(false);
        sleep_ms(250); // Wait 250ms
    }
    return PICO_OK;
}

#if USE_PICO_GRAPHICS == true
class DigitalClockDisplay : public PicoGraphics_PenRGB888
{
private:
    Pen bg;
    Pen fg;
    Pen accent;

    int last_second = -1;
    bool colon_on = true;

public:
    DigitalClockDisplay(uint width, uint height) : PicoGraphics_PenRGB888(width, height, nullptr)
    {
        bg = create_pen(0, 0, 0);
        fg = create_pen(235, 244, 255);
        accent = create_pen(120, 220, 160);
        set_font(&font8);
    }

    void draw_waiting(const char *msg)
    {
        char short_msg[13];
        std::snprintf(short_msg, sizeof(short_msg), "%.12s", msg);

        set_pen(bg);
        clear();
        set_pen(fg);
        text("WiFi/NTP", Point(2, 1), false, 0.7f, 0.0f, false);
        set_pen(accent);
        text(short_msg, Point(2, 21), false, 0.7f, 0.0f, false);
    }

    void draw_time(time_t now)
    {
        struct tm local_tm;
        localtime_r(&now, &local_tm);

        if (local_tm.tm_sec == last_second)
        {
            return;
        }

        last_second = local_tm.tm_sec;
        colon_on = !colon_on;

        char line[9];
        std::snprintf(line, sizeof(line), "%02d%c%02d", local_tm.tm_hour, colon_on ? ':' : ' ', local_tm.tm_min);

        char sec[3];
        std::snprintf(sec, sizeof(sec), "%02d", local_tm.tm_sec);

        set_pen(bg);
        clear();

        set_pen(fg);
        text(line, Point(2, 3), false, 1.3f, 0.0f, false);

        set_pen(accent);
        text(sec, Point(DISPLAY_WIDTH - 12, DISPLAY_HEIGHT - 8), false, 0.7f, 0.0f, false);
    }

    void draw_info_page(const char *title, const char *line1, const char *line2)
    {
        set_pen(bg);
        clear();

        set_pen(fg);
        text(title, Point(2, 1), false, 0.7f, 0.0f, false);

        set_pen(accent);
        text(line1, Point(2, 12), false, 0.7f, 0.0f, false);
        text(line2, Point(2, 21), false, 0.7f, 0.0f, false);
    }
};
#endif

/**
 * @brief Secondary core entry point.
 *
 * Initializes and starts the HUB75 driver on core 1.
 */
void core1_entry()
{
    create_hub75_driver(DISPLAY_WIDTH, DISPLAY_HEIGHT, PANEL_TYPE, INVERTED_STB);
    start_hub75_driver();

    // KEEP CORE 1 ALIVE — without this, Core 1's NVIC is torn down and DMA_IRQ_1 stops firing
    //
    // Add your additional tasks for core1 here
    while (true)
    {
        tight_loop_contents();
    }
}

void initialize()
{
    // Set system clock to 250MHz - just to show that it is possible to drive the HUB75 panel with a high clock speed
    set_sys_clock_khz(266000, true);

    stdio_init_all(); // Initialize Pico SDK

    led_init(); // Initialize LED - blinking at program start

#if HUB75_MULTICORE == true
    // Run hub75 driver on core1
    multicore_reset_core1();             // Reset core 1
    multicore_launch_core1(core1_entry); // Launch core 1 entry function - the Hub75 driver is doing its job there
#else
    // Run hub75 on core0 - the Hub75 driver is doing its job here
    create_hub75_driver(DISPLAY_WIDTH, DISPLAY_HEIGHT, PANEL_TYPE, INVERTED_STB);
    start_hub75_driver();
#endif
}

#if HUB75_HAS_WIFI
static int connect_wifi()
{
    if (std::strlen(WIFI_SSID) == 0u || std::strlen(WIFI_PASSWORD) == 0u)
    {
        printf("WIFI creds missing (WIFI_SSID / WIFI_PASSWORD).\n");
        return -100;
    }

    cyw43_arch_enable_sta_mode();
    printf("Connecting to Wi-Fi (ssid-len=%u, pass-len=%u)...\n",
           (unsigned)std::strlen(WIFI_SSID),
           (unsigned)std::strlen(WIFI_PASSWORD));

    int rc = cyw43_arch_wifi_connect_timeout_ms(WIFI_SSID, WIFI_PASSWORD, WIFI_AUTH, 30000);
    if (rc != 0)
    {
        printf("Wi-Fi connect failed: %d\n", rc);
        return rc;
    }

    printf("Wi-Fi connected.\n");
    return 0;
}

static void start_sntp()
{
    sntp_setoperatingmode(SNTP_OPMODE_POLL);
#if defined(SNTP_SERVER_DNS) && (SNTP_SERVER_DNS)
    sntp_setservername(0, NTP_SERVER);
#else
    printf("SNTP hostname DNS support is disabled in lwipopts.h\n");
#endif
    sntp_init();
    printf("SNTP started, server: %s\n", NTP_SERVER);
}

static bool wait_for_time_sync(uint32_t timeout_ms)
{
    const absolute_time_t deadline = make_timeout_time_ms(timeout_ms);

    while (!time_reached(deadline))
    {
        const time_t now = time(nullptr);
        if (now > MIN_VALID_UNIX_TIME)
        {
            return true;
        }
        sleep_ms(200);
    }
    return false;
}
#endif

int main()
{
    initialize();

    float hz = 20.0f;
    float ms = 1000.0f / hz;

    // set basis brightness of matrix panel
    setBasisBrightness(8);

    // set full brightness of panel
    setIntensity(1.0f);

#if USE_PICO_GRAPHICS == true
    DigitalClockDisplay clockView(DISPLAY_WIDTH, DISPLAY_HEIGHT);
#endif

    AppState app;

#if HUB75_HAS_WIFI
    const char *tz = "CET-1CEST,M3.5.0/2,M10.5.0/3";
    setenv("TZ", tz, 1);
    tzset();

#if USE_PICO_GRAPHICS == true
    clockView.draw_waiting("Connecting");
    update(&clockView);
#endif

    int wifi_rc = connect_wifi();
    bool wifi_ok = wifi_rc == 0;
    app.wifi_error = wifi_rc;
    app.wifi_connected = wifi_ok;
    if (wifi_ok)
    {
        start_sntp();
    }
#if USE_PICO_GRAPHICS == true
    else
    {
        char wifi_msg[13];
        format_wifi_error_text(wifi_msg, sizeof(wifi_msg), app.wifi_error);
        clockView.draw_waiting(wifi_msg);
        update(&clockView);
    }
#endif
#else
    printf("Wi-Fi support unavailable in this SDK build; showing fallback clock.\n");
#endif

    ViewId last_view = ViewId::Count;

    while (true)
    {
        const uint32_t now_ms = to_ms_since_boot(get_absolute_time());
        ViewId view = ViewId::Clock;
        if (ENABLE_VIEW_ROTATION)
        {
            view = static_cast<ViewId>((now_ms / VIEW_SWITCH_MS) % static_cast<uint32_t>(ViewId::Count));
        }

#if USE_PICO_GRAPHICS == true
#if HUB75_HAS_WIFI
        app.now = time(nullptr);
        app.time_synced = app.now > MIN_VALID_UNIX_TIME;

        if (!app.time_synced)
        {
            if (app.wifi_connected)
            {
                clockView.draw_waiting("Syncing NTP");
            }
            else
            {
                char wifi_msg[13];
                format_wifi_error_text(wifi_msg, sizeof(wifi_msg), app.wifi_error);
                clockView.draw_waiting(wifi_msg);
            }
            if (wait_for_time_sync(200))
            {
                app.now = time(nullptr);
                app.time_synced = app.now > MIN_VALID_UNIX_TIME;
            }
        }
#else
        app.now = time(nullptr);
        app.time_synced = true;
#endif

        if (view == ViewId::Clock)
        {
            if (app.time_synced)
            {
                clockView.draw_time(app.now);
            }
            else
            {
                if (app.wifi_connected)
                {
                    clockView.draw_waiting("Syncing NTP");
                }
                else
                {
                    char wifi_msg[13];
                    format_wifi_error_text(wifi_msg, sizeof(wifi_msg), app.wifi_error);
                    clockView.draw_waiting(wifi_msg);
                }
            }
        }
        else if (view == ViewId::Weather)
        {
            if (view != last_view)
            {
                clockView.draw_info_page("Wetter", "TODO", "MQTT/HA");
            }
        }
        else if (view == ViewId::HomeAssistant)
        {
            if (view != last_view)
            {
                clockView.draw_info_page("HomeAssistant", "TODO", "Sensoren");
            }
        }
        else
        {
            if (view != last_view)
            {
                clockView.draw_info_page("NINA", "TODO", "Warnungen");
            }
        }

        last_view = view;
        update(&clockView);
#endif

        sleep_ms(ms);
    }
}
