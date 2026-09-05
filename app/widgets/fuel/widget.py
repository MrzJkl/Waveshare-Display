"""Cheapest fuel price from Tankerkoenig data in Home Assistant.

Every configured sensor is one station and one fuel type. Its state is the
price in Euro with three decimals, its attributes carry brand, street and
house number. The widget picks the cheapest station that currently reports a
price, shows that price large and scrolls the station name along the bottom
edge, so a long name stays readable on 64 pixels.

The name is rendered once into a one bit wide strip and then blitted with an
offset, which keeps the moving text down to two blits per frame instead of one
per character. Strings and positions are prepared when the data changes, so
drawing a frame allocates nothing and cannot trigger a collection mid-scroll.

Layout on 64 x 32:
   1 .. 21   price like 2.22 with a raised 9, in the 3x7 digital font
  25 .. 31   station name as a marquee, prefixed with the fuel label

A station without a price (closed, no data) is skipped; if no station reports
one, the widget hides itself.
"""

import framebuf
import time

from app import settings
from app.shared.font import FONT_DIGITAL
from app.shared.text import plain
from app.widgets.base import Widget

ATTRIBUTES = ("brand", "street", "house_number")

PRICE_Y = 1
PRICE_SCALE = 3
TENTH_SCALE = 2         # the third decimal, drawn smaller like on a price sign
TENTH_GAP = 2
NAME_Y = 25
MARQUEE_GAP = 12        # blank pixels between two passes of the name
RESTART_AFTER_MS = 1000  # not drawn for longer than this: start from the left again


class FuelWidget(Widget):
    name = "fuel"

    def __init__(self):
        super().__init__()
        self.entities = settings.FUEL_ENTITIES
        self.price = None        # price of the cheapest station, in Euro
        self.station = None      # its name, ready to draw
        self._main = None        # prepared by _compose()
        self._tenth = None
        self._main_x = 0
        self._tenth_x = 0
        self._text = None        # marquee text, label plus station name
        self._seen = None
        self._scroll_start = 0
        self._last_draw = 0
        self._strip = None          # rendered marquee text, 1 bit per pixel
        self._strip_text = None
        self._strip_width = 0
        self._palette = None        # 2 entry palette for blitting the strip
        self._palette_colour = None

    # ------------------------------------------------------------------
    def service(self, now_ticks, ctx):
        hass = ctx.hass
        if self._seen is None:
            for entity in self.entities:
                hass.watch_state(entity)
                for attribute in ATTRIBUTES:
                    hass.watch_attribute(entity, attribute)
        marker = 0
        for entity in self.entities:
            marker += hass.revision_of(entity)
        if marker == self._seen:
            return
        self._seen = marker
        self._pick(hass)

    def _pick(self, hass):
        """Find the cheapest station that reports a price."""
        best_price = None
        best_entity = None
        for entity in self.entities:
            price = hass.state_float(entity)
            if price is None or price <= 0:
                continue
            if best_price is None or price < best_price:
                best_price, best_entity = price, entity
        station = self._label(hass, best_entity) if best_entity else None
        if best_price != self.price or station != self.station:
            self.price, self.station = best_price, station
            self._compose()
            self.revision += 1

    def _compose(self):
        """Prepare what draw() needs: price strings, their x positions and the
        marquee text. Done once per data change, not once per frame."""
        if self.price is None:
            self._main = self._tenth = self._text = None
            return
        # 2.229 -> "2.22" large plus a raised "9", the way price signs show it.
        milli = int(self.price * 1000 + 0.5)
        self._main = "%d.%02d" % (milli // 1000, milli // 10 % 100)
        self._tenth = "%d" % (milli % 10)
        main_w = FONT_DIGITAL.text_width(self._main, PRICE_SCALE)
        tenth_w = FONT_DIGITAL.text_width(self._tenth, TENTH_SCALE)
        self._main_x = (settings.MATRIX_WIDTH - (main_w + TENTH_GAP + tenth_w)) // 2
        self._tenth_x = self._main_x + main_w + TENTH_GAP
        label = settings.FUEL_LABEL
        self._text = (label + " " + self.station) if label else self.station

    @staticmethod
    def _label(hass, entity):
        """Brand, street and house number, or an override from the settings."""
        override = settings.FUEL_NAMES.get(entity)
        if override:
            return plain(override)
        parts = " ".join(str(hass.attribute(entity, a) or "") for a in ATTRIBUTES)
        return plain(parts) or plain(entity.split(".", 1)[-1])

    def is_ready(self, ctx):
        return self.price is not None

    # ------------------------------------------------------------------
    def draw(self, display, ctx):
        display.clear()
        ticks = time.ticks_ms()
        if self._text is None:
            display.text_center(settings.FUEL_LABEL or "?", settings.FUEL_PRICE_COLOR)
            return 60000
        colour = settings.FUEL_PRICE_COLOR
        display.text(self._main, self._main_x, PRICE_Y, colour, PRICE_SCALE, font=FONT_DIGITAL)
        display.text(self._tenth, self._tenth_x, PRICE_Y, colour, TENTH_SCALE, font=FONT_DIGITAL)
        wait = self._draw_name(display, ticks)
        self._last_draw = ticks
        return wait

    def _draw_name(self, display, ticks):
        text = self._text
        colour = settings.FUEL_NAME_COLOR
        if isinstance(colour, tuple):
            colour = colour[0]              # the strip carries one colour only
        strip, width = self._render(display, text)

        if width <= display.width:
            display.fb.blit(strip, (display.width - width) // 2, NAME_Y, 0, self._pal(colour))
            return 60000                    # nothing moves, no redraw needed

        if time.ticks_diff(ticks, self._last_draw) > RESTART_AFTER_MS:
            self._scroll_start = ticks      # coming back: start from the left edge
        step = settings.FUEL_SCROLL_MS
        elapsed = time.ticks_diff(ticks, self._scroll_start)
        period = width + MARQUEE_GAP
        offset = (elapsed // step) % period
        # Two copies one period apart make the loop seamless; framebuf clips
        # whatever falls outside the panel, and the second one is only needed
        # once it has scrolled in.
        palette = self._pal(colour)
        display.fb.blit(strip, -offset, NAME_Y, 0, palette)
        if period - offset < display.width:
            display.fb.blit(strip, period - offset, NAME_Y, 0, palette)
        return step - elapsed % step + 1

    def _render(self, display, text):
        """The marquee text as a 1 bit strip, rendered once per text change."""
        if text != self._strip_text:
            font = display.font
            width = font.text_width(text)
            height = font.height
            strip = framebuf.FrameBuffer(bytearray(((width + 7) // 8) * height),
                                         width, height, framebuf.MONO_HLSB)
            font.draw(strip, text, 0, 0, 1)
            self._strip, self._strip_text, self._strip_width = strip, text, width
        return self._strip, self._strip_width

    def _pal(self, colour):
        """2 entry palette: source 0 stays transparent, source 1 gets `colour`."""
        if colour != self._palette_colour:
            self._palette = framebuf.FrameBuffer(bytearray((0, colour)), 2, 1, framebuf.GS8)
            self._palette_colour = colour
        return self._palette
