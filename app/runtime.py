"""Main loop: services, widget rotation, drawing and the on/off state.

Every pass runs the shared services (WLAN, time sync, MQTT, web server) and
every widget's service(), then draws when the current widget asks for it or
its data changed. The panel refreshes itself in hardware, so the loop sleeps
until the next such moment, at most LOOP_MAX_SLEEP_MS.

Robustness for unattended operation:
  * a widget that raises is logged, marked failed and dropped from the
    rotation; the other widgets keep running
  * an error outside the widgets blinks the status LED and reboots
  * with settings.WATCHDOG_MS the hardware watchdog reboots on a hang
"""

import gc
import time

import machine
from machine import Pin

from app import settings
from app.shared import timezone
from app.shared.display import Hub75Display
from app.shared.hass import HomeAssistant
from app.shared.mqtt import MqttClient
from app.shared.timesync import TimeSync
from app.shared.web import WebServer
from app.shared.wifi import WifiService
from app.widgets import create_default_widgets


class Context:
    """What widgets get to look at."""

    def __init__(self, net, time_sync, mqtt, hass):
        self.net = net          # WifiService: connected
        self.time = time_sync   # TimeSync: now_ms(), zone, health(), synced
        self.mqtt = mqtt        # MqttClient: watch(), get(), connected
        self.hass = hass        # HomeAssistant: state(), attribute(), watch_state()


class Rotator:
    """Cycles through the widgets that are currently visible.

    A widget is visible when it is switched on in settings.WIDGETS_ENABLED and
    its own is_ready() says it has something to show. Both are re-read on every
    pass, so the web UI can switch widgets on and off while the display runs.
    """

    def __init__(self, widgets):
        if not widgets:
            raise ValueError("widget list is empty")
        self.widgets = widgets
        self.index = 0
        self.next_switch_ms = time.ticks_add(time.ticks_ms(), settings.WIDGET_ROTATE_MS)

    @staticmethod
    def visible(widget, ctx):
        if widget.failed:
            return False
        enabled = settings.WIDGETS_ENABLED
        if enabled and widget.name not in enabled:
            return False
        try:
            return widget.is_ready(ctx)
        except Exception as exc:
            _widget_failed(widget, "is_ready", exc)
            return False

    def current(self, ctx):
        widget = self.widgets[self.index]
        if self.visible(widget, ctx):
            return widget
        for candidate in self.widgets:
            if self.visible(candidate, ctx):
                return candidate
        # Nothing is ready: never leave the panel empty, but prefer a widget
        # that at least is not broken.
        for candidate in self.widgets:
            if not candidate.failed:
                return candidate
        return self.widgets[0]

    def service(self, now_ticks, ctx):
        rotate_ms = settings.WIDGET_ROTATE_MS
        if len(self.widgets) < 2 or rotate_ms <= 0:
            return
        if time.ticks_diff(now_ticks, self.next_switch_ms) < 0:
            return
        for step in range(1, len(self.widgets) + 1):
            index = (self.index + step) % len(self.widgets)
            if self.visible(self.widgets[index], ctx):
                self.index = index
                break
        self.next_switch_ms = time.ticks_add(now_ticks, rotate_ms)


def _led_blink(status_led, count, on_ms=90, off_ms=90, tail_ms=800):
    for _ in range(count):
        status_led.value(1)
        time.sleep_ms(on_ms)
        status_led.value(0)
        time.sleep_ms(off_ms)
    if tail_ms:
        time.sleep_ms(tail_ms)


def _fatal_reboot(status_led, code=5):
    """Signal the error on the LED long enough to be noticed, then restart."""
    for _ in range(5):
        _led_blink(status_led, code)
    print("rebooting after a fatal error")
    machine.reset()


def _widget_failed(widget, where, exc):
    """Drop a broken widget instead of taking the whole display down."""
    if not widget.failed:
        print("widget %s failed in %s: %s" % (widget.name, where, exc))
    widget.failed = True


def _draw(display, widget, ctx):
    try:
        wait = widget.draw(display, ctx)
    except Exception as exc:
        _widget_failed(widget, "draw", exc)
        return 1000            # the next pass picks a widget that still works
    display.show()
    return 1000 if wait is None else max(1, wait)


def _switch(display, widget, ctx, animate):
    """Show a different widget, fading out and in when a transition is set."""
    duration = settings.TRANSITION_MS
    fade = animate and duration > 0
    level = display.brightness
    if fade:
        display.fade_to(0.0, duration)
    wait = _draw(display, widget, ctx)
    if fade:
        display.fade_to(level, duration)
    return wait


