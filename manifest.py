# Frozen modules: board defaults, MQTT client library and the app package (recursively).
# local_config.py (WLAN and MQTT credentials) is NOT frozen: it lives on the device
# filesystem and is deployed with `mpremote cp local_config.py :local_config.py`.
include("$(PORT_DIR)/boards/manifest.py")
require("umqtt.simple")
require("requests")
module("main.py", base_path=".", opt=0)
package("app", base_path=".", opt=0)
