from app.modules.base import DisplayModule


class HomeAssistantModule(DisplayModule):
    name = "homeassistant"

    def is_ready(self, providers, boot_state):
        return providers.ha_online

    def render(self, now_tuple, providers, boot_state):
        return "HAOK" if providers.ha_online else "HA--"
