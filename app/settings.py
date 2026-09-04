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

# Zeitbudget pro Zeile (us), das zwischen Leucht- und Dunkelphase aufgeteilt
# wird. Bestimmt die Bildwiederholrate: 16 Zeilen * (32 us + ~4.6 us) -> ca. 1.7 kHz.
ON_TIME_US = 32

# Helligkeit 0.0..1.0 (wahrgenommen). Wird mit BRIGHTNESS_GAMMA in eine lineare
# Leuchtdauer umgerechnet, damit Rampen (fade_to) gleichmaessig wirken.
BRIGHTNESS = 1.0
BRIGHTNESS_GAMMA = 2.2
FADE_STEP_MS = 16

# Native Scan-Engine (PIO + DMA, laeuft ohne CPU-Beteiligung).
# Timing-Werte entsprechen dem Waveshare/JuPfu-Referenztreiber.
NATIVE_PIO_CLKDIV = 2.0        # PIO-Takt = CPU-Takt / clkdiv (250 MHz / 2 = 125 MHz), vgl. SM_CLOCKDIV_FACTOR
NATIVE_CLK_HALF_CYCLES = 4     # PIO-Zyklen pro CLK-Halbperiode -> Pixeltakt 125 MHz / 8 = 15.6 MHz
NATIVE_OE_GUARD_NS = 60        # Dunkelphase vor dem Latch (BASE_OE_NS)
NATIVE_LATCH_NS = 120          # Latch-Pulsbreite und Latch-Settle (BASE_LATCH_NS)
NATIVE_ADDR_NS = 200           # Settle nach Zeilenadresswechsel vor OE (BASE_ADDR_NS)

# Hauptschleife: das Panel refresht sich selbst, der Loop schlaeft zwischen
# den Service-Laeufen.
LOOP_IDLE_MS = 50
SERVICE_INTERVAL_MS = 250
MODULE_ROTATE_MS = 15000
DATA_REFRESH_MS = 6000

WIFI_RETRY_MS = 15000
NTP_RETRY_MS = 60000
NTP_RESYNC_MS = 60 * 60 * 1000
NTP_TIMEOUT_S = 0.1

CPU_FREQ_HZ = 250_000_000
WLAN_PM_PERF = 0xA11140

TEXT_SCALE = 2
UTC_OFFSET_HOURS = 2

NTP_HOST = "192.168.178.1"
NTP_PORT = 123
NTP_DELTA = 2208988800

try:
    from wifi_config import WIFI_PASSWORD, WIFI_SSID
except ImportError:
    WIFI_SSID = ""
    WIFI_PASSWORD = ""
