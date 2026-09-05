# Local, secret configuration. Copy to local_config.py (gitignored) or generate it
# with tools/generate_local_config.sh, then copy it to the device filesystem:
#   mpremote cp local_config.py :local_config.py
# It is deliberately not frozen into the firmware, so credentials can change
# without a rebuild.

WIFI_SSID = "your-ssid"
WIFI_PASSWORD = "your-password"

# MQTT broker (Mosquitto add-on of HomeAssistant). Empty host = MQTT disabled.
MQTT_HOST = "192.168.178.2"
MQTT_PORT = 1883
MQTT_USER = "display"
MQTT_PASSWORD = "your-mqtt-password"
