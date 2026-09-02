# LED Display (Current Version)

Dieses Repository ist auf den aktuellen Stand reduziert: **modulare MicroPython-App fuer HUB75**.

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
tools/
  generate_wifi_config.sh
wifi_config.example.py
README.md
.gitignore
```

## Zweck der Dateien

- [main.py](main.py): schlanker Entrypoint.
- [app/display.py](app/display.py): reine Darstellungsebene (HUB75 Pins, Font, Scan-Loop).
- [app/boot.py](app/boot.py): Boot-/Infrastruktur-Ebene (WLAN + NTP + Status-LED).
- [app/data.py](app/data.py): Datenbeschaffungsebene (derzeit Platzhalter, spaeter Sensoren/APIs).
- [app/modules](app/modules): rotierende Anzeige-Module (Clock, Temperatur, HomeAssistant).
- [app/runtime.py](app/runtime.py): Orchestrierung und Modulrotation.
- [manifest.py](manifest.py): Frozen-Manifest fuer den Build.
- [tools/generate_wifi_config.sh](tools/generate_wifi_config.sh): erzeugt lokale [wifi_config.py](wifi_config.py) aus Env-Variablen.
- [wifi_config.example.py](wifi_config.example.py): Vorlage fuer lokale WLAN-Konfiguration.

## Architektur

- Darstellung: nur Pixel/Scan, keine Netzlogik.
- Boot/Infra: WLAN/NTP/LED, kein Zeichnen.
- Module: liefern nur Anzeige-Text und koennen beliebig erweitert werden.
- Runtime: rotiert Module alle paar Sekunden und aktualisiert Anzeige bei Bedarf.

Damit kannst du spaeter leicht z. B. Wetter, HomeAssistant oder Kalender als eigene Module einhaengen.

## Schnellstart

1. WLAN-Config generieren:

```bash
cd tools
WIFI_SSID='dein-ssid' WIFI_PASSWORD='dein-passwort' ./generate_wifi_config.sh
```

2. MicroPython RP2 Firmware mit Frozen Manifest bauen (im separaten MicroPython-Checkout):

```bash
cd /home/moritz/micropython/ports/rp2
cmake -S . -B build-RPI_PICO2_W-min \
  -DMICROPY_BOARD=RPI_PICO2_W \
  -DMICROPY_FROZEN_MANIFEST=/home/moritz/pico/led-display/manifest.py
cmake --build build-RPI_PICO2_W-min -j"$(nproc)"
```

3. UF2 flashen (BOOTSEL):

```bash
cp /home/moritz/micropython/ports/rp2/build-RPI_PICO2_W-min/firmware.uf2 /run/media/$USER/RP2350/
```

Hinweis: `wifi_config.py` ist absichtlich nicht versioniert.

## Neues Modul hinzufuegen

1. Datei in [app/modules](app/modules) anlegen, Klasse von `DisplayModule` ableiten und `render(...)` implementieren.
2. Modul in [app/modules/__init__.py](app/modules/__init__.py) in `create_default_modules()` aufnehmen.
3. Datei in [manifest.py](manifest.py) mit `module("app/modules/dein_modul.py", ...)` einfrieren.
