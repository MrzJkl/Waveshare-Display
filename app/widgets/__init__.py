from app.widgets.bus import BusWidget
from app.widgets.clock import ClockWidget
from app.widgets.pegel import PegelWidget
from app.widgets.weather import WeatherWidget


def create_default_widgets():
    """Widgets in rotation order; the first one is shown at start."""
    return [
        #ClockWidget(),
        #WeatherWidget(),
        #BusWidget(),
        PegelWidget(),
    ]
