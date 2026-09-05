"""Vehicle radio status board (FMS status 0..9) from the Feuer Software API.

Layout on 64 x 32: two columns of VEHICLES_ROWS rows, spread evenly over the
height, columns spread evenly over the width. Each cell shows the status digit
in bold in its status colour and the vehicle name ("1-24-1", or "24-1" without
the location number) in the 3x7 digital font next to it. Status 0 (emergency) blinks. When the last
successful poll is older than VEHICLES_STALE_MS, status digits turn white to
flag outdated data.
"""

import time

from app import settings
from app.shared.display import WHITE
from app.shared.font import FONT_DIGITAL
from app.widgets.base import Widget
from app.widgets.vehicles.client import ConnectClient

COLUMNS = 2
NAME_GAP = 3            # pixels between the status digit and the name
BLINK_MS = 500


class VehiclesWidget(Widget):
    name = "vehicles"

    def __init__(self):
        super().__init__()
        self.enabled = bool(settings.FEUERSOFTWARE_TOKEN)
        self.vehicles = []
        self.last_ok_ticks = None
        self.last_error = None
        self._client = ConnectClient(settings.VEHICLES_API_URL, settings.FEUERSOFTWARE_TOKEN, settings.VEHICLES_HTTP_TIMEOUT_S)
        self._next_poll = time.ticks_ms()

    # ------------------------------------------------------------------
    def service(self, now_ticks, ctx):
        if not self.enabled or not ctx.net.connected:
            return
        if time.ticks_diff(now_ticks, self._next_poll) < 0:
            return
        self._next_poll = time.ticks_add(now_ticks, settings.VEHICLES_POLL_MS)
        try:
            vehicles = self._client.fetch()
        except Exception as exc:          # network, TLS, HTTP or JSON problem: keep old data
            self.last_error = exc
            print("vehicles: poll failed:", exc)
            return
        self.last_error = None
        was_stale = self.last_ok_ticks is None
        self.last_ok_ticks = now_ticks
        shown = self._select(vehicles)
        if was_stale or [(v.name, v.status) for v in shown] != [(v.name, v.status) for v in self.vehicles]:
            self.vehicles = shown
            self.revision += 1

    def _select(self, vehicles):
        by_name = {v.name: v for v in vehicles}
        if settings.VEHICLES_SHOW:
            return [by_name[n] for n in settings.VEHICLES_SHOW if n in by_name]
        return sorted(vehicles, key=lambda v: v.name)[:COLUMNS * settings.VEHICLES_ROWS]

    def _stale(self):
        return self.last_ok_ticks is None or time.ticks_diff(time.ticks_ms(), self.last_ok_ticks) > settings.VEHICLES_STALE_MS

    def is_ready(self, ctx):
        return self.enabled and bool(self.vehicles)

    # ------------------------------------------------------------------
    def draw(self, display, ctx):
        display.clear()
        if not self.vehicles:
            display.text_center("FMS", settings.TEXT_COLOR)
            return 1000
        stale = self._stale()
        ticks = time.ticks_ms()
        blink_on = (ticks // BLINK_MS) & 1 == 0
        rows = settings.VEHICLES_ROWS
        shown = self.vehicles[:COLUMNS * rows]

        # Geometry: rows spread over the height, two equally wide cells spread
        # over the width with equal margins left, between and right.
        pitch = (display.height - display.font.height) // (rows - 1) if rows > 1 else 0
        labels = [(v, v.label(settings.VEHICLES_SHOW_LOCATION)) for v in shown]
        name_w = max(self._name_font(display, label).text_width(label) for _, label in labels)
        cell_w = display.font.text_width("0", bold=True) + NAME_GAP + name_w
        margin = max(0, (display.width - COLUMNS * cell_w) // (COLUMNS + 1))
        column_x = (margin, display.width - margin - cell_w)

        wait_ms = 60000
        for index, (vehicle, label) in enumerate(labels):
            x = column_x[index // rows]
            y = (index % rows) * pitch
            if vehicle.status == 0:
                wait_ms = min(wait_ms, BLINK_MS - ticks % BLINK_MS + 1)
            self._draw_cell(display, x, y, vehicle, label, stale, blink_on)
        return wait_ms

    @staticmethod
    def _name_font(display, label):
        return FONT_DIGITAL if all(c in FONT_DIGITAL.glyphs for c in label) else display.font

    def _draw_cell(self, display, x, y, vehicle, label, stale, blink_on):
        status = vehicle.status
        if status is None:
            digit, colour = "-", WHITE
        else:
            digit = "%d" % status
            colour = WHITE if stale else settings.VEHICLE_STATUS_COLORS.get(status, WHITE)
        if not (status == 0 and not blink_on):
            display.text(digit, x, y, colour, bold=True)
        x += display.font.text_width("0", bold=True) + NAME_GAP
        display.text(label, x, y, settings.VEHICLES_NAME_COLOR, font=self._name_font(display, label))
