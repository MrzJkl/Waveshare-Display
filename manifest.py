# Current manifest: board defaults + HUB75 MicroPython clock app.
include("$(PORT_DIR)/boards/manifest.py")
module("main.py", base_path=".", opt=0)
module("wifi_config.py", base_path=".", opt=0)