def _run(status_led):
    print("hub75 runtime start")

    try:
        machine.freq(settings.CPU_FREQ_HZ)
    except (OSError, ValueError) as exc:
        print("cpu freq unchanged:", exc)

    display = Hub75Display()
    net = WifiService(status_led)
    time_sync = TimeSync(timezone.get_zone(settings.TIMEZONE))
    mqtt = MqttClient()
    hass = HomeAssistant(mqtt, settings.HASS_BASE_TOPIC)
    ctx = Context(net, time_sync, mqtt, hass)
    widgets = create_default_widgets()
    rotator = Rotator(widgets)
    started = time.ticks_ms()

    def state():
        """Machine readable state for /status; cheap, it runs inside a request."""
        local = time_sync.local()
        return {
            "display_on": settings.DISPLAY_ON,
            "brightness": display.brightness,
            "widget": rotator.current(ctx).name,
            "address": net.address or "",
            "wifi": net.connected,
            "mqtt": mqtt.connected,
            "time_synced": time_sync.synced,
            "time": "%02d:%02d:%02d" % (local.hour, local.minute, local.second) if local else "",
            "zone": local.abbr if local else "",
            "uptime_s": time.ticks_diff(time.ticks_ms(), started) // 1000,
            "frame_hz": int(display.stats()["frame_hz"]),
            "mem_free": gc.mem_free(),
        }

    def status():
        """The same values as (label, value) pairs for the web page."""
        now_state = state()
        seconds = now_state["uptime_s"]
        return (
            ("Display", "an" if now_state["display_on"] else "aus"),
            ("Adresse", now_state["address"] or "nicht verbunden"),
            ("Laufzeit", "%dh %02dm" % (seconds // 3600, seconds % 3600 // 60)),
            ("Zeit", "%s %s" % (now_state["time"], now_state["zone"]) if now_state["time"] else "nicht synchron"),
            ("MQTT", "verbunden" if now_state["mqtt"] else "getrennt"),
            ("Widget", now_state["widget"]),
            ("Widget-Fehler", ", ".join(w.name for w in widgets if w.failed) or "keine"),
            ("Helligkeit aktiv", "%.2f" % now_state["brightness"]),
            ("Bildrate", "%d Hz" % now_state["frame_hz"]),
            ("Freier Speicher", "%d KB" % (now_state["mem_free"] // 1024)),
        )

    web = WebServer([widget.name for widget in widgets], status, state)

    watchdog = None
    if settings.WATCHDOG_MS:
        try:
            watchdog = machine.WDT(timeout=settings.WATCHDOG_MS)
            print("watchdog: %d ms" % settings.WATCHDOG_MS)
        except (ValueError, OSError) as exc:
            print("watchdog unavailable:", exc)

    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add
    max_sleep = settings.LOOP_MAX_SLEEP_MS

    current = None
    next_draw = ticks_ms()
    last_power = settings.DISPLAY_ON
    if not last_power:
        display.set_brightness(0.0)
    last_second = -1
    last_widget_revision = -1
    last_time_revision = -1

    while True:
        now = ticks_ms()
        if watchdog is not None:
            watchdog.feed()

        net.service(now)
        time_sync.service(net.connected)
        mqtt.service(now, net.connected)
        web.service(now, ctx)
        for w in widgets:
            if w.failed:
                continue
            try:
                w.service(now, ctx)
            except Exception as exc:
                _widget_failed(w, "service", exc)

        # Display on/off (web UI and the /on, /off, /toggle webhooks) and
        # brightness changes; both can happen while the display runs.
        power = settings.DISPLAY_ON
        if power != last_power:
            last_power = power
            fade_ms = settings.TRANSITION_MS or 300
            if power:
                # Draw a fresh frame while still dark, then fade it in.
                current = rotator.current(ctx)
                next_draw = ticks_add(ticks_ms(), _draw(display, current, ctx))
                display.fade_to(settings.BRIGHTNESS, fade_ms)
            else:
                display.fade_to(0.0, fade_ms)
                current = None
        elif power and display.brightness != settings.BRIGHTNESS:
            display.set_brightness(settings.BRIGHTNESS)

        second = now // 1000
        if second != last_second:
            net.update_status_led(second, time_sync.synced)
            last_second = second

        if not power:
            # Nothing to draw while the panel is dark; the services above keep
            # running so the web server and the status LED stay alive.
            time.sleep_ms(max_sleep)
            continue

        rotator.service(now, ctx)
        widget = rotator.current(ctx)

        if widget is not current:
            wait = _switch(display, widget, ctx, current is not None)
            current = widget
            next_draw = ticks_add(ticks_ms(), wait)
        elif (ticks_diff(now, next_draw) >= 0
              or widget.revision != last_widget_revision
              or time_sync.revision != last_time_revision):
            wait = _draw(display, widget, ctx)
            next_draw = ticks_add(now, wait)

        last_widget_revision = widget.revision
        last_time_revision = time_sync.revision

        sleep = ticks_diff(next_draw, ticks_ms())
        if sleep > max_sleep:
            sleep = max_sleep
        if sleep > 0:
            time.sleep_ms(sleep)


def run():
    status_led = Pin("LED", Pin.OUT, value=0)
    try:
        _run(status_led)
    except Exception as exc:
        print("fatal:", exc)
        _fatal_reboot(status_led, code=5)
