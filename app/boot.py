import socket
import time

import network
from machine import RTC

from app import settings


class BootService:
    def __init__(self, status_led):
        self.status_led = status_led
        self.rtc = RTC()
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        try:
            self.wlan.config(pm=settings.WLAN_PM_PERF)
        except Exception:
            pass

        now = time.ticks_ms()
        self.next_wifi_try = now
        self.next_ntp_try = now
        self.ntp_synced = False

    @property
    def wifi_connected(self):
        return self.wlan.isconnected()

    def led_set(self, is_on):
        self.status_led.value(1 if is_on else 0)

    def update_status_led(self, second):
        # Fast visual hint: synced shows steady beat, unsynced shows sparse pulse.
        self.led_set((second & 1) == 0 if self.ntp_synced else (second % 3 == 0))

    def _set_rtc_from_unix_epoch(self, unix_seconds):
        tm = time.localtime(unix_seconds)
        self.rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))

    def _sync_ntp_once(self):
        sock = None
        try:
            addr = socket.getaddrinfo(settings.NTP_HOST, settings.NTP_PORT)[0][-1]
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(settings.NTP_TIMEOUT_S)

            packet = bytearray(48)
            packet[0] = 0x1B
            sock.sendto(packet, addr)
            data = sock.recv(48)

            if len(data) < 48:
                raise RuntimeError("short ntp response")

            ntp_seconds = (data[40] << 24) | (data[41] << 16) | (data[42] << 8) | data[43]
            unix_seconds = ntp_seconds - settings.NTP_DELTA
            if unix_seconds <= 0:
                raise RuntimeError("invalid ntp timestamp")

            self._set_rtc_from_unix_epoch(unix_seconds)
            print("ntp sync ok via", settings.NTP_HOST, "unix", unix_seconds)
            return True
        except Exception as exc:
            print("ntp retry", exc)
            self.led_set(False)
            return False
        finally:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass

    def service(self, now_ticks):
        ticks_add = time.ticks_add
        ticks_diff = time.ticks_diff
        rtc_changed = False

        if ticks_diff(now_ticks, self.next_wifi_try) >= 0 and not self.wifi_connected:
            if settings.WIFI_SSID and settings.WIFI_PASSWORD:
                try:
                    print("wifi connect request")
                    self.wlan.connect(settings.WIFI_SSID, settings.WIFI_PASSWORD)
                except Exception as exc:
                    print("wifi connect error:", exc)
            self.next_wifi_try = ticks_add(now_ticks, settings.WIFI_RETRY_MS)

        if self.wifi_connected and ticks_diff(now_ticks, self.next_ntp_try) >= 0:
            if self._sync_ntp_once():
                self.ntp_synced = True
                rtc_changed = True
                self.next_ntp_try = ticks_add(now_ticks, settings.NTP_RESYNC_MS)
            else:
                self.next_ntp_try = ticks_add(now_ticks, settings.NTP_RETRY_MS)

        return rtc_changed
