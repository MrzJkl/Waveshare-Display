#!/usr/bin/env bash
# Writes local_config.py (gitignored) from environment variables and copies it
# to the device when --deploy is given.
#   WIFI_SSID=... WIFI_PASSWORD=... MQTT_HOST=... MQTT_USER=... MQTT_PASSWORD=... \
#   FEUERSOFTWARE_TOKEN=... ./tools/generate_local_config.sh [--deploy]
# MQTT_PORT is optional (default 1883). Leave MQTT_HOST empty to disable MQTT and
# FEUERSOFTWARE_TOKEN empty to disable the vehicle status widget.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${WIFI_SSID:?WIFI_SSID is required}"
: "${WIFI_PASSWORD:?WIFI_PASSWORD is required}"
py_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
cat > local_config.py <<CFG
WIFI_SSID = $(py_str "$WIFI_SSID")
WIFI_PASSWORD = $(py_str "$WIFI_PASSWORD")

MQTT_HOST = $(py_str "${MQTT_HOST:-}")
MQTT_PORT = ${MQTT_PORT:-1883}
MQTT_USER = $(py_str "${MQTT_USER:-}")
MQTT_PASSWORD = $(py_str "${MQTT_PASSWORD:-}")

FEUERSOFTWARE_TOKEN = $(py_str "${FEUERSOFTWARE_TOKEN:-}")
CFG
echo "wrote local_config.py"
if [[ "${1:-}" == "--deploy" ]]; then
  mpremote cp local_config.py :local_config.py
  echo "copied to the device; restart with: mpremote reset"
fi
