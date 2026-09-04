"""Rendering layer for the HUB75 panel.

Python draws text into a 1 byte per pixel framebuffer and converts it into
"scan words": one 32-bit word per (scan row, column) holding the GPIO mask of
the RGB pins that are on (upper half via R1/G1/B1, lower half via R2/G2/B2).
That array is handed to the native engine, which refreshes the panel by
itself via PIO + DMA. See native/hub75_native_scan/README.md for how.
"""

import array
import time

from app import settings

try:
    import hub75_native_scan
except ImportError:
    hub75_native_scan = None

try:
    import micropython
except ImportError:
    class _MicroPythonCompat:
        @staticmethod
        def native(func):
            return func

    micropython = _MicroPythonCompat()


FONT_5X7 = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "10000", "10000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
}


class Hub75Display:
    """Frame rendering in Python, panel refresh in hardware.

    The native module refreshes the panel autonomously via PIO + DMA. This
    class only renders frames and hands them over; nothing here runs in the
    display's timing path.
    """

    def __init__(self):
        if hub75_native_scan is None:
            raise RuntimeError("hub75_native_scan module missing - build firmware with USER_C_MODULES")

        self.width = settings.MATRIX_WIDTH
        self.height = settings.MATRIX_HEIGHT
        self.scan_rows = settings.SCAN_ROWS
        self.text_scale = settings.TEXT_SCALE
        self.on_time_us = settings.ON_TIME_US
        self.brightness = self._clamp(settings.BRIGHTNESS)

        self.front_frame = bytearray(self.width * self.height)
        self.back_frame = bytearray(self.width * self.height)

        # One word per (scan row, column): absolute GPIO masks of the RGB pins
        # that are on. This is the hand-over format for the native engine.
        self._scan_words = array.array("I", [0] * (self.width * self.scan_rows))
        self._top_rgb_mask = (1 << settings.R1_PIN) | (1 << settings.G1_PIN) | (1 << settings.B1_PIN)
        self._bot_rgb_mask = (1 << settings.R2_PIN) | (1 << settings.G2_PIN) | (1 << settings.B2_PIN)

        self._native = hub75_native_scan
        self._native.init(
            self.width,
            self.scan_rows,
            settings.R1_PIN,
            settings.G1_PIN,
            settings.B1_PIN,
            settings.R2_PIN,
            settings.G2_PIN,
            settings.B2_PIN,
            settings.ROWSEL_BASE_PIN,
            settings.ROWSEL_N_PINS,
            settings.CLK_PIN,
            settings.LAT_PIN,
            settings.OE_PIN,
            on_time_us=self.on_time_us,
            pio_clkdiv=settings.NATIVE_PIO_CLKDIV,
            clk_half_cycles=settings.NATIVE_CLK_HALF_CYCLES,
            oe_guard_ns=settings.NATIVE_OE_GUARD_NS,
            latch_ns=settings.NATIVE_LATCH_NS,
            addr_ns=settings.NATIVE_ADDR_NS,
            brightness=self._duty(self.brightness),
        )
        print("hub75 native scan:", self._native.stats())

    def stats(self):
        return self._native.stats()

    def set_on_time_us(self, value):
        self.on_time_us = value
        self._native.set_on_time_us(value)

    # ------------------------------------------------------------------
    # Brightness
    # ------------------------------------------------------------------
    @staticmethod
    def _clamp(level):
        return 0.0 if level < 0.0 else 1.0 if level > 1.0 else float(level)

    @staticmethod
    def _duty(level):
        """Perceived level 0.0..1.0 -> linear duty 0..BRIGHTNESS_MAX for the engine."""
        return int((level ** settings.BRIGHTNESS_GAMMA) * hub75_native_scan.BRIGHTNESS_MAX + 0.5)

    def set_brightness(self, level):
        """Set the perceived brightness (0.0 dark .. 1.0 full).

        Takes effect at the next frame boundary, the refresh rate stays the
        same, and the call returns after about one frame time.
        """
        self.brightness = self._clamp(level)
        self._native.set_brightness(self._duty(self.brightness))

    def fade_to(self, level, duration_ms=300):
        """Blocking ramp of the perceived brightness to `level`.

        Building block for soft transitions: fade_to(0.0), show the next
        frame, fade_to(1.0). Steps every FADE_STEP_MS.
        """
        target = self._clamp(level)
        start = self.brightness
        step_ms = settings.FADE_STEP_MS
        steps = max(1, duration_ms // step_ms)
        for i in range(1, steps + 1):
            self.set_brightness(start + (target - start) * i / steps)
            if i < steps:
                time.sleep_ms(step_ms)

    def clear(self):
        self._native.clear()

    def clear_frame(self, buf):
        for i in range(len(buf)):
            buf[i] = 0

    def set_pixel(self, buf, x, y, on=1):
        if 0 <= x < self.width and 0 <= y < self.height:
            buf[y * self.width + x] = 1 if on else 0

    def draw_char(self, buf, x, y, ch, scale=1):
        glyph = FONT_5X7.get(ch, FONT_5X7[" "])
        for gy, row_bits in enumerate(glyph):
            py = y + gy * scale
            for gx, bit in enumerate(row_bits):
                if bit == "1":
                    px = x + gx * scale
                    for sy in range(scale):
                        for sx in range(scale):
                            self.set_pixel(buf, px + sx, py + sy, 1)

    def draw_text_center(self, buf, text, scale=1):
        self.clear_frame(buf)

        char_w = 5 * scale
        char_h = 7 * scale
        spacing = 1
        text_w = len(text) * (char_w + spacing) - spacing
        x = (self.width - text_w) // 2
        y = (self.height - char_h) // 2

        for ch in text:
            self.draw_char(buf, x, y, ch, scale)
            x += char_w + spacing

    def show_text(self, text):
        self.draw_text_center(self.back_frame, text, self.text_scale)
        self.front_frame, self.back_frame = self.back_frame, self.front_frame
        self.show_frame()

    def show_frame(self):
        """Publish front_frame: the native engine renders it into its back
        buffer and swaps at the next frame boundary (no tearing, no gap)."""
        self._rebuild_scan_words()
        self._native.swap_scan_words(self._scan_words)

    @micropython.native
    def _rebuild_scan_words(self):
        frame_local = self.front_frame
        scan_words = self._scan_words
        width = self.width
        scan_rows = self.scan_rows
        top_rgb_mask = self._top_rgb_mask
        bot_rgb_mask = self._bot_rgb_mask

        for row in range(scan_rows):
            top_index = row * width
            bot_index = (row + scan_rows) * width
            row_index = row * width

            for x in range(width):
                top_on = frame_local[top_index + x]
                bot_on = frame_local[bot_index + x]
                scan_words[row_index + x] = (top_rgb_mask if top_on else 0) | (bot_rgb_mask if bot_on else 0)
