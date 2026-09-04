"""Time source: a non-blocking SNTP client on top of a monotonic millisecond clock.

Between syncs the time runs on time.ticks_ms(); a sync only adjusts the offset
between that tick counter and Unix time, so nothing depends on the RTC.

Robustness:
- never blocks the main loop: non-blocking UDP, one step per service() call
- full 64-bit NTP timestamps with round-trip compensation; several samples per
  sync, the one with the smallest delay wins (filters delayed packets)
- plausibility checks: reply matches request, leap indicator, stratum, delay, year
- server list with fallback and cached name resolution
- the RTC is set as well, so time.time() and log timestamps are right

Accuracy is a few tens of milliseconds, which is plenty for a seconds display.
"""

import socket
import struct
import time

import machine

from app import settings

NTP_UNIX_DELTA = 2208988800          # seconds from 1900-01-01 to 1970-01-01
MIN_PLAUSIBLE_MS = 1735689600000     # 2025-01-01: anything earlier is garbage
_EAGAIN = 11


def _ntp_ms(data, pos):
    """64-bit NTP timestamp at `pos` -> Unix milliseconds."""
    secs, frac = struct.unpack_from("!II", data, pos)
    if secs < NTP_UNIX_DELTA:        # NTP era 1 (after 2036)
        secs += 1 << 32
    return (secs - NTP_UNIX_DELTA) * 1000 + ((frac * 1000) >> 32)


class TimeSync:
    def __init__(self, zone):
        self.zone = zone
        self.revision = 0             # bumps on every applied sync
        self.offset_ms = None         # unix_ms = mono_ms + offset_ms; None until the first sync
        self.last_sync_mono = None
        self.last_delay_ms = None
        self.last_host = None

        self._mono_ms = 0
        self._last_ticks = time.ticks_ms()
        self._next_attempt = 0
        self._host_index = 0
        self._addr_cache = {}

        self._sock = None
        self._host = None
        self._addr = None
        self._request = None
        self._samples = []
        self._samples_left = 0
        self._sent_mono = None
        self._next_send = 0
        self._t1 = 0

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------
    def _mono(self):
        """Monotonic milliseconds since start, immune to ticks_ms() wrap-around."""
        now = time.ticks_ms()
        self._mono_ms += time.ticks_diff(now, self._last_ticks)
        self._last_ticks = now
        return self._mono_ms

    @property
    def synced(self):
        return self.offset_ms is not None

    def now_ms(self):
        """Unix time in milliseconds, or None before the first sync."""
        mono = self._mono()
        if self.offset_ms is None:
            return None
        return mono + self.offset_ms

    def age_ms(self):
        if self.last_sync_mono is None:
            return None
        return self._mono() - self.last_sync_mono

    def health(self):
        """'none' (never synced), 'ok', or 'stale' (last sync older than TIME_STALE_MS)."""
        age = self.age_ms()
        if age is None:
            return "none"
        return "stale" if age > settings.TIME_STALE_MS else "ok"

    def local(self):
        """LocalTime in the configured zone, or None before the first sync."""
        now = self.now_ms()
        return None if now is None else self.zone.localize(now // 1000)

    # ------------------------------------------------------------------
    # SNTP state machine, one step per call
    # ------------------------------------------------------------------
    def service(self, connected):
        mono = self._mono()
        if not connected:
            if self._sock is not None:
                self._close()
                self._next_attempt = mono + 1000
            return
        if self._sock is None:
            if mono >= self._next_attempt:
                self._open(mono)
        elif self._sent_mono is None:
            if mono >= self._next_send:
                self._send(mono)
        else:
            self._poll(mono)

    def _open(self, mono):
        host = settings.NTP_HOSTS[self._host_index % len(settings.NTP_HOSTS)]
        try:
            addr = self._addr_cache.get(host)
            if addr is None:
                addr = socket.getaddrinfo(host, settings.NTP_PORT)[0][-1]
                self._addr_cache[host] = addr
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
        except OSError as exc:
            print("ntp: cannot use", host, exc)
            self._give_up(mono)
            return
        self._sock = sock
        self._host = host
        self._addr = addr
        self._samples = []
        self._samples_left = settings.NTP_SAMPLES
        self._sent_mono = None
        self._next_send = mono

    def _send(self, mono):
        request = bytearray(48)
        request[0] = 0x23                # leap 0, NTP version 4, mode 3 (client)
        # Transmit timestamp: a tag the server echoes as originate timestamp,
        # which lets us match the reply to this request.
        struct.pack_into("!II", request, 40, 0x50494330, mono & 0xFFFFFFFF)
        try:
            self._sock.sendto(request, self._addr)
        except OSError as exc:
            print("ntp: send failed", exc)
            self._finish(mono)
            return
        self._request = request
        self._sent_mono = mono
        self._t1 = mono + (self.offset_ms or 0)

    def _poll(self, mono):
        try:
            data, _ = self._sock.recvfrom(48)
        except OSError as exc:
            if exc.args[0] == _EAGAIN:
                if mono - self._sent_mono > settings.NTP_TIMEOUT_MS:
                    self._sample_done(mono)
                return
            print("ntp: receive failed", exc)
            self._finish(mono)
            return
        if len(data) < 48 or data[24:32] != self._request[40:48]:
            return                       # not the answer to our request, keep waiting
        sample = self._evaluate(data, mono)
        if sample is not None:
            self._samples.append(sample)
        self._sample_done(mono)

    def _evaluate(self, data, mono):
        leap = data[0] >> 6
        stratum = data[1]
        if leap == 3 or stratum == 0 or stratum > 15:
            return None                  # server unsynchronised or kiss-of-death
        t2 = _ntp_ms(data, 32)           # server receive
        t3 = _ntp_ms(data, 40)           # server transmit
        if t3 < MIN_PLAUSIBLE_MS:
            return None
        t1 = self._t1                    # our send time
        t4 = mono + (self.offset_ms or 0)   # our receive time
        delay = (t4 - t1) - (t3 - t2)
        if delay < 0 or delay > settings.NTP_MAX_DELAY_MS:
            return None
        correction = ((t2 - t1) + (t3 - t4)) // 2
        return (delay, correction)

    def _sample_done(self, mono):
        self._sent_mono = None
        self._samples_left -= 1
        if self._samples_left > 0:
            self._next_send = mono + 100
        else:
            self._finish(mono)

    def _finish(self, mono):
        host = self._host
        self._close()
        if not self._samples:
            print("ntp: no valid reply from", host)
            self._give_up(mono)
            return
        delay, correction = min(self._samples)
        first = self.offset_ms is None
        self.offset_ms = (self.offset_ms or 0) + correction
        self.last_sync_mono = mono
        self.last_delay_ms = delay
        self.last_host = host
        self.revision += 1
        self._set_rtc()
        self._next_attempt = mono + settings.NTP_RESYNC_MS
        if first:
            print("ntp: synced via %s, delay %d ms" % (host, delay))
        else:
            print("ntp: resynced via %s, delay %d ms, correction %+d ms" % (host, delay, correction))

    def _give_up(self, mono):
        self._close()
        self._host_index += 1            # try the next server next time
        self._next_attempt = mono + settings.NTP_RETRY_MS

    def _close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._sent_mono = None

    def _set_rtc(self):
        t = time.gmtime(self.now_ms() // 1000)
        machine.RTC().datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
