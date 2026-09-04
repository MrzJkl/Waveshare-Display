"""Temperature placeholder: shows a fixed value while connected.

Replace service() with a real sensor or API client; keep the pattern of
updating self.temperature_c and bumping self.revision when it changes.
"""

import time

from app import settings
from app.widgets.base import Widget


class TemperatureWidget(Widget):
    name = "temperature"

    def __init__(self):
        super().__init__()
        self.temperature_c = None
        self._next_refresh = time.ticks_ms()

    def service(self, now_ticks, ctx):
        if time.ticks_diff(now_ticks, self._next_refresh) < 0:
            return
        self._next_refresh = time.ticks_add(now_ticks, settings.DATA_REFRESH_MS)
        value = 23 if ctx.net.connected else None    # placeholder
        if value != self.temperature_c:
            self.temperature_c = value
            self.revision += 1

    def is_ready(self, ctx):
        return self.temperature_c is not None

    def draw(self, display, ctx):
        display.clear()
        temp = self.temperature_c
        if temp is None:
            display.text_center("--°C", settings.TEXT_COLOR)
        else:
            display.text_center("%d°C" % int(temp + 0.5 if temp >= 0 else temp - 0.5), settings.TEXT_COLOR)
        return 1000
