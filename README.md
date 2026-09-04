# LED Display (Current Version)

**Modulare MicroPython-App fuer HUB75-Panels** mit einer **autonomen Scan-Engine in C (PIO + DMA)**.
Widgets sind reines Python und zeichnen auf einen `framebuf`; die Engine haelt das Bild flackerfrei.

## Aktive Struktur

```text
main.py
manifest.py
app/
  settings.py
  runtime.py
  shared/
    display.py
    font.py
    wifi.py
    timezone.py
    timesync.py
  widgets/
    base.py
    clock/widget.py
    temperature/widget.py
    homeassistant/widget.py
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
  run_demo.sh
  brightness_demo.py
  color_demo.py
wifi_config.example.py
README.md
.gitignore
```

## Zweck der Dateien

- [main.py](main.py): schlanker Entrypoint.
- [app/shared/display.py](app/shared/display.py): Darstellungsebene: `framebuf`-Zeichenflaeche (GS8, ein Byte pro Pixel als Farbindex), Text-Helfer, Helligkeit; uebergibt den Framebuffer an die native Engine.
- [app/shared/font.py](app/shared/font.py): Bitmap-Fonts (5x7 Text, 3x7 Digitalziffern), gerendert per `framebuf.blit` mit Palette (skalierbar, farbig, optional mit Hintergrund).
- [app/shared/wifi.py](app/shared/wifi.py): WLAN-Verbindung und Status-LED.
- [app/shared/timesync.py](app/shared/timesync.py): Zeitquelle: nicht blockierender SNTP-Client mit Laufzeitkompensation, Plausibilitaetspruefung und Server-Fallback; laeuft zwischen den Syncs auf dem Millisekunden-Ticker.
- [app/shared/timezone.py](app/shared/timezone.py): Zeitzonen mit lokal berechneter Sommerzeitregel (EU), z. B. `Europe/Berlin` = CET/CEST.
- [app/widgets](app/widgets): ein Ordner pro Widget mit Darstellung und (spaeter) eigenem Datenclient: [clock](app/widgets/clock/widget.py) (taktische Uhr), Temperatur und HomeAssistant als Platzhalter. [base.py](app/widgets/base.py) beschreibt den Lebenszyklus.
- [app/runtime.py](app/runtime.py): Hauptschleife: Dienste, `service()` aller Widgets, Rotation mit Fade, Zeichnen genau dann, wenn das Widget es will oder seine Daten sich aendern.
- [native/hub75_native_scan](native/hub75_native_scan): User-C-Modul, das das Panel komplett in Hardware (PIO + DMA) refresht. Aufbau und Funktionsweise sind in [native/hub75_native_scan/README.md](native/hub75_native_scan/README.md) erklaert.
- [manifest.py](manifest.py): Frozen-Manifest fuer den Build.
- [tools/generate_wifi_config.sh](tools/generate_wifi_config.sh): erzeugt lokale [wifi_config.py](wifi_config.py) aus Env-Variablen.
- [tools/run_demo.sh](tools/run_demo.sh): spielt eine visuelle Testsequenz ab (`brightness` oder `color`, laeuft per `mpremote run`, nichts wird geflasht) und startet danach `main.py` neu.
- [tools/brightness_demo.py](tools/brightness_demo.py), [tools/color_demo.py](tools/color_demo.py): die Testsequenzen fuer Helligkeit/Fading bzw. Farben/Pixelzuordnung.
- [wifi_config.example.py](wifi_config.example.py): Vorlage fuer lokale WLAN-Konfiguration.

## Architektur

- **Darstellung:** Widgets zeichnen mit `framebuf` auf `display.fb` (64x32, ein Byte pro Pixel,
  Farbindex 0..7: Bit 0 rot, Bit 1 gruen, Bit 2 blau). `display.show()` uebergibt den Puffer
  unveraendert an das native Modul, das ihn in seinen DMA-Strom umrechnet.
- **Refresh:** laeuft vollstaendig ohne CPU. Eine PIO-State-Machine treibt RGB-Daten, CLK, LAT, OE
  und die Zeilenadresse aus einem vorgebauten Wortstrom; zwei verkettete DMA-Kanaele spielen den
  Frame endlos ab (Datenkanal -> Steuerkanal setzt die Leseadresse zurueck -> Datenkanal ...).
  Python darf beliebig lange blockieren (WLAN, NTP, HTTP, Garbage Collection, Rendering), ohne dass
  das Panel dunkel wird oder flackert. Das ist dasselbe Prinzip wie im Waveshare-/JuPfu-Referenztreiber.
