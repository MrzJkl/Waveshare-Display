"""Firmware defaults for the whole application.

Everything here can be edited and reflashed. A curated subset can also be
changed while the display runs, through the web page; see app/shared/config.py.
Credentials are not part of this file, they come from local_config.py on the
device filesystem.
"""

MATRIX_WIDTH = 64
MATRIX_HEIGHT = 32
SCAN_ROWS = 16

DATA_BASE_PIN = 0
R1_PIN = DATA_BASE_PIN + 0
G1_PIN = DATA_BASE_PIN + 1
B1_PIN = DATA_BASE_PIN + 2
R2_PIN = DATA_BASE_PIN + 3
G2_PIN = DATA_BASE_PIN + 4
B2_PIN = DATA_BASE_PIN + 5

ROWSEL_BASE_PIN = 6
ROWSEL_N_PINS = 4
CLK_PIN = 11
LAT_PIN = 12
OE_PIN = 13

# Time budget per row (us), split between the lit and the dark phase. Sets the
# refresh rate: 16 rows * (32 us + ~4.6 us) is about 1.7 kHz.
ON_TIME_US = 32

# Display on or off. "Off" means brightness zero: the scan engine keeps
# running, the panel is dark and switching back on is instant. Switchable from
# the web page and through the /on, /off and /toggle webhooks.
DISPLAY_ON = True

# Perceived brightness 0.0..1.0, mapped through BRIGHTNESS_GAMMA to a linear
# duty cycle so that ramps (fade_to) look even.
BRIGHTNESS = 1.0
BRIGHTNESS_GAMMA = 2.2
FADE_STEP_MS = 16

# Native scan engine (PIO + DMA, runs without the CPU).
# The timings match the Waveshare/JuPfu reference driver.
NATIVE_PIO_CLKDIV = 2.0        # PIO clock = system clock / clkdiv (250 MHz / 2), cf. SM_CLOCKDIV_FACTOR
NATIVE_CLK_HALF_CYCLES = 4     # PIO cycles per CLK half period -> pixel clock 125 MHz / 8 = 15.6 MHz
NATIVE_OE_GUARD_NS = 60        # blanking before the latch pulse (BASE_OE_NS)
NATIVE_LATCH_NS = 120          # latch pulse width and latch settle (BASE_LATCH_NS)
NATIVE_ADDR_NS = 200           # settle after a row address change, before OE (BASE_ADDR_NS)

# Main loop: the panel refreshes itself, so the loop sleeps until the next
# drawing moment, at most LOOP_MAX_SLEEP_MS.
LOOP_MAX_SLEEP_MS = 50
# Hardware watchdog: reboots the board if the main loop hangs. 0 = off,
# otherwise 1000..8300 ms (the RP2350 limit). 8000 is a good value for
# unattended operation. Careful while developing: once armed, the board also
# reboots whenever mpremote interrupts main.py, tools/run_demo.sh included.
WATCHDOG_MS = 0
WIDGET_ROTATE_MS = 15000       # widget change; 0 shows only the first widget
TRANSITION_MS = 400            # fade out and in on a widget change; 0 is a hard cut
# Widgets in the rotation (names from app/widgets); empty means all of them. A
# widget can also hide itself, see is_ready() in app/widgets/base.py.
WIDGETS_ENABLED = ("clock", "weather", "dwd", "bus", "pegel")

# Small web server for changing options while running (app/shared/web.py).
# No authentication: anybody on the network can change colours and reboot.
WEB_ENABLED = True
WEB_PORT = 80

WIFI_RETRY_MS = 15000
WLAN_PM_PERF = 0xA11140

# Time: non-blocking SNTP client, see app/shared/timesync.py.
TIMEZONE = "Europe/Berlin"     # zones in app/shared/timezone.py
NTP_HOSTS = ("192.168.178.1", "pool.ntp.org", "time.cloudflare.com")
NTP_PORT = 123
NTP_SAMPLES = 3                # samples per sync; the one with the shortest round trip wins
NTP_TIMEOUT_MS = 1500
NTP_MAX_DELAY_MS = 500         # replies with a longer round trip are discarded
NTP_RETRY_MS = 30000           # after a failed sync (then the next server)
NTP_RESYNC_MS = 60 * 60 * 1000
TIME_STALE_MS = 6 * 60 * 60 * 1000   # after this the clock turns its date line yellow

CPU_FREQ_HZ = 250_000_000

# Text widgets
TEXT_SCALE = 2
TEXT_COLOR = 7   # colour index: bit 0 red, bit 1 green, bit 2 blue, so 7 = white

# Weather widget: a Home Assistant weather entity (DWD here)
WEATHER_ENTITY = "weather.bonn_friesdorf"
WEATHER_TEMP_COLOR = 7         # white
WEATHER_HUMIDITY_COLOR = 6     # cyan
WEATHER_WIND_COLOR = 7         # white

