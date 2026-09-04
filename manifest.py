# Frozen modules: board defaults, the app package (recursively) and the local WLAN config.
include("$(PORT_DIR)/boards/manifest.py")
module("main.py", base_path=".", opt=0)
package("app", base_path=".", opt=0)
module("wifi_config.py", base_path=".", opt=0)
