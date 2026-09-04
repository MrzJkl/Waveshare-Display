from app.widgets.clock import ClockWidget
from app.widgets.homeassistant import HomeAssistantWidget
from app.widgets.temperature import TemperatureWidget


def create_default_widgets():
    """Widgets in rotation order; the first one is shown at start."""
    return [ClockWidget(), TemperatureWidget(), HomeAssistantWidget()]
