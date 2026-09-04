"""Tactical clock: time with seconds, weekday and date.

Layout on 64 x 32 (y ranges):
   4 .. 17   HH:MM:SS in the 3x7 digital font at scale 2
  21 .. 27   weekday and date, e.g. "DO 04.09.26"

Sync state: before the first sync the time shows dashes and "SYNC" blinks in
the date line; when the last sync is older than TIME_STALE_MS the date line
turns yellow.
"""

import time

from app import settings
from app.shared.display import RED, YELLOW
from app.shared.font import FONT_DIGITAL
from app.widgets.base import Widget


class ClockWidget(Widget):
    name = "clock"

    TIME_Y = 4
    DATE_Y = 21

    def draw(self, display, ctx):
        display.clear()
        now_ms = ctx.time.now_ms()
        if now_ms is None:
            return self._draw_unsynced(display)

        lt = ctx.time.zone.localize(now_ms // 1000)
        date_colour = YELLOW if ctx.time.health() == "stale" else settings.CLOCK_DATE_COLOR
        display.text_center("%02d:%02d:%02d" % (lt.hour, lt.minute, lt.second),
                            settings.CLOCK_TIME_COLOR, 2, self.TIME_Y, FONT_DIGITAL)
        display.text_center("%s %02d.%02d.%02d" % (settings.CLOCK_WEEKDAYS[lt.weekday], lt.day, lt.month, lt.year % 100),
                            date_colour, 1, self.DATE_Y)
        return 1000 - now_ms % 1000 + 1      # wake up right after the next second boundary

    def _draw_unsynced(self, display):
        display.text_center("--:--:--", settings.CLOCK_TIME_COLOR, 2, self.TIME_Y, FONT_DIGITAL)
        if (time.ticks_ms() // 500) & 1:
            display.text_center("SYNC", RED, 1, self.DATE_Y)
        return 500 - time.ticks_ms() % 500 + 1
