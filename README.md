# LED Display (Current Version)

Dieses Repository ist auf den aktuellen Stand reduziert: **modulare MicroPython-App fuer HUB75**
mit einer **autonomen Scan-Engine in C (PIO + DMA)**.

## Aktive Struktur

```text
main.py
manifest.py
app/
  settings.py
  display.py
  boot.py
  data.py
  runtime.py
  modules/
    base.py
    clock.py
    temperature.py
    homeassistant.py
native/
  hub75_native_scan/
    README.md
    hub75.h
    hub75_internal.h
    hub75_stream.c
    hub75_pio.c
    hub75_dma.c
    hub75_driver.c
    mod_hub75_native_scan.c
    micropython.cmake
tools/
  generate_wifi_config.sh
wifi_config.example.py
README.md
.gitignore
```

## Zweck der Dateien

- [main.py](main.py): schlanker Entrypoint.
- [app/display.py](app/display.py): Darstellungsebene (Font/Buffer in Python, uebergibt fertige Frames an die native Engine).
- [app/boot.py](app/boot.py): Boot-/Infrastruktur-Ebene (WLAN + NTP + Status-LED).
- [app/data.py](app/data.py): Datenbeschaffungsebene (derzeit Platzhalter, spaeter Sensoren/APIs).
- [app/modules](app/modules): rotierende Anzeige-Module (Clock, Temperatur, HomeAssistant).
- [app/runtime.py](app/runtime.py): Orchestrierung und Modulrotation.
- [native/hub75_native_scan](native/hub75_native_scan): User-C-Modul, das das Panel komplett in Hardware (PIO + DMA) refresht. Aufbau und Funktionsweise sind in [native/hub75_native_scan/README.md](native/hub75_native_scan/README.md) erklaert.
- [manifest.py](manifest.py): Frozen-Manifest fuer den Build.
- [tools/generate_wifi_config.sh](tools/generate_wifi_config.sh): erzeugt lokale [wifi_config.py](wifi_config.py) aus Env-Variablen.
- [wifi_config.example.py](wifi_config.example.py): Vorlage fuer lokale WLAN-Konfiguration.

## Architektur

- **Darstellung:** Pixel/Text werden in Python in einen Framebuffer gezeichnet und als Wortliste
  (`width * scan_rows` GPIO-Masken) an das native Modul uebergeben.
- **Refresh:** laeuft vollstaendig ohne CPU. Eine PIO-State-Machine treibt RGB-Daten, CLK, LAT, OE
  und die Zeilenadresse aus einem vorgebauten Wortstrom; zwei verkettete DMA-Kanaele spielen den
  Frame endlos ab (Datenkanal -> Steuerkanal setzt die Leseadresse zurueck -> Datenkanal ...).
  Python darf beliebig lange blockieren (WLAN, NTP, HTTP, Garbage Collection, Rendering), ohne dass
  das Panel dunkel wird oder flackert. Das ist dasselbe Prinzip wie im Waveshare-/JuPfu-Referenztreiber.
- **Frame-Wechsel:** doppelt gepuffert. `swap_scan_words()` baut den neuen Frame im Hintergrundpuffer
  und veroeffentlicht ihn; der DMA uebernimmt ihn an der naechsten Frame-Grenze (kein Tearing).
- **Zeilen-Sequenz** (pro Scanzeile, Timing aus `settings.py`): naechste Zeile einschieben, waehrend
  die aktuelle noch leuchtet -> OE aus (Guard) -> LAT-Puls -> Latch-Settle -> neue Zeilenadresse ->
  Adress-Settle -> OE an fuer `ON_TIME_US`.
- **Boot/Infra:** WLAN/NTP/LED, kein Zeichnen.
- **Module:** liefern nur Anzeige-Text und koennen beliebig erweitert werden.
- **Runtime:** schlaeft zwischen Service-Laeufen (`LOOP_IDLE_MS`) und rotiert Module alle paar Sekunden.

Damit kannst du spaeter leicht z. B. Wetter, HomeAssistant oder Kalender als eigene Module einhaengen.

### Native API (`hub75_native_scan`)