- **Frame-Wechsel:** doppelt gepuffert. `show_frame()` baut den neuen Frame im Hintergrundpuffer
  und veroeffentlicht ihn; der DMA uebernimmt ihn an der naechsten Frame-Grenze (kein Tearing).
- **Zeilen-Sequenz** (pro Scanzeile, Timing aus `settings.py`): naechste Zeile einschieben ->
  OE aus (Guard) -> LAT-Puls -> Latch-Settle -> neue Zeilenadresse -> Adress-Settle -> Leuchtphase ->
  Dunkelphase. Leucht- und Dunkelphase teilen sich das Budget `ON_TIME_US`.
- **Helligkeit:** `display.set_brightness(0.0..1.0)` verschiebt die Grenze zwischen Leucht- und
  Dunkelphase; die Bildrate bleibt konstant, die Aenderung landet an der naechsten Frame-Grenze.
  `display.fade_to(level, ms)` rampt weich (Baustein fuer sanfte Widget-Wechsel).
- **Zeit:** `TimeSync` fragt per SNTP mehrere Server ab (nicht blockierend, mehrere Messungen, die mit der
  kleinsten Laufzeit gewinnt, Plausibilitaetspruefung) und laeuft dazwischen auf `time.ticks_ms()`.
  Die Zeitzone rechnet `timezone.py` lokal inklusive Sommerzeit. Vor dem ersten Sync zeigt die Uhr
  Striche und ein blinkendes `SYNC`; ist der letzte Sync aelter als `TIME_STALE_MS`, wird die
  Datumszeile gelb.
- **Widgets:** reines Python, ein Ordner pro Widget. `service(now, ctx)` wird fuer alle Widgets in jedem
  Schleifendurchlauf gerufen (Daten holen, nicht blockieren, `self.revision` erhoehen, wenn sich etwas
  geaendert hat). `draw(display, ctx)` zeichnet einen kompletten Frame auf `display.fb` und gibt zurueck,
  in wie vielen Millisekunden es wieder gezeichnet werden will (die Uhr: bis zur naechsten
  Sekundengrenze). `ctx` liefert Netz (`ctx.net`) und Zeit (`ctx.time`).
- **Runtime:** ruft die Dienste auf, rotiert Widgets alle `WIDGET_ROTATE_MS` mit Aus-/Einblenden
  (`TRANSITION_MS`) und schlaeft sonst bis zum naechsten Zeichenzeitpunkt.

Damit kannst du spaeter leicht z. B. Wetter, HomeAssistant oder Kalender als eigene Widgets einhaengen.

### Native API (`hub75_native_scan`)

| Funktion | Zweck |
| --- | --- |
| `init(width, scan_rows, r1, g1, b1, r2, g2, b2, row_base_pin, row_n_pins, clk_pin, lat_pin, oe_pin, *, on_time_us=32, pio_clkdiv=2.0, clk_half_cycles=4, oe_guard_ns=60, latch_ns=120, addr_ns=200, brightness=65535)` | startet den autonomen Refresh (Panel zunaechst dunkel) |
| `show_frame(buf)` | neuen Frame anzeigen: `width * height` Bytes, ein Farbindex pro Pixel (z. B. der Puffer eines `framebuf` GS8) |
| `set_brightness(level)` | Helligkeit 0..65535 (linearer Tastgrad) bei konstanter Bildrate |
| `set_on_time_us(us)` | Zeitbudget pro Zeile aendern (Bildrate) |
| `stats()` | Dict mit PIO/DMA-Zuordnung, Pixeltakt, Zeilen-/Frame-Zeit |
| `measure_frame_rate(ms=200)` | gemessene Bildwiederholrate in Hz (Diagnose) |
| `is_running()` | `True`, solange der DMA-Loop laeuft |
| `deinit()` | Refresh stoppen, Panel dunkel, PIO/DMA freigeben |

Grenzen: `MAX_WIDTH = 128`, `MAX_SCAN_ROWS = 32` (statische Puffer, ca. 36 KB RAM).

### Timing-Einstellungen

