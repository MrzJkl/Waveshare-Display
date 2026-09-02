# LED Display (Current Version)

Dieses Repository ist auf den aktuellen Stand reduziert: **MicroPython-Clock auf HUB75**.

## Aktive Struktur

```text
main.py
manifest.py
tools/
  generate_wifi_config.sh
wifi_config.example.py
README.md
.gitignore
```

## Zweck der Dateien

- `main.py`: aktuelle Matrix-Clock-Implementierung inkl. WLAN + NTP + Scan-Loop.
- `manifest.py`: Frozen-Manifest fuer den Build.
- `tools/generate_wifi_config.sh`: erzeugt lokale `wifi_config.py` aus Env-Variablen.
- `wifi_config.example.py`: Vorlage fuer lokale WLAN-Konfiguration.

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