# Bus widget: Home Assistant departure sensors (one entity per line and direction)
BUS_ENTITIES = (
    "sensor.bonn_endenich_euskirchener_str_606_bonn_ramersdorf",
    "sensor.bonn_endenich_euskirchener_str_607_bonn_ramersdorf",
    "sensor.bonn_endenich_euskirchener_str_608_bonn_holzlar_gielgen",
    "sensor.bonn_endenich_euskirchener_str_609_bonn_holzlar_gielgen",
    "sensor.bonn_endenich_euskirchener_str_n2_bonn_hbf",
    "sensor.bonn_endenich_euskirchener_str_n6_bonn_hbf",
)
BUS_ROWS = 4
# Line number colours as on the real departure boards. (1, 3) is a red/yellow
# checkerboard, which reads as orange.
BUS_LINE_COLORS = {"606": 2, "607": 2, "608": (1, 3), "609": (1, 3), "N2": 7, "N6": 7}
BUS_LINE_COLOR = 7             # white, for lines missing from BUS_LINE_COLORS
BUS_MINUTES_COLOR = 7          # white
BUS_DELAY_RED_MIN = 5          # delay in minutes from which it turns red instead of yellow

# River level widget: water level from Home Assistant (cm), animated water surface
PEGEL_ENTITY = "sensor.rhein_pegel_bonn_wasserstand"
PEGEL_MIN_CM = 0               # bottom of the scale (no water in the picture)
PEGEL_MAX_CM = 800             # top of the scale (full picture); keeps both marks visible
# Flood marks: dashed lines in the picture and the colour of the number.
# Check the values for your gauge (source: PEGELONLINE / HochwasserPortal).
PEGEL_WARN_CM = 620            # yellow mark, number turns yellow from here
PEGEL_ALARM_CM = 750           # red mark, number turns red and blinks from here
PEGEL_TREND_WINDOW_MS = 3 * 60 * 60 * 1000   # window for the trend arrow
PEGEL_TREND_MIN_CM = 2         # change from which the level counts as rising or falling
PEGEL_WAVE_MS = 160            # step of the wave animation
PEGEL_WATER_COLOR = 4          # blue
PEGEL_SURFACE_COLOR = 6        # cyan
PEGEL_NUMBER_COLOR = 7         # white

# DWD warning level widget: two Home Assistant sensors (current level and advance notice)
DWD_CURRENT_ENTITY = "sensor.stadt_bonn_aktuelle_warnstufe"
DWD_PREWARN_ENTITY = "sensor.stadt_bonn_vorwarnstufe"
DWD_ALWAYS_SHOW = False        # True also shows level 0 ("KEINE WARNUNG")
DWD_BLINK_LEVEL = 3            # the warning triangle blinks from this level up
# DWD levels: 1 yellow, 2 orange, 3 red, 4 dark red. The panel has neither
# orange nor dark red: (1, 3) is a red/yellow checkerboard, level 4 is magenta.
DWD_LEVEL_COLORS = {1: 3, 2: (1, 3), 3: 1, 4: 5}
DWD_OK_COLOR = 2               # green for "no warning"
DWD_TEXT_COLOR = 7             # white

# Clock widget. The weekday abbreviations are the panel text, German by default.
CLOCK_TIME_COLOR = 7           # white
CLOCK_DATE_COLOR = 1           # red (yellow when the last time sync is older than TIME_STALE_MS)
CLOCK_WEEKDAYS = ("MO", "DI", "MI", "DO", "FR", "SA", "SO")

# Home Assistant over MQTT (Mosquitto + mqtt_statestream), see app/shared/mqtt.py and hass.py.
MQTT_CLIENT_ID = "led-display"
MQTT_KEEPALIVE_S = 60
MQTT_RECONNECT_MS = 5000       # first retry delay, doubles up to MQTT_RECONNECT_MAX_MS
MQTT_RECONNECT_MAX_MS = 60000
MQTT_CONNECT_TIMEOUT_S = 3     # bounds how long one connect attempt can stall the loop
HASS_BASE_TOPIC = "statestream"  # base_topic of mqtt_statestream in Home Assistant

# Credentials come from local_config.py on the device filesystem, not from the firmware.
try:
    import local_config as _local
except ImportError:
    _local = None
WIFI_SSID = getattr(_local, "WIFI_SSID", "")
WIFI_PASSWORD = getattr(_local, "WIFI_PASSWORD", "")
MQTT_HOST = getattr(_local, "MQTT_HOST", "")       # empty disables MQTT
MQTT_PORT = getattr(_local, "MQTT_PORT", 1883)
MQTT_USER = getattr(_local, "MQTT_USER", "")
MQTT_PASSWORD = getattr(_local, "MQTT_PASSWORD", "")

# Last: options changed at runtime through the web server override the defaults
# above (settings_override.json on the device, see app/shared/config.py).
try:
    from app.shared import config as _config
    _config.apply(globals())
except Exception as _exc:      # the application still starts without overrides
    print("settings: overrides not applied:", _exc)