| Setting | Default | Bedeutung |
| --- | --- | --- |
| `ON_TIME_US` | 32 | Zeitbudget pro Zeile fuer Leucht- + Dunkelphase; 16 Zeilen -> ca. 1.7 kHz Refresh |
| `BRIGHTNESS` | 1.0 | wahrgenommene Helligkeit 0.0..1.0 beim Start |
| `BRIGHTNESS_GAMMA` | 2.2 | Umrechnung wahrgenommen -> Tastgrad, damit Rampen gleichmaessig wirken |
| `FADE_STEP_MS` | 16 | Schrittweite von `fade_to()` |
| `NATIVE_PIO_CLKDIV` | 2.0 | PIO-Takt = CPU-Takt / clkdiv (wie `SM_CLOCKDIV_FACTOR` im Waveshare-Beispiel) |
| `NATIVE_CLK_HALF_CYCLES` | 4 | PIO-Zyklen pro CLK-Halbperiode -> Pixeltakt 250 MHz / 2 / 8 = 15.6 MHz |
| `NATIVE_OE_GUARD_NS` | 60 | Dunkelphase vor dem Latch (`BASE_OE_NS`) |
| `NATIVE_LATCH_NS` | 120 | Latch-Puls und Latch-Settle (`BASE_LATCH_NS`) |
| `NATIVE_ADDR_NS` | 200 | Settle nach Adresswechsel vor OE (`BASE_ADDR_NS`) |

Bei Ghosting oder Bildfehlern zuerst `NATIVE_PIO_CLKDIV` erhoehen (z. B. 3.0), danach die ns-Werte.
Die Herleitung der Werte und eine Symptom-Tabelle stehen in [native/hub75_native_scan/README.md](native/hub75_native_scan/README.md).

### Zeit und Uhr

| Setting | Default | Bedeutung |
| --- | --- | --- |
| `TIMEZONE` | `Europe/Berlin` | Zone aus `app/timezone.py` (CET/CEST mit EU-Regel) |
| `NTP_HOSTS` | Router, `pool.ntp.org`, `time.cloudflare.com` | Reihenfolge der Zeitserver; nach einem Fehlschlag wird zum naechsten gewechselt |
| `NTP_SAMPLES` | 3 | Messungen pro Sync, die mit der kleinsten Laufzeit wird uebernommen |
| `NTP_MAX_DELAY_MS` | 500 | Antworten mit groesserer Laufzeit werden verworfen |
| `NTP_RESYNC_MS` | 1 h | Abstand zwischen erfolgreichen Syncs |
| `TIME_STALE_MS` | 6 h | danach gilt die Zeit als veraltet (Datumszeile gelb) |
| `CLOCK_TIME_COLOR`, `CLOCK_DATE_COLOR` | weiss, rot | Farben der Uhr (Farbindex 0..7) |
| `CLOCK_WEEKDAYS` | `MO`..`SO` | Wochentagskuerzel |
| `WIDGET_ROTATE_MS`, `TRANSITION_MS` | 15 s, 400 ms | Widget-Wechsel und Fade-Dauer |

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

5. Am Panel pruefen (Testsequenzen, danach startet `main.py` automatisch neu):

```bash
./tools/run_demo.sh brightness   # Helligkeit und Fading, ca. 60 s
./tools/run_demo.sh color        # Farben und Pixelzuordnung, ca. 25 s
```

Die Skripte schreiben zu jedem Test auf die Konsole, was auf dem Panel zu sehen sein soll. Wirken bei
`brightness` die unteren Stufen zu dunkel oder zu hell, `GAMMA` im Skript aendern und den passenden
Wert nach `BRIGHTNESS_GAMMA` in `settings.py` uebernehmen.

Hinweis: `wifi_config.py` ist absichtlich nicht versioniert.

## Neues Widget hinzufuegen

1. Ordner `app/widgets/dein_widget/` mit `__init__.py` und `widget.py` anlegen, Klasse von `Widget`
   ableiten (siehe [base.py](app/widgets/base.py)): Daten in `service(now, ctx)` holen, Frame in
   `draw(display, ctx)` zeichnen (`display.clear()`, `display.text(...)`, `display.text_center(...)`,
   `display.fb.rect(...)` usw.) und zurueckgeben, nach wie vielen Millisekunden neu gezeichnet werden soll.
   Fonts: `display.font` (5x7, Buchstaben/Ziffern/Satzzeichen) und `app.shared.font.FONT_DIGITAL` (3x7-Ziffern).
   Ein eigener Datenclient (REST, MQTT, Sensor) gehoert als weitere Datei in denselben Ordner.
2. Widget in [app/widgets/__init__.py](app/widgets/__init__.py) in `create_default_widgets()` aufnehmen.
   Das Manifest friert das ganze Paket `app` ein, dort ist nichts zu tun.
