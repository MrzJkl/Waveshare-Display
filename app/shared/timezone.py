"""Local time without an external time zone database.

A Zone has a standard UTC offset and optionally a DST offset plus a rule that
decides whether DST is active for a given UTC time. The EU rule (last Sunday
of March 01:00 UTC until last Sunday of October 01:00 UTC) covers all EU
zones, e.g. Europe/Berlin (CET/CEST).

MicroPython has no time zone support of its own: the RTC runs on UTC and
time.gmtime()/time.mktime() are plain UTC conversions, which is exactly what
the rules here build on.
"""

import time


def _last_sunday(year, month):
    # Both EU switch months have 31 days. weekday(): 0 = Monday ... 6 = Sunday.
    weekday = time.gmtime(time.mktime((year, month, 31, 12, 0, 0, 0, 0)))[6]
    return 31 - ((weekday + 1) % 7)


def eu_dst(unix_s):
    """EU daylight saving time rule; unix_s is UTC."""
    year = time.gmtime(unix_s)[0]
    start = time.mktime((year, 3, _last_sunday(year, 3), 1, 0, 0, 0, 0))
    end = time.mktime((year, 10, _last_sunday(year, 10), 1, 0, 0, 0, 0))
    return start <= unix_s < end


class LocalTime:
    """Broken-down local time. weekday: 0 = Monday ... 6 = Sunday."""

    def __init__(self, t, abbr, dst, offset_min):
        self.year = t[0]
        self.month = t[1]
        self.day = t[2]
        self.hour = t[3]
        self.minute = t[4]
        self.second = t[5]
        self.weekday = t[6]
        self.yearday = t[7]
        self.abbr = abbr
        self.dst = dst
        self.offset_min = offset_min


class Zone:
    def __init__(self, name, std_abbr, std_offset_min, dst_abbr=None, dst_offset_min=None, rule=None):
        self.name = name
        self.std_abbr = std_abbr
        self.std_offset_min = std_offset_min
        self.dst_abbr = dst_abbr
        self.dst_offset_min = dst_offset_min
        self.rule = rule

    def offset(self, unix_s):
        """(offset in minutes, abbreviation, dst active) for a UTC time."""
        if self.rule is not None and self.rule(unix_s):
            return self.dst_offset_min, self.dst_abbr, True
        return self.std_offset_min, self.std_abbr, False

    def localize(self, unix_s):
        offset_min, abbr, dst = self.offset(unix_s)
        return LocalTime(time.gmtime(unix_s + offset_min * 60), abbr, dst, offset_min)


ZONES = {
    "UTC": Zone("UTC", "UTC", 0),
    "Europe/Berlin": Zone("Europe/Berlin", "CET", 60, "CEST", 120, eu_dst),
    "Europe/London": Zone("Europe/London", "GMT", 0, "BST", 60, eu_dst),
    "Europe/Helsinki": Zone("Europe/Helsinki", "EET", 120, "EEST", 180, eu_dst),
}


def get_zone(name):
    zone = ZONES.get(name)
    if zone is None:
        raise ValueError("unknown time zone: " + str(name))
    return zone
