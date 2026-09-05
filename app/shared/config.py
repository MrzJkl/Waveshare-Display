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
COLOR_NAMES = ("BLACK", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE")


class Option:
    """One editable setting.

    kind      int, float, bool, color, choice, text or widgets
    live      True: takes effect with the next frame, False: needs a restart
    form      False: not part of the settings form (it has its own control, and
              a partial POST must not be able to change it by omission)
    """

    def __init__(self, key, kind, label, low=None, high=None, choices=None, live=True, group="", form=True):
        self.key = key
        self.kind = kind
        self.label = label
        self.low = low
        self.high = high
        self.choices = choices
        self.live = live
        self.group = group
        self.form = form


OPTIONS = (
    # Switched with the buttons and the /on, /off, /toggle webhooks, not in the form.
    Option("DISPLAY_ON", "bool", "Display on", group="Display", form=False),
    Option("BRIGHTNESS", "float", "Brightness (0.0 - 1.0)", 0.0, 1.0, group="Display"),
    Option("WIDGETS_ENABLED", "widgets", "Active widgets", group="Display"),
    Option("WIDGET_ROTATE_MS", "int", "Rotate every (ms, 0 = never)", 0, 3600000, group="Display"),
    Option("TRANSITION_MS", "int", "Fade (ms, 0 = hard cut)", 0, 5000, group="Display"),

    Option("CLOCK_TIME_COLOR", "color", "Time", group="Clock"),
    Option("CLOCK_DATE_COLOR", "color", "Date", group="Clock"),

    Option("WEATHER_TEMP_COLOR", "color", "Temperature", group="Weather"),
    Option("WEATHER_HUMIDITY_COLOR", "color", "Humidity", group="Weather"),
    Option("WEATHER_WIND_COLOR", "color", "Wind", group="Weather"),

    Option("BUS_ROWS", "int", "Rows (3 or 4)", 1, 4, group="Departures"),
    Option("BUS_DELAY_RED_MIN", "int", "Delay red from (min)", 1, 60, group="Departures"),
    Option("BUS_MINUTES_COLOR", "color", "Minutes", group="Departures"),

    Option("PEGEL_MIN_CM", "int", "Scale from (cm)", 0, 2000, group="River level"),
    Option("PEGEL_MAX_CM", "int", "Scale to (cm)", 1, 2000, group="River level"),
    Option("PEGEL_WARN_CM", "int", "Yellow mark (cm)", 0, 2000, group="River level"),
    Option("PEGEL_ALARM_CM", "int", "Red mark (cm)", 0, 2000, group="River level"),
    Option("PEGEL_WATER_COLOR", "color", "Water", group="River level"),
    Option("PEGEL_SURFACE_COLOR", "color", "Wave crest", group="River level"),

    Option("FUEL_PRICE_COLOR", "color", "Price", group="Fuel prices"),
    Option("FUEL_NAME_COLOR", "color", "Station name", group="Fuel prices"),
    Option("FUEL_SCROLL_MS", "int", "Marquee step (ms)", 20, 500, group="Fuel prices"),

    Option("DWD_ALWAYS_SHOW", "bool", "Show without a warning", group="Weather warning"),
    Option("DWD_BLINK_LEVEL", "int", "Triangle blinks from level", 1, 4, group="Weather warning"),

    Option("TIMEZONE", "choice", "Time zone", choices=("Europe/Berlin", "Europe/London", "Europe/Helsinki", "UTC"), live=False, group="System"),
    Option("WATCHDOG_MS", "int", "Watchdog (ms, 0 = off)", 0, 8300, live=False, group="System"),
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
        # A value equal to the firmware default belongs in neither the file nor
        # a change report; anything else is stored.
        should_store = not (key in DEFAULTS and same(DEFAULTS[key], clean))
        setting_differs = not same(getattr(settings, key, None), clean)
        file_differs = (key in stored) != should_store or (should_store and not same(stored.get(key), clean))
        if not setting_differs and not file_differs:
            continue

        setattr(settings, key, clean)
        if should_store:
            stored[key] = clean
        else:
            stored.pop(key, None)
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
