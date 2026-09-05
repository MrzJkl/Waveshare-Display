"""Runtime-editable settings, stored on the device filesystem.

The firmware defaults live in app/settings.py. A curated subset of them can be
changed while the display runs (see app/shared/web.py). Those values are
written to OVERRIDE_FILE as JSON and applied on top of the defaults when
settings.py is imported, so a change survives a reboot without a new firmware.

Only the keys listed in OPTIONS can be changed, and only to plain values
(numbers, booleans, strings, lists of strings). Credentials are deliberately
not on that list: they stay in local_config.py and are never exposed.
"""

import json

OVERRIDE_FILE = "settings_override.json"
MAX_TEXT = 64

# Panel colours; the index is the value stored in a setting.
COLOR_NAMES = ("SCHWARZ", "ROT", "GRUEN", "GELB", "BLAU", "MAGENTA", "CYAN", "WEISS")


class Option:
    """One editable setting.

    kind      int, float, bool, color, choice, text or widgets
    live      True: takes effect with the next frame, False: needs a restart
    """

    def __init__(self, key, kind, label, low=None, high=None, choices=None, live=True, group=""):
        self.key = key
        self.kind = kind
        self.label = label
        self.low = low
        self.high = high
        self.choices = choices
        self.live = live
        self.group = group


OPTIONS = (
    Option("DISPLAY_ON", "bool", "Display an", group="Anzeige"),
    Option("BRIGHTNESS", "float", "Helligkeit (0.0 - 1.0)", 0.0, 1.0, group="Anzeige"),
    Option("WIDGETS_ENABLED", "widgets", "Aktive Widgets", group="Anzeige"),
    Option("WIDGET_ROTATE_MS", "int", "Wechsel alle (ms, 0 = kein Wechsel)", 0, 3600000, group="Anzeige"),
    Option("TRANSITION_MS", "int", "Ueberblenden (ms, 0 = hart)", 0, 5000, group="Anzeige"),

    Option("CLOCK_TIME_COLOR", "color", "Uhrzeit", group="Uhr"),
    Option("CLOCK_DATE_COLOR", "color", "Datum", group="Uhr"),

    Option("WEATHER_TEMP_COLOR", "color", "Temperatur", group="Wetter"),
    Option("WEATHER_HUMIDITY_COLOR", "color", "Luftfeuchte", group="Wetter"),
    Option("WEATHER_WIND_COLOR", "color", "Wind", group="Wetter"),

    Option("BUS_ROWS", "int", "Zeilen (3 oder 4)", 1, 4, group="Bus"),
    Option("BUS_DELAY_RED_MIN", "int", "Verspaetung rot ab (min)", 1, 60, group="Bus"),
    Option("BUS_MINUTES_COLOR", "color", "Minuten", group="Bus"),

    Option("PEGEL_MIN_CM", "int", "Skala von (cm)", 0, 2000, group="Pegel"),
    Option("PEGEL_MAX_CM", "int", "Skala bis (cm)", 1, 2000, group="Pegel"),
    Option("PEGEL_WARN_CM", "int", "Marke gelb (cm)", 0, 2000, group="Pegel"),
    Option("PEGEL_ALARM_CM", "int", "Marke rot (cm)", 0, 2000, group="Pegel"),
    Option("PEGEL_WATER_COLOR", "color", "Wasser", group="Pegel"),
    Option("PEGEL_SURFACE_COLOR", "color", "Wellenkamm", group="Pegel"),

    Option("DWD_ALWAYS_SHOW", "bool", "Auch ohne Warnung zeigen", group="DWD-Warnung"),
    Option("DWD_BLINK_LEVEL", "int", "Dreieck blinkt ab Stufe", 1, 4, group="DWD-Warnung"),

    Option("TIMEZONE", "choice", "Zeitzone", choices=("Europe/Berlin", "Europe/London", "Europe/Helsinki", "UTC"), live=False, group="System"),
)

BY_KEY = {option.key: option for option in OPTIONS}

# Firmware defaults, captured by apply() before the overrides land on top.
# Only deviations from these are stored, so the file stays small and a changed
# default in settings.py still takes effect after the next firmware update.
DEFAULTS = {}


def same(left, right):
    """Compare values, treating a tuple and a list with equal items as equal."""
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        try:
            return list(left) == list(right)
        except TypeError:
            return False
    return left == right


def coerce(option, value, widget_names=()):
    """Validate and convert a value (string from a form or native from JSON)."""
    kind = option.kind
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "on", "true", "yes")
    if kind in ("int", "color"):
        number = int(float(value))
        low, high = (0, 7) if kind == "color" else (option.low, option.high)
        if low is not None and number < low:
            number = low
        if high is not None and number > high:
            number = high
        return number
    if kind == "float":
        number = float(value)
        if option.low is not None and number < option.low:
            number = option.low
        if option.high is not None and number > option.high:
            number = option.high
        return number
    if kind == "choice":
        text = str(value)
        if text not in option.choices:
            raise ValueError("unknown choice")
        return text
    if kind == "widgets":
        names = value if isinstance(value, (list, tuple)) else [value]
        allowed = tuple(widget_names)
        chosen = [str(n) for n in names if not allowed or str(n) in allowed]
        return chosen
    text = str(value)[:MAX_TEXT]
    return text


def load():
    """Overrides from the file; an unreadable or broken file yields nothing."""
    try:
        with open(OVERRIDE_FILE) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def apply(target):
    """Apply the stored overrides to a globals() dict (called by settings.py)."""
    for option in OPTIONS:
        if option.key in target:
            DEFAULTS[option.key] = target[option.key]
    applied = {}
    for key, value in load().items():
        option = BY_KEY.get(key)
        if option is None or key not in target:
            continue
        try:
            target[key] = coerce(option, value)
            applied[key] = target[key]
        except (TypeError, ValueError):
            continue
    return applied


def save(values):
    try:
        with open(OVERRIDE_FILE, "w") as handle:
            json.dump(values, handle)
        return True
    except OSError as exc:
        print("config: cannot write", OVERRIDE_FILE, exc)
        return False


def update(raw, widget_names=()):
    """Validate raw form values, apply them to the running settings and store them.

    Returns (changed keys, keys that need a restart).
    """
    from app import settings

    stored = load()
    changed = []
    restart = []
    for key, value in raw.items():
        option = BY_KEY.get(key)
        if option is None:
            continue
        try:
            clean = coerce(option, value, widget_names)
        except (TypeError, ValueError):
            continue
        was_stored = key in stored
        if same(getattr(settings, key, None), clean) and not was_stored:
            continue
        setattr(settings, key, clean)
        if key in DEFAULTS and same(DEFAULTS[key], clean):
            stored.pop(key, None)           # back to the firmware default
            if not was_stored:
                continue
        else:
            if was_stored and same(stored[key], clean):
                continue
            stored[key] = clean
        changed.append(key)
        if not option.live:
            restart.append(key)
    if changed:
        if stored:
            save(stored)
        else:
            clear()                         # nothing deviates any more
    return changed, restart


def clear():
    """Forget all overrides; the firmware defaults apply after the next boot."""
    try:
        import os
        os.remove(OVERRIDE_FILE)
        return True
    except OSError:
        return False
