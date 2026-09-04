"""Main loop: services (WLAN, time sync, data), widget rotation and drawing.

The panel refreshes itself in hardware, so this loop only has to draw a new
frame when the current widget asks for it or its data changed. It sleeps
until the next such moment, at most LOOP_MAX_SLEEP_MS, so the non-blocking
services get their turn regularly.
"""

import time

import machine
from machine import Pin

from app import settings
from app.shared import timezone
from app.shared.display import Hub75Display
from app.shared.timesync import TimeSync
from app.shared.wifi import WifiService
from app.widgets import create_default_widgets


class Context:
    """What widgets get to look at."""

    def __init__(self, net, time_sync):
        self.net = net          # WifiService: connected
        self.time = time_sync   # TimeSync: now_ms(), zone, health(), synced


class Rotator:
    def __init__(self, widgets, rotate_ms):
        if not widgets:
            raise ValueError("widget list is empty")
        self.widgets = widgets
        self.rotate_ms = rotate_ms
        self.index = 0
        self.next_switch_ms = time.ticks_add(time.ticks_ms(), rotate_ms)

    def current(self, ctx):
        widget = self.widgets[self.index]
        if widget.is_ready(ctx):
            return widget
        for candidate in self.widgets:
            if candidate.is_ready(ctx):
                return candidate
        return self.widgets[0]

    def service(self, now_ticks, ctx):
        if len(self.widgets) < 2 or self.rotate_ms <= 0:
            return
        if time.ticks_diff(now_ticks, self.next_switch_ms) < 0:
            return
        for step in range(1, len(self.widgets) + 1):
            index = (self.index + step) % len(self.widgets)
            if self.widgets[index].is_ready(ctx):
                self.index = index
                break
        self.next_switch_ms = time.ticks_add(now_ticks, self.rotate_ms)


def _led_blink(status_led, count, on_ms=90, off_ms=90, tail_ms=800):
    for _ in range(count):
        status_led.value(1)
        time.sleep_ms(on_ms)
        status_led.value(0)
        time.sleep_ms(off_ms)
    if tail_ms:
        time.sleep_ms(tail_ms)


def _fatal_loop(status_led, code=5):
    while True:
        _led_blink(status_led, code)


def _draw(display, widget, ctx):
    wait = widget.draw(display, ctx)
    display.show()
    return 1000 if wait is None else max(1, wait)


def _switch(display, widget, ctx, fade):
    """Show a different widget, with a fade out / fade in when fade is set."""
    level = display.brightness
    if fade:
        display.fade_to(0.0, settings.TRANSITION_MS)
    wait = _draw(display, widget, ctx)
    if fade:
        display.fade_to(level, settings.TRANSITION_MS)
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
    ctx = Context(net, time_sync)
    widgets = create_default_widgets()
    rotator = Rotator(widgets, settings.WIDGET_ROTATE_MS)

    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add
    max_sleep = settings.LOOP_MAX_SLEEP_MS
    fade = settings.TRANSITION_MS > 0

    current = None
    next_draw = ticks_ms()
    last_second = -1
    last_widget_revision = -1
    last_time_revision = -1

    while True:
        now = ticks_ms()

        net.service(now)
        time_sync.service(net.connected)
        for w in widgets:
            w.service(now, ctx)

        second = now // 1000
        if second != last_second:
            net.update_status_led(second, time_sync.synced)
            last_second = second

        rotator.service(now, ctx)
        widget = rotator.current(ctx)

        if widget is not current:
            wait = _switch(display, widget, ctx, fade and current is not None)
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
        _fatal_loop(status_led, code=5)
