"""WLAN connection management and the on-board status LED."""

import time

import network

from app import settings


class WifiService:
    def __init__(self, status_led):
        self.status_led = status_led
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        try:
            self.wlan.config(pm=settings.WLAN_PM_PERF)
        except (OSError, ValueError):
            pass
        self.next_try = time.ticks_ms()

    @property
    def connected(self):
        return self.wlan.isconnected()

    @property
    def address(self):
        """Own IP address, or None while not connected."""
        if not self.wlan.isconnected():
            return None
        try:
            return self.wlan.ifconfig()[0]
        except OSError:
            return None

    def service(self, now_ticks):
        if self.connected or time.ticks_diff(now_ticks, self.next_try) < 0:
            return
        if settings.WIFI_SSID and settings.WIFI_PASSWORD:
            try:
                print("wifi: connecting")
                self.wlan.connect(settings.WIFI_SSID, settings.WIFI_PASSWORD)
            except OSError as exc:
                print("wifi: connect error", exc)
        self.next_try = time.ticks_add(now_ticks, settings.WIFI_RETRY_MS)

    def update_status_led(self, second, synced):
        # Time synced: steady 1 Hz beat. Not synced: sparse pulse.
        on = (second & 1) == 0 if synced else (second % 3 == 0)
        self.status_led.value(1 if on else 0)
