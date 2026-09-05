"""DWD warning level for one region, from two HomeAssistant sensors.

The sensors of the DWD integration carry the level in their state (0 = no
warning, 1 = Wetterwarnung, 2 = markantes Wetter, 3 = Unwetter, 4 = extremes
Unwetter) and the number of warnings in the attribute warning_count. Event
names (warning_1_name) only exist while a warning is active, so they are read
only when warning_count is above zero.

Three states, all using the same visual language of triangle plus level:
  active warning     solid triangle in the level colour, "STUFE n", the event
                     name or the count, plus the advance notice as a bottom row
  advance notice     outlined triangle, "VORAB" and "STUFE n"
  nothing            calm green "KEINE WARNUNG"

From DWD_BLINK_LEVEL upwards the triangle blinks; the text stays put.
"""

import time

from app import settings
from app.shared.display import BLACK
from app.shared.text import fit, plain
from app.widgets.base import Widget
from app.widgets.dwd.icons import HEIGHT as ICON_H, ICONS, WIDTH as ICON_W

ATTRIBUTES = ("warning_count", "warning_1_name")
BLINK_MS = 500

ICON_X = 0
ICON_Y = 4
TEXT_X = ICON_W + 2
LINE_A_Y = 3
LINE_B_Y = 12
ROW_C_Y = 22

# The event name has about 50 pixels, so long DWD names are shortened by the
# first matching keyword. Order matters: the more specific keyword comes first.
EVENT_SHORT = (
    ("ORKAN", "ORKAN"),
    ("STURM", "STURM"),
    ("WIND", "WIND"),
    ("GEWITTER", "GEWITTER"),
    ("REGEN", "REGEN"),
    ("SCHNEEFALL", "SCHNEE"),
    ("SCHNEE", "SCHNEE"),
    ("GLATT", "GLATTEIS"),
    ("FROST", "FROST"),
    ("HITZE", "HITZE"),
    ("NEBEL", "NEBEL"),
    ("TAUWETTER", "TAUWETTER"),
    ("UV", "UV-INDEX"),
)


def event_label(name):
    """Short label for a DWD event name, e.g. "Windboeen" -> "WIND"."""
    name = plain(name)
    for keyword, label in EVENT_SHORT:
        if keyword in name:
            return label
    return name


def fit(font, text, max_width, bold=False):
    while text and font.text_width(text, bold=bold) > max_width:
        text = text[:-1]
    return text


class DwdWarnWidget(Widget):
    name = "dwd"

    def __init__(self):
        super().__init__()
        self.current = settings.DWD_CURRENT_ENTITY
        self.prewarn = settings.DWD_PREWARN_ENTITY
        self.level = 0
        self.count = 0
        self.event = None
        self.prewarn_level = 0
        self._seen = None

    # ------------------------------------------------------------------
    def service(self, now_ticks, ctx):
        hass = ctx.hass
        if self._seen is None:
            for entity in (self.current, self.prewarn):
                hass.watch_state(entity)
                hass.watch_attribute(entity, "warning_count")
            hass.watch_attribute(self.current, "warning_1_name")
        marker = 0
        for entity in (self.current, self.prewarn):
            marker += hass.revision_of(entity)
            for attribute in ATTRIBUTES:
                marker += hass.revision_of(entity, attribute)
        if marker == self._seen:
            return
        self._seen = marker
        self.level = self._level(hass, self.current)
        self.prewarn_level = self._level(hass, self.prewarn)
        self.count = self._count(hass, self.current)
        # The name topic keeps its last value after a warning ended, so it is
        # only trusted while warnings are actually reported.
        self.event = event_label(hass.attribute(self.current, "warning_1_name") or "") if self.count > 0 else ""
        self.revision += 1

    @staticmethod
    def _level(hass, entity):
        value = hass.state_float(entity)
        if value is None:
            return 0
        level = int(value + 0.5)
        return 0 if level < 0 else 4 if level > 4 else level

    @staticmethod
    def _count(hass, entity):
        value = hass.attribute(entity, "warning_count")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def is_ready(self, ctx):
        return settings.DWD_ALWAYS_SHOW or self.level > 0 or self.prewarn_level > 0

    # ------------------------------------------------------------------
    def draw(self, display, ctx):
        display.clear()
        ticks = time.ticks_ms()

        if self.level > 0:
            colour = self._colour(self.level)
            blink = self.level >= settings.DWD_BLINK_LEVEL
            if not (blink and (ticks // BLINK_MS) & 1):
                self._icon(display, "solid", colour)
            self._line(display, LINE_A_Y, "STUFE %d" % self.level, colour, bold=True)
            detail = self.event or ("%d AKTIV" % self.count if self.count else "")
            if detail:
                self._line(display, LINE_B_Y, detail, settings.DWD_TEXT_COLOR)
            if self.prewarn_level > 0:
                self._centred(display, ROW_C_Y, "VORAB %d" % self.prewarn_level, self._colour(self.prewarn_level))
            return (BLINK_MS - ticks % BLINK_MS + 1) if blink else 60000

        if self.prewarn_level > 0:
            colour = self._colour(self.prewarn_level)
            self._icon(display, "outline", colour)
            self._line(display, LINE_A_Y, "VORAB", colour, bold=True)
            self._line(display, LINE_B_Y, "STUFE %d" % self.prewarn_level, settings.DWD_TEXT_COLOR)
            return 60000

        self._centred(display, 7, "KEINE", settings.DWD_OK_COLOR)
        self._centred(display, 17, "WARNUNG", settings.DWD_OK_COLOR)
        return 60000

    @staticmethod
    def _colour(level):
        return settings.DWD_LEVEL_COLORS.get(level, settings.DWD_TEXT_COLOR)

    @staticmethod
    def _icon(display, shape, colour):
        ICONS.draw_glyph(display.fb, shape, ICON_X, ICON_Y, colour)
        # Black on the solid triangle, level colour inside the outlined one.
        ICONS.draw_glyph(display.fb, "excl", ICON_X, ICON_Y, BLACK if shape == "solid" else colour)

    @staticmethod
    def _line(display, y, text, colour, bold=False):
        text = fit(display.font, plain(text), display.width - TEXT_X, bold)
        display.text(text, TEXT_X, y, colour, bold=bold)

    @staticmethod
    def _centred(display, y, text, colour):
        text = fit(display.font, plain(text), display.width)
        display.text(text, (display.width - display.font.text_width(text)) // 2, y, colour)
