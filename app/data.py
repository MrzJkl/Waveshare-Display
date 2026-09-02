import time

from app import settings


class DataProviders:
    def __init__(self):
        self.temperature_c = None
        self.ha_online = False
        self.next_refresh_ms = time.ticks_ms()

    def service(self, now_ticks, boot_state):
        if time.ticks_diff(now_ticks, self.next_refresh_ms) < 0:
            return

        self.next_refresh_ms = time.ticks_add(now_ticks, settings.DATA_REFRESH_MS)

        # Placeholder data provider: swap with real sensors/APIs later.
        if not boot_state.wifi_connected:
            self.temperature_c = None
            self.ha_online = False
            return

        sec = time.localtime()[5]
        self.temperature_c = 21 + (sec % 5)
        self.ha_online = boot_state.ntp_synced