| Funktion | Zweck |
| --- | --- |
| `init(width, scan_rows, r1, g1, b1, r2, g2, b2, row_base_pin, row_n_pins, clk_pin, lat_pin, oe_pin, *, on_time_us=32, pio_clkdiv=2.0, clk_half_cycles=4, oe_guard_ns=60, latch_ns=120, addr_ns=200)` | startet den autonomen Refresh (Panel zunaechst dunkel) |
| `swap_scan_words(words)` | neuen Frame anzeigen (`array('I')`, `width * scan_rows` Woerter) |
| `clear()` | Panel dunkel schalten |
| `set_on_time_us(us)` | Leuchtdauer pro Zeile zur Laufzeit aendern (Helligkeit/Refresh) |
| `stats()` | Dict mit PIO/DMA-Zuordnung, Pixeltakt, Zeilen-/Frame-Zeit |
| `measure_frame_rate(ms=200)` | gemessene Bildwiederholrate in Hz (Diagnose) |
| `is_running()` | `True`, solange der DMA-Loop laeuft |
| `deinit()` | Refresh stoppen, Panel dunkel, PIO/DMA freigeben |

Grenzen: `MAX_WIDTH = 128`, `MAX_SCAN_ROWS = 32` (statische Puffer, ca. 36 KB RAM).

### Timing-Einstellungen

| Setting | Default | Bedeutung |
| --- | --- | --- |
| `ON_TIME_US` | 32 | Leuchtdauer pro Zeile nach dem Umschalten; 16 Zeilen -> ca. 1.7 kHz Refresh |
| `NATIVE_PIO_CLKDIV` | 2.0 | PIO-Takt = CPU-Takt / clkdiv (wie `SM_CLOCKDIV_FACTOR` im Waveshare-Beispiel) |
| `NATIVE_CLK_HALF_CYCLES` | 4 | PIO-Zyklen pro CLK-Halbperiode -> Pixeltakt 250 MHz / 2 / 8 = 15.6 MHz |
| `NATIVE_OE_GUARD_NS` | 60 | Dunkelphase vor dem Latch (`BASE_OE_NS`) |
| `NATIVE_LATCH_NS` | 120 | Latch-Puls und Latch-Settle (`BASE_LATCH_NS`) |
| `NATIVE_ADDR_NS` | 200 | Settle nach Adresswechsel vor OE (`BASE_ADDR_NS`) |

Bei Ghosting oder Bildfehlern zuerst `NATIVE_PIO_CLKDIV` erhoehen (z. B. 3.0), danach die ns-Werte.
Die Herleitung der Werte und eine Symptom-Tabelle stehen in [native/hub75_native_scan/README.md](native/hub75_native_scan/README.md).

## Schnellstart

1. WLAN-Config generieren:

```bash
cd tools
WIFI_SSID='dein-ssid' WIFI_PASSWORD='dein-passwort' ./generate_wifi_config.sh
```

2. MicroPython RP2 Firmware mit Frozen Manifest und nativem Modul bauen (im separaten MicroPython-Checkout):

```bash
cd /home/moritz/micropython/ports/rp2
cmake -S . -B build-RPI_PICO2_W-min \
  -DMICROPY_BOARD=RPI_PICO2_W \
  -DMICROPY_FROZEN_MANIFEST=/home/moritz/pico/led-display/manifest.py \
  -DUSER_C_MODULES=/home/moritz/pico/led-display/native/hub75_native_scan/micropython.cmake
cmake --build build-RPI_PICO2_W-min -j"$(nproc)"
```

Wichtig: `-DUSER_C_MODULES` muss gesetzt sein. Ohne natives Modul startet die App nicht
(`hub75_native_scan module missing`), einen Python-Scan-Fallback gibt es nicht mehr.

3. UF2 flashen (BOOTSEL-Taste oder per USB in den Bootloader):

```bash
mpremote bootloader
cp /home/moritz/micropython/ports/rp2/build-RPI_PICO2_W-min/firmware.uf2 /run/media/$USER/RP2350/
```

4. Pruefen (unterbricht `main.py`, das Panel laeuft dank Hardware-Refresh weiter):

```bash
mpremote exec "import hub75_native_scan as h; print(h.stats()); print(h.measure_frame_rate(500))"
mpremote reset   # danach main.py wieder starten
```

Achtung: `mpremote soft-reset` startet `main.py` nicht (Soft-Reset im Raw-REPL laeuft ohne
`main.py`). Zum Neustart `mpremote reset` verwenden oder im `mpremote repl` Strg-D druecken.

Hinweis: `wifi_config.py` ist absichtlich nicht versioniert.

## Neues Modul hinzufuegen

1. Datei in [app/modules](app/modules) anlegen, Klasse von `DisplayModule` ableiten und `render(...)` implementieren.
2. Modul in [app/modules/__init__.py](app/modules/__init__.py) in `create_default_modules()` aufnehmen.
3. Datei in [manifest.py](manifest.py) mit `module("app/modules/dein_modul.py", ...)` einfrieren.
