from app.modules.clock import ClockModule
from app.modules.homeassistant import HomeAssistantModule
from app.modules.temperature import TemperatureModule


def create_default_modules():
    return [ClockModule(), TemperatureModule(), HomeAssistantModule()]
