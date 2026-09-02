import array
import time

import machine
from machine import Pin

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

        @staticmethod
        def viper(func):
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
    def __init__(self):
        self.width = settings.MATRIX_WIDTH
        self.height = settings.MATRIX_HEIGHT
        self.scan_rows = settings.SCAN_ROWS
        self.text_scale = settings.TEXT_SCALE
        self.on_time_us = settings.ON_TIME_US

        self.r1 = Pin(settings.R1_PIN, Pin.OUT, value=0)
        self.g1 = Pin(settings.G1_PIN, Pin.OUT, value=0)
        self.b1 = Pin(settings.B1_PIN, Pin.OUT, value=0)
        self.r2 = Pin(settings.R2_PIN, Pin.OUT, value=0)
        self.g2 = Pin(settings.G2_PIN, Pin.OUT, value=0)
        self.b2 = Pin(settings.B2_PIN, Pin.OUT, value=0)

        self.row_pins = [
            Pin(settings.ROWSEL_BASE_PIN + i, Pin.OUT, value=0)
            for i in range(settings.ROWSEL_N_PINS)
        ]

        self.clk = Pin(settings.CLK_PIN, Pin.OUT, value=0)
        self.lat = Pin(settings.LAT_PIN, Pin.OUT, value=0)
        self.oe = Pin(settings.OE_PIN, Pin.OUT, value=1)  # Active-low OE.

        self.front_frame = bytearray(self.width * self.height)
        self.back_frame = bytearray(self.width * self.height)

        self._scan_words = array.array("I", [0] * (self.width * self.scan_rows))

        self._top_rgb_mask = (1 << settings.R1_PIN) | (1 << settings.G1_PIN) | (1 << settings.B1_PIN)
        self._bot_rgb_mask = (1 << settings.R2_PIN) | (1 << settings.G2_PIN) | (1 << settings.B2_PIN)
        self._rgb_mask = self._top_rgb_mask | self._bot_rgb_mask
        self._clk_mask = 1 << settings.CLK_PIN
        self._lat_mask = 1 << settings.LAT_PIN
        self._oe_mask = 1 << settings.OE_PIN

        self._row_mask_all = 0
        for idx in range(settings.ROWSEL_N_PINS):
            self._row_mask_all |= 1 << (settings.ROWSEL_BASE_PIN + idx)

        self._row_masks = array.array("I", [0] * self.scan_rows)
        for row in range(self.scan_rows):
            row_mask = 0
            for bit_idx in range(settings.ROWSEL_N_PINS):
                if row & (1 << bit_idx):
                    row_mask |= 1 << (settings.ROWSEL_BASE_PIN + bit_idx)
            self._row_masks[row] = row_mask

        self._gpio_set_addr = settings.SIO_GPIO_OUT_SET
        self._gpio_clr_addr = settings.SIO_GPIO_OUT_CLR
        self._mem32 = getattr(machine, "mem32", None)
        self._native_scan = hub75_native_scan
        self._use_native_scan = False
        self._use_fast_gpio = settings.USE_FAST_GPIO_SCAN and self._mem32 is not None

        if settings.USE_NATIVE_SCAN_ENGINE and self._native_scan is not None:
            try:
                self._native_scan.init(
                    self.width,
                    self.scan_rows,
                    self.on_time_us,
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
                    settings.NATIVE_DATA_SETUP_NOPS,
                    settings.NATIVE_CLK_HIGH_NOPS,
                    settings.NATIVE_LAT_HIGH_NOPS,
                )
                self._use_native_scan = True
            except Exception as exc:
                print("native scan disabled:", exc)
                self._use_native_scan = False

        self._rebuild_scan_words()
        self._publish_scan_words()

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
        self._rebuild_scan_words()
        self._publish_scan_words()

    def _publish_scan_words(self):
        if self._use_native_scan:
            self._native_scan.swap_scan_words(self._scan_words)

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

    @micropython.native
    def _scan_frame_once_fast(self):
        mem32 = self._mem32
        gpio_set = self._gpio_set_addr
        gpio_clr = self._gpio_clr_addr
        rgb_mask = self._rgb_mask
        clk_mask = self._clk_mask
        lat_mask = self._lat_mask
        oe_mask = self._oe_mask
        row_mask_all = self._row_mask_all
        row_masks = self._row_masks
        scan_words = self._scan_words
        width = self.width
        scan_rows = self.scan_rows
        sleep_us = time.sleep_us
        on_time_us = self.on_time_us

        for row in range(scan_rows):
            mem32[gpio_set] = oe_mask

            mem32[gpio_clr] = row_mask_all
            mem32[gpio_set] = row_masks[row]

            row_index = row * width
            for x in range(width):
                mem32[gpio_clr] = rgb_mask
                mem32[gpio_set] = scan_words[row_index + x]
                mem32[gpio_set] = clk_mask
                mem32[gpio_clr] = clk_mask

            mem32[gpio_set] = lat_mask
            mem32[gpio_clr] = lat_mask

            mem32[gpio_clr] = oe_mask
            sleep_us(on_time_us)

        # Keep output blanked between frame scans to avoid row hold artifacts.
        mem32[gpio_set] = oe_mask

    @micropython.native
    def _scan_frame_once_compat(self):
        r1_on = self.r1.on
        r1_off = self.r1.off
        g1_on = self.g1.on
        g1_off = self.g1.off
        b1_on = self.b1.on
        b1_off = self.b1.off
        r2_on = self.r2.on
        r2_off = self.r2.off
        g2_on = self.g2.on
        g2_off = self.g2.off
        b2_on = self.b2.on
        b2_off = self.b2.off
        row0_value = self.row_pins[0].value
        row1_value = self.row_pins[1].value
        row2_value = self.row_pins[2].value
        row3_value = self.row_pins[3].value
        clk_on = self.clk.on
        clk_off = self.clk.off
        lat_on = self.lat.on
        lat_off = self.lat.off
        oe_on = self.oe.on
        oe_off = self.oe.off
        sleep_us = time.sleep_us
        width = self.width
        scan_rows = self.scan_rows
        on_time_us = self.on_time_us
        scan_words = self._scan_words
        top_mask = self._top_rgb_mask
        bot_mask = self._bot_rgb_mask

        for row in range(scan_rows):
            oe_on()

            row0_value(row & 0x01)
            row1_value((row >> 1) & 0x01)
            row2_value((row >> 2) & 0x01)
            row3_value((row >> 3) & 0x01)

            row_index = row * width
            for x in range(width):
                rgb_bits = scan_words[row_index + x]

                if rgb_bits & top_mask:
                    r1_on()
                    g1_on()
                    b1_on()
                else:
                    r1_off()
                    g1_off()
                    b1_off()

                if rgb_bits & bot_mask:
                    r2_on()
                    g2_on()
                    b2_on()
                else:
                    r2_off()
                    g2_off()
                    b2_off()

                clk_on()
                clk_off()

            lat_on()
            lat_off()

            oe_off()
            sleep_us(on_time_us)

        # Keep output blanked between frame scans to avoid row hold artifacts.
        oe_on()

    @micropython.native
    def scan_frame_once(self):
        if self._use_native_scan:
            self._native_scan.scan_once()
            return

        if self._use_fast_gpio:
            self._scan_frame_once_fast()
            return

        self._scan_frame_once_compat()

    def scan_batch(self, count):
        if self._use_native_scan:
            self._native_scan.scan_batch(count)
            return

        for _ in range(count):
            self.scan_frame_once()
