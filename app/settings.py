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

# Hauptschleife: das Panel refresht sich selbst, der Loop schlaeft bis zum
# naechsten Zeichenzeitpunkt, hoechstens LOOP_MAX_SLEEP_MS.
LOOP_MAX_SLEEP_MS = 50
WIDGET_ROTATE_MS = 15000       # Widget-Wechsel; 0 = nur das erste Widget zeigen
TRANSITION_MS = 400            # Aus-/Einblenden beim Widget-Wechsel; 0 = hart
DATA_REFRESH_MS = 6000

WIFI_RETRY_MS = 15000
WLAN_PM_PERF = 0xA11140

# Zeit: nicht blockierender SNTP-Client, siehe app/timesync.py.
TIMEZONE = "Europe/Berlin"     # Zonen in app/timezone.py
NTP_HOSTS = ("192.168.178.1", "pool.ntp.org", "time.cloudflare.com")
NTP_PORT = 123
NTP_SAMPLES = 3                # Messungen pro Sync, die mit der kleinsten Laufzeit gewinnt
NTP_TIMEOUT_MS = 1500
NTP_MAX_DELAY_MS = 500         # Antworten mit groesserer Laufzeit werden verworfen
NTP_RETRY_MS = 30000           # nach fehlgeschlagenem Sync (dann naechster Server)
NTP_RESYNC_MS = 60 * 60 * 1000
TIME_STALE_MS = 6 * 60 * 60 * 1000   # danach zeigt die Uhr die Datumszeile gelb

CPU_FREQ_HZ = 250_000_000

# Text-Widgets
TEXT_SCALE = 2
TEXT_COLOR = 7   # Farbindex: Bit 0 rot, Bit 1 gruen, Bit 2 blau -> 7 = weiss

# Uhr-Widget
CLOCK_TIME_COLOR = 7           # weiss
CLOCK_DATE_COLOR = 1           # rot (gelb, wenn der letzte Zeitabgleich aelter als TIME_STALE_MS ist)
CLOCK_WEEKDAYS = ("MO", "DI", "MI", "DO", "FR", "SA", "SO")

try:
    from wifi_config import WIFI_PASSWORD, WIFI_SSID
except ImportError:
    WIFI_SSID = ""
    WIFI_PASSWORD = ""
