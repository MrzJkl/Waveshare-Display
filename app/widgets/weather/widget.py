"""Weather dashboard from a HomeAssistant weather entity (here DWD).

Layout on 64 x 32:
   3 .. 16   condition icon (left) and the temperature in big digital digits
  21 .. 27   humidity with a drop symbol (left), wind symbol with direction and
             speed in km/h (right)

All values are attributes of the weather entity; the condition is its state.
"""

from app import settings
from app.shared.font import FONT_DIGITAL
from app.widgets.base import Widget
from app.widgets.weather import icons

ATTRIBUTES = ("temperature", "humidity", "wind_speed", "wind_bearing")
COMPASS = ("N", "NO", "O", "SO", "S", "SW", "W", "NW")


def compass(bearing):
    return COMPASS[int((bearing + 22.5) // 45) % 8]


class WeatherWidget(Widget):
    name = "weather"

    ICON_X = 2
    ICON_Y = 4
    TEMP_X0 = 16          # temperature is centred in the area right of the icon
    TEMP_Y = 3
    ROW_Y = 21

    def __init__(self):
        super().__init__()
        self.entity = settings.WEATHER_ENTITY
        self._seen = None

    def service(self, now_ticks, ctx):
        hass = ctx.hass
        if self._seen is None:
            hass.watch_state(self.entity)
            for attribute in ATTRIBUTES:
                hass.watch_attribute(self.entity, attribute)
        marker = hass.revision_of(self.entity)
        for attribute in ATTRIBUTES:
            marker += hass.revision_of(self.entity, attribute)
        if marker != self._seen:
            self._seen = marker
            self.revision += 1

    def is_ready(self, ctx):
        return ctx.hass.attribute_float(self.entity, "temperature") is not None

    def draw(self, display, ctx):
        hass = ctx.hass
        display.clear()
        fb = display.fb
        font = display.font

        icons.draw(fb, hass.state(self.entity), self.ICON_X, self.ICON_Y)

        temperature = hass.attribute_float(self.entity, "temperature")
        temp_text = "--" if temperature is None else "%.1f" % temperature
        unit = "°C"
        width = FONT_DIGITAL.text_width(temp_text, 2) + 2 + font.text_width(unit)
        x = self.TEMP_X0 + (display.width - self.TEMP_X0 - width) // 2
        x = display.text(temp_text, x, self.TEMP_Y, settings.WEATHER_TEMP_COLOR, 2, font=FONT_DIGITAL)
        display.text(unit, x + 1, self.TEMP_Y, settings.WEATHER_TEMP_COLOR)

        humidity = hass.attribute_float(self.entity, "humidity")
        x = icons.SYMBOLS.draw_glyph(fb, "drop", 0, self.ROW_Y, settings.WEATHER_HUMIDITY_COLOR)
        display.text("--%" if humidity is None else "%d%%" % round(humidity), x + 2, self.ROW_Y, settings.WEATHER_HUMIDITY_COLOR)

        wind = hass.attribute_float(self.entity, "wind_speed")
        bearing = hass.attribute_float(self.entity, "wind_bearing")
        if wind is None:
            wind_text = "--"
        elif bearing is None:
            wind_text = "%d" % round(wind)
        else:
            wind_text = "%s %d" % (compass(bearing), round(wind))
        symbol_w = icons.SYMBOLS.glyph_width("wind")
        x = display.width - font.text_width(wind_text) - 2 - symbol_w
        icons.SYMBOLS.draw_glyph(fb, "wind", x, self.ROW_Y, settings.WEATHER_WIND_COLOR)
        display.text(wind_text, x + symbol_w + 2, self.ROW_Y, settings.WEATHER_WIND_COLOR)
        return 60000
