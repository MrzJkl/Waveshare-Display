"""Bus departure board from HomeAssistant departure sensors.

Each configured sensor entity describes one line at one stop and carries
    line_name   the line number, e.g. "608"
    times       JSON list of departures: planned, estimated (ISO 8601 with
                offset), cancelled, head_sign, alerts
The widget merges the departures of all lines, sorts them by estimated time
and shows the next BUS_ROWS as rows of: line number in bold in its line
colour, minutes until departure (rounded up, like the HomeAssistant app),
delay in minutes right-aligned with sign (yellow, red from BUS_DELAY_RED_MIN)
or "AUS" when cancelled. A departure that is due shows "0" and its row
blinks; it stays for GRACE_S after the estimated time unless HomeAssistant
drops it earlier.

Layout on 64 x 32: BUS_ROWS rows of 7 px spread evenly over the height.
"""

import time

from app import settings
from app.shared.display import RED, YELLOW
from app.widgets.base import Widget

ATTRIBUTES = ("line_name", "times")
MINUTES_RIGHT_X = 40        # minutes column is right-aligned here
MAX_MINUTES = 99            # departures further away are not shown
GRACE_S = 60                # a due departure stays this long after its estimated time
BLINK_MS = 500              # half period of the "due" blink


def parse_iso(text):
    """'2026-09-05T12:08:00+02:00' (or with a space) -> Unix seconds, None on error."""
    try:
        date, clock = text[:10], text[11:19]
        year, month, day = int(date[0:4]), int(date[5:7]), int(date[8:10])
        hour, minute, second = int(clock[0:2]), int(clock[3:5]), int(clock[6:8])
        # time.mktime() is a plain UTC conversion on MicroPython (no time zone support)
        utc = time.mktime((year, month, day, hour, minute, second, 0, 0))
        offset = text[19:]
        if offset and offset != "Z":
            sign = -1 if offset[0] == "-" else 1
            utc -= sign * (int(offset[1:3]) * 3600 + int(offset[4:6]) * 60)
        return utc
    except (ValueError, IndexError):
        return None


class BusWidget(Widget):
    name = "bus"

    def __init__(self):
        super().__init__()
        self.entities = settings.BUS_ENTITIES
        self._seen = None
        self._departures = []     # (estimated_unix, planned_unix, line, cancelled)
        self._data_marker = None

    # ------------------------------------------------------------------
    def service(self, now_ticks, ctx):
        hass = ctx.hass
        if self._seen is None:
            for entity in self.entities:
                for attribute in ATTRIBUTES:
                    hass.watch_attribute(entity, attribute)
        marker = 0
        for entity in self.entities:
            for attribute in ATTRIBUTES:
                marker += hass.revision_of(entity, attribute)
        if marker != self._seen:
            self._seen = marker
            self._rebuild(hass)
            self.revision += 1

    def _rebuild(self, hass):
        """Merge the departure lists of all lines into one sorted list."""
        departures = []
        for entity in self.entities:
            line = hass.attribute(entity, "line_name")
            times = hass.attribute(entity, "times")
            if line is None or not isinstance(times, list):
                continue
            line = str(line)
            for item in times:
                if not isinstance(item, dict):
                    continue
                planned = parse_iso(item.get("planned") or "")
                estimated = parse_iso(item.get("estimated") or "") or planned
                if estimated is None:
                    continue
                departures.append((estimated, planned or estimated, line, bool(item.get("cancelled"))))
        departures.sort()
        self._departures = departures

    def _upcoming(self, now_s):
        rows = []
        for estimated, planned, line, cancelled in self._departures:
            remaining = estimated - now_s
            if remaining < -GRACE_S or remaining > MAX_MINUTES * 60:
                continue
            rows.append((estimated, planned, line, cancelled))
            if len(rows) == settings.BUS_ROWS:
                break
        return rows

    def is_ready(self, ctx):
        now_ms = ctx.time.now_ms()
        return now_ms is not None and bool(self._upcoming(now_ms // 1000))

    # ------------------------------------------------------------------
    def draw(self, display, ctx):
        display.clear()
        now_ms = ctx.time.now_ms()
        if now_ms is None:
            display.text_center("BUS", settings.TEXT_COLOR)
            return 1000
        now_s = now_ms // 1000
        rows = self._upcoming(now_s)
        if not rows:
            display.text_center("KEINE", settings.TEXT_COLOR, 1, 8)
            display.text_center("ABFAHRT", settings.TEXT_COLOR, 1, 18)
            return 30000

        # Row geometry: rows of text height spread evenly over the panel.
        n = settings.BUS_ROWS
        text_h = display.font.height
        pitch = display.height // n
        y0 = (display.height - (n * text_h + (n - 1) * (pitch - text_h))) // 2

        ticks = time.ticks_ms()
        blink_on = (ticks // BLINK_MS) & 1 == 0
        wait_ms = 60000
        for i, (estimated, planned, line, cancelled) in enumerate(rows):
            remaining = estimated - now_s
            minutes = max(0, -(-remaining // 60))            # rounded up, 0 = due
            wait_ms = min(wait_ms, (remaining % 60 or 60) * 1000 + 1)
            if minutes == 0:
                wait_ms = min(wait_ms, BLINK_MS - ticks % BLINK_MS + 1)
                if not blink_on:
                    continue
            self._draw_row(display, y0 + i * pitch, line, minutes, (estimated - planned) // 60, cancelled)
        return max(1, wait_ms)

    def _draw_row(self, display, y, line, minutes, delay, cancelled):
        font = display.font
        colour = settings.BUS_LINE_COLORS.get(line, settings.BUS_LINE_COLOR)
        display.text(line, 0, y, colour, bold=True)

        minutes_text = "%d" % minutes
        display.text(minutes_text, MINUTES_RIGHT_X - font.text_width(minutes_text), y, RED if cancelled else settings.BUS_MINUTES_COLOR)

        if cancelled:
            delay_text, delay_colour = "AUS", RED
        elif delay > 0:
            delay_text, delay_colour = "+%d" % delay, RED if delay >= settings.BUS_DELAY_RED_MIN else YELLOW
        elif delay < 0:
            delay_text, delay_colour = "%d" % delay, settings.BUS_MINUTES_COLOR
        else:
            return
        display.text(delay_text, display.width - font.text_width(delay_text), y, delay_colour)
