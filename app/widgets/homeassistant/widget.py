"""HomeAssistant placeholder: reports "online" once network and time are up.

Replace service() with a real HomeAssistant client (REST or MQTT).
"""

import time

from app import settings
from app.widgets.base import Widget


class HomeAssistantWidget(Widget):
    name = "homeassistant"

    def __init__(self):
        super().__init__()
        self.online = False
        self._next_refresh = time.ticks_ms()

    def service(self, now_ticks, ctx):
        if time.ticks_diff(now_ticks, self._next_refresh) < 0:
            return
        self._next_refresh = time.ticks_add(now_ticks, settings.DATA_REFRESH_MS)
        online = ctx.net.connected and ctx.time.synced    # placeholder
        if online != self.online:
            self.online = online
            self.revision += 1

    def is_ready(self, ctx):
        return self.online

    def draw(self, display, ctx):
        display.clear()
        display.text_center("HA OK" if self.online else "HA --", settings.TEXT_COLOR)
        return 1000
