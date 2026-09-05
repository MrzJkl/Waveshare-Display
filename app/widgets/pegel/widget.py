"""Water level (Pegel) as an animated water surface.

The panel is a tank: water rises from the bottom, its height scaled between
PEGEL_MIN_CM and PEGEL_MAX_CM. The surface ripples (two interfering integer
sine tables, one pixel of travel per animation step), the body is blue with a
cyan crest. The warn and alarm levels are drawn as dashed lines across the
water, so the current level can be read against them at a glance.

The value in cm sits in the middle in large digits, followed by the unit and a
trend arrow (nothing when the level is steady; the arrow sits behind the unit
so it can never be misread as a sign). Everything is drawn with a one pixel
black outline so it stays legible over the water. Above
PEGEL_WARN_CM the number turns yellow, above PEGEL_ALARM_CM it turns red and
blinks. Without data it shows dashes and an empty tank.

The trend comes from the widget's own history: the difference between the
newest and the oldest sample inside PEGEL_TREND_WINDOW_MS.
"""

import time

from app import settings
from app.shared.display import BLACK, RED, YELLOW
from app.shared.font import FONT_DIGITAL
from app.widgets.base import Widget
from app.widgets.pegel.icons import TREND, WIDTH as ARROW_W

# Ripple: two tables of different length interfere, so the pattern never
# repeats within the panel width. Values are pixel offsets of the surface.
WAVE_A = (0, 1, 1, 2, 2, 2, 1, 1, 0, -1, -1, -2, -2, -2, -1, -1)
WAVE_B = (0, 1, 1, 1, 0, 0, -1, -1, -1, 0, 0)

OUTLINE = ((-1, 0), (1, 0), (0, -1), (0, 1))
BLINK_MS = 500
DIGIT_SCALE = 2
UNIT = "CM"
GAP = 2                 # px between arrow, number and unit
MAX_SAMPLES = 12


class PegelWidget(Widget):
    name = "pegel"

    def __init__(self):
        super().__init__()
        self.entity = settings.PEGEL_ENTITY
        self.level_cm = None
        self._samples = []      # (ticks_ms, cm), newest last
        self._seen = None

    # ------------------------------------------------------------------
    def service(self, now_ticks, ctx):
        hass = ctx.hass
        if self._seen is None:
            hass.watch_state(self.entity)
        revision = hass.revision_of(self.entity)
        if revision == self._seen:
            return
        self._seen = revision
        level = hass.state_float(self.entity)
        if level is None:
            return
        if level != self.level_cm:
            self.level_cm = level
            self.revision += 1
        self._record(now_ticks, level)

    def _record(self, now_ticks, level):
        samples = self._samples
        if samples and samples[-1][1] == level:
            return
        samples.append((now_ticks, level))
        window = settings.PEGEL_TREND_WINDOW_MS
        while len(samples) > 1 and (time.ticks_diff(now_ticks, samples[0][0]) > window or len(samples) > MAX_SAMPLES):
            samples.pop(0)

    def trend_cm(self):
        """Change over the trend window; 0.0 when there is not enough history."""
        if len(self._samples) < 2:
            return 0.0
        return self._samples[-1][1] - self._samples[0][1]

    def is_ready(self, ctx):
        return self.level_cm is not None

    # ------------------------------------------------------------------
    def draw(self, display, ctx):
        display.clear()
        level = self.level_cm
        ticks = time.ticks_ms()

        self._draw_water(display, level, ticks // settings.PEGEL_WAVE_MS)
        self._draw_marks(display)

        alarm = level is not None and level >= settings.PEGEL_ALARM_CM
        blink_off = alarm and (ticks // BLINK_MS) & 1
        if not blink_off:
            self._draw_readout(display, level)

        wait = settings.PEGEL_WAVE_MS - ticks % settings.PEGEL_WAVE_MS + 1
        if alarm:
            wait = min(wait, BLINK_MS - ticks % BLINK_MS + 1)
        return max(1, wait)

    # --- water ---------------------------------------------------------
    def _level_height(self, level):
        """Water height in pixels for a level in cm."""
        if level is None:
            return 0
        span = settings.PEGEL_MAX_CM - settings.PEGEL_MIN_CM
        if span <= 0:
            return 0
        height = int((level - settings.PEGEL_MIN_CM) * 32 / span + 0.5)
        return 0 if height < 0 else 32 if height > 32 else height

    def _draw_water(self, display, level, phase):
        height = self._level_height(level)
        if height <= 0:
            return
        fb = display.fb
        base = display.height - height
        water = settings.PEGEL_WATER_COLOR
        crest = settings.PEGEL_SURFACE_COLOR
        bottom = display.height - 1
        for x in range(display.width):
            surface = base + WAVE_A[(x + phase) & 15] + WAVE_B[(x + 2 * phase) % 11]
            if surface < 0:
                surface = 0
            elif surface > bottom:
                surface = bottom
            fb.vline(x, surface, display.height - surface, water)
            fb.pixel(x, surface, crest)

    def _draw_marks(self, display):
        fb = display.fb
        for mark_cm, colour in ((settings.PEGEL_WARN_CM, YELLOW), (settings.PEGEL_ALARM_CM, RED)):
            height = self._level_height(mark_cm)
            if height <= 0 or height >= 32:
                continue            # outside the scale
            y = display.height - height
            for x in range(0, display.width, 5):
                fb.hline(x, y, 2, colour)

    # --- readout -------------------------------------------------------
    def _draw_readout(self, display, level):
        font = display.font
        if level is None:
            number, colour, arrow = "---", settings.PEGEL_NUMBER_COLOR, None
        else:
            number = "%d" % (level + 0.5 if level >= 0 else level - 0.5)
            colour = settings.PEGEL_NUMBER_COLOR
            if level >= settings.PEGEL_ALARM_CM:
                colour = RED
            elif level >= settings.PEGEL_WARN_CM:
                colour = YELLOW
            change = self.trend_cm()
            threshold = settings.PEGEL_TREND_MIN_CM
            arrow = "up" if change >= threshold else "down" if change <= -threshold else None

        number_w = FONT_DIGITAL.text_width(number, DIGIT_SCALE)
        unit_w = font.text_width(UNIT)
        # The arrow slot is always reserved, so the value never shifts when the
        # trend changes.
        x = (display.width - (number_w + GAP + unit_w + GAP + ARROW_W)) // 2
        y = (display.height - FONT_DIGITAL.text_height(DIGIT_SCALE)) // 2

        self._text_outlined(display, number, x, y, colour, DIGIT_SCALE, FONT_DIGITAL)
        x += number_w + GAP
        self._text_outlined(display, UNIT, x, y + 7, colour, 1, font)
        if arrow is not None:
            self._glyph_outlined(display.fb, arrow, x + unit_w + GAP, y + 4, colour)

    @staticmethod
    def _text_outlined(display, text, x, y, colour, scale, font):
        for dx, dy in OUTLINE:
            display.text(text, x + dx, y + dy, BLACK, scale, font=font)
        display.text(text, x, y, colour, scale, font=font)

    @staticmethod
    def _glyph_outlined(fb, key, x, y, colour):
        for dx, dy in OUTLINE:
            TREND.draw_glyph(fb, key, x + dx, y + dy, BLACK)
        TREND.draw_glyph(fb, key, x, y, colour)
