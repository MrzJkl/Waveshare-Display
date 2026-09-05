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

# Display an oder aus. "Aus" bedeutet Helligkeit null: die Scan-Engine laeuft
# weiter, das Panel ist dunkel, das Einschalten ist sofort da. Schaltbar per
# Weboberflaeche und ueber die Webhooks /on, /off und /toggle.
DISPLAY_ON = True

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
# Widgets in der Rotation (Namen aus app/widgets); leer = alle. Ein Widget kann
# sich zusaetzlich selbst ausblenden, siehe is_ready() in app/widgets/base.py.
WIDGETS_ENABLED = ("clock", "weather", "dwd", "bus", "pegel")

# Kleiner Webserver zum Aendern von Optionen im Betrieb (app/shared/web.py).
# Ohne Anmeldung: jeder im Netz kann Farben aendern und neu starten.
WEB_ENABLED = True
WEB_PORT = 80

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

# Wetter-Widget: HomeAssistant weather-Entity (hier DWD)
WEATHER_ENTITY = "weather.bonn_friesdorf"
WEATHER_TEMP_COLOR = 7         # weiss
WEATHER_HUMIDITY_COLOR = 6     # cyan
WEATHER_WIND_COLOR = 7         # weiss

# Bus-Widget: HomeAssistant-Abfahrtssensoren (eine Entity pro Linie und Richtung)
BUS_ENTITIES = (
    "sensor.bonn_endenich_euskirchener_str_606_bonn_ramersdorf",
    "sensor.bonn_endenich_euskirchener_str_607_bonn_ramersdorf",
    "sensor.bonn_endenich_euskirchener_str_608_bonn_holzlar_gielgen",
    "sensor.bonn_endenich_euskirchener_str_609_bonn_holzlar_gielgen",
    "sensor.bonn_endenich_euskirchener_str_n2_bonn_hbf",
    "sensor.bonn_endenich_euskirchener_str_n6_bonn_hbf",
)
BUS_ROWS = 4
# Farbe der Liniennummer wie auf den echten Anzeigen. (1, 3) = Rot/Gelb-Schachbrett, wirkt orange.
BUS_LINE_COLORS = {"606": 2, "607": 2, "608": (1, 3), "609": (1, 3), "N2": 7, "N6": 7}
BUS_LINE_COLOR = 7             # weiss, fuer Linien ohne Eintrag in BUS_LINE_COLORS
BUS_MINUTES_COLOR = 7          # weiss
BUS_DELAY_RED_MIN = 5          # ab so vielen Minuten Verspaetung rot statt gelb

# Pegel-Widget: Wasserstand aus HomeAssistant (cm), animierte Wasserflaeche
PEGEL_ENTITY = "sensor.rhein_pegel_bonn_wasserstand"
PEGEL_MIN_CM = 0               # unteres Ende der Skala (kein Wasser im Bild)
PEGEL_MAX_CM = 800             # oberes Ende (Bild voll); so liegen beide Marken auf der Skala
# Hochwassermarken: gestrichelte Linien im Bild und Farbwechsel der Zahl.
# Werte fuer den Pegel Bonn bitte pruefen (Quelle: PEGELONLINE / HochwasserPortal).
PEGEL_WARN_CM = 620            # gelbe Marke, ab hier Zahl gelb
PEGEL_ALARM_CM = 750           # rote Marke, ab hier Zahl rot und blinkend
PEGEL_TREND_WINDOW_MS = 3 * 60 * 60 * 1000   # Zeitfenster fuer den Trendpfeil
PEGEL_TREND_MIN_CM = 2         # ab dieser Aenderung gilt der Pegel als steigend/fallend
PEGEL_WAVE_MS = 160            # Schrittweite der Wellenanimation
PEGEL_WATER_COLOR = 4          # blau
PEGEL_SURFACE_COLOR = 6        # cyan
PEGEL_NUMBER_COLOR = 7         # weiss

# DWD-Warnstufen-Widget: zwei HomeAssistant-Sensoren (aktuelle Stufe und Vorwarnstufe)
DWD_CURRENT_ENTITY = "sensor.stadt_bonn_aktuelle_warnstufe"
DWD_PREWARN_ENTITY = "sensor.stadt_bonn_vorwarnstufe"
DWD_ALWAYS_SHOW = False        # True: auch bei Stufe 0 zeigen ("KEINE WARNUNG")
DWD_BLINK_LEVEL = 3            # ab dieser Stufe blinkt das Warndreieck
# DWD-Warnstufen: 1 gelb, 2 orange, 3 rot, 4 dunkelrot. Auf dem Panel gibt es
# kein Orange und kein Dunkelrot: (1, 3) ist ein Rot/Gelb-Schachbrett, Stufe 4 magenta.
DWD_LEVEL_COLORS = {1: 3, 2: (1, 3), 3: 1, 4: 5}
DWD_OK_COLOR = 2               # gruen fuer "keine Warnung"
DWD_TEXT_COLOR = 7             # weiss

# Uhr-Widget
CLOCK_TIME_COLOR = 7           # weiss
CLOCK_DATE_COLOR = 1           # rot (gelb, wenn der letzte Zeitabgleich aelter als TIME_STALE_MS ist)
CLOCK_WEEKDAYS = ("MO", "DI", "MI", "DO", "FR", "SA", "SO")

# HomeAssistant via MQTT (Mosquitto + mqtt_statestream), siehe app/shared/mqtt.py und hass.py.
MQTT_CLIENT_ID = "led-display"
MQTT_KEEPALIVE_S = 60
MQTT_RECONNECT_MS = 5000       # erster Wiederverbindungsversuch, verdoppelt sich bis MQTT_RECONNECT_MAX_MS
MQTT_RECONNECT_MAX_MS = 60000
MQTT_CONNECT_TIMEOUT_S = 5
HASS_BASE_TOPIC = "statestream"  # base_topic von mqtt_statestream in HomeAssistant

# Zugangsdaten kommen aus local_config.py auf dem Geraete-Dateisystem (nicht in der Firmware).
try:
    import local_config as _local
except ImportError:
    _local = None
WIFI_SSID = getattr(_local, "WIFI_SSID", "")
WIFI_PASSWORD = getattr(_local, "WIFI_PASSWORD", "")
MQTT_HOST = getattr(_local, "MQTT_HOST", "")       # leer = MQTT aus
MQTT_PORT = getattr(_local, "MQTT_PORT", 1883)
MQTT_USER = getattr(_local, "MQTT_USER", "")
MQTT_PASSWORD = getattr(_local, "MQTT_PASSWORD", "")

# Zuletzt: Optionen, die im Betrieb per Webserver geaendert wurden, ueberschreiben
# die Defaults von oben (settings_override.json auf dem Geraet, app/shared/config.py).
try:
    from app.shared import config as _config
    _config.apply(globals())
except Exception as _exc:      # ohne Overrides startet die App trotzdem
    print("settings: overrides not applied:", _exc)
