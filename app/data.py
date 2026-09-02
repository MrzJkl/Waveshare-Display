import time

from app import settings


class DataProviders:
    def __init__(self):
        self.temperature_c = None
        self.ha_online = False
        self.next_refresh_ms = time.ticks_ms()
        self.revision = 0

    def service(self, now_ticks, boot_state):
        if time.ticks_diff(now_ticks, self.next_refresh_ms) < 0:
            return

        self.next_refresh_ms = time.ticks_add(now_ticks, settings.DATA_REFRESH_MS)

        # Placeholder data provider: swap with real sensors/APIs later.
        if not boot_state.wifi_connected:
            if self.temperature_c is not None or self.ha_online:
                self.temperature_c = None
                self.ha_online = False
                self.revision += 1
            return

        # Keep placeholder values stable to avoid unnecessary full-frame redraws.
        new_temp = 23
        new_ha_online = boot_state.ntp_synced

        if new_temp != self.temperature_c or new_ha_online != self.ha_online:
            self.temperature_c = new_temp
            self.ha_online = new_ha_online
            self.revision += 1
