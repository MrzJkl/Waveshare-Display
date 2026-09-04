"""Rendering layer for the HUB75 panel.

Widgets draw on `display.fb`, a framebuf.FrameBuffer in GS8 format: one byte
per pixel holding a colour index 0..7 (bit 0 red, bit 1 green, bit 2 blue).
`display.show()` hands that buffer to the native engine, which converts it
into its DMA stream and refreshes the panel by itself via PIO + DMA.
See native/hub75_native_scan/README.md for how.
"""

import framebuf
import time

from app import settings
from app.font import Font5x7

try:
    import hub75_native_scan
except ImportError:
    hub75_native_scan = None

# Colour indices: bit 0 = red, bit 1 = green, bit 2 = blue.
BLACK = 0
RED = 1
GREEN = 2
YELLOW = 3
BLUE = 4
MAGENTA = 5
CYAN = 6
WHITE = 7


class Hub75Display:
    """Framebuffer and text helpers in Python, panel refresh in hardware.

    Nothing in this class runs in the display's timing path: the native
    engine keeps refreshing the last frame until show() publishes a new one.
    """

    def __init__(self):
        if hub75_native_scan is None:
            raise RuntimeError("hub75_native_scan module missing - build firmware with USER_C_MODULES")

        self.width = settings.MATRIX_WIDTH
        self.height = settings.MATRIX_HEIGHT
        self.scan_rows = settings.SCAN_ROWS
        if self.height != 2 * self.scan_rows:
            raise ValueError("MATRIX_HEIGHT must be 2 * SCAN_ROWS")
        self.text_scale = settings.TEXT_SCALE
        self.on_time_us = settings.ON_TIME_US
        self.brightness = self._clamp(settings.BRIGHTNESS)

        # The drawing surface. Its raw bytes go straight to the native engine.
        self.buf = bytearray(self.width * self.height)
        self.fb = framebuf.FrameBuffer(self.buf, self.width, self.height, framebuf.GS8)
        self.font = Font5x7()

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
    # Frames
    # ------------------------------------------------------------------
    def show(self):
        """Publish the framebuffer.

        The engine renders it into its back buffer and swaps at the next
        frame boundary (no tearing, no dark gap); returns after about one
        frame time. The framebuffer may be drawn on again right away.
        """
        self._native.show_frame(self.buf)

    def clear(self, colour=BLACK):
        self.fb.fill(colour)

    def text(self, text, x, y, colour=WHITE, scale=1, background=None):
        """Draw text with its top-left corner at (x, y); returns the x after it."""
        return self.font.draw(self.fb, text, x, y, colour, scale, background)

    def text_center(self, text, colour=WHITE, scale=None, y=None):
        """Draw text horizontally centred; vertically centred unless y is given."""
        if scale is None:
            scale = self.text_scale
        x = (self.width - self.font.text_width(text, scale)) // 2
        if y is None:
            y = (self.height - self.font.text_height(scale)) // 2
        self.font.draw(self.fb, text, x, y, colour, scale)

    def show_text(self, text, colour=None):
        """Clear, draw `text` centred in the default text colour and show it."""
        self.clear()
        self.text_center(text, settings.TEXT_COLOR if colour is None else colour)
        self.show()

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
