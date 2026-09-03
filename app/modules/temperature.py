from app.modules.base import DisplayModule


class TemperatureModule(DisplayModule):
    name = "temperature"

    def is_ready(self, providers, boot_state):
        return providers.temperature_c is not None

    def render(self, now_tuple, providers, boot_state):
        temp = providers.temperature_c
        if temp is None:
            return "--:--"

        value = int(temp + 0.5) if temp >= 0 else int(temp - 0.5)
        if value < 0:
            value = 0
        if value > 99:
            value = 99

        return "T{:02d}C".format(value)
