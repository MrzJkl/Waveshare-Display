import time

import machine
from machine import Pin

from app import settings
from app.boot import BootService
from app.data import DataProviders
from app.display import Hub75Display
from app.modules import create_default_modules


class ModuleRotator:
    def __init__(self, modules, rotate_ms):
        if not modules:
            raise ValueError("modules list is empty")

        self.modules = modules
        self.rotate_ms = rotate_ms
        self.index = 0
        self.next_switch_ms = time.ticks_add(time.ticks_ms(), rotate_ms)

    def current(self, providers, boot_state):
        module = self.modules[self.index]
        if module.is_ready(providers, boot_state):
            return module

        for candidate in self.modules:
            if candidate.is_ready(providers, boot_state):
                return candidate

        return self.modules[0]

    def service(self, now_ticks, providers, boot_state):
        if len(self.modules) < 2:
            return False
        if time.ticks_diff(now_ticks, self.next_switch_ms) < 0:
            return False

        for step in range(1, len(self.modules) + 1):
            candidate_index = (self.index + step) % len(self.modules)
            candidate = self.modules[candidate_index]
            if candidate.is_ready(providers, boot_state):
                self.index = candidate_index
                break
        self.next_switch_ms = time.ticks_add(now_ticks, self.rotate_ms)
        return True


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


def _run(status_led):
    print("hub75 modular runtime start")

    try:
        machine.freq(settings.CPU_FREQ_HZ)
    except Exception as exc:
        print("cpu freq unchanged:", exc)

    display = Hub75Display()
    boot = BootService(status_led)
    providers = DataProviders()
    rotator = ModuleRotator(create_default_modules(), settings.MODULE_ROTATE_MS)

    display.show_text("--:--")

    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add

    next_service = ticks_ms()
    last_second = -1
    last_text = ""
    force_redraw = True

    while True:
        display.scan_batch(settings.SCAN_BATCH)

        now_ticks = ticks_ms()
        if ticks_diff(now_ticks, next_service) < 0:
            continue
        next_service = ticks_add(now_ticks, settings.SERVICE_INTERVAL_MS)

        rtc_changed = boot.service(now_ticks)
        providers.service(now_ticks, boot)
        module_changed = rotator.service(now_ticks, providers, boot)

        now = time.localtime()
        sec = now[5]
        if sec != last_second:
            boot.update_status_led(sec)
            last_second = sec

        module = rotator.current(providers, boot)
        text = module.render(now, providers, boot)
        if not text:
            text = "--:--"

        if force_redraw or rtc_changed or module_changed or text != last_text:
            display.show_text(text)
            last_text = text
            force_redraw = False


def run():
    status_led = Pin("LED", Pin.OUT, value=0)
    try:
        _run(status_led)
    except Exception as exc:
        print("fatal:", exc)
        _fatal_loop(status_led, code=5)
