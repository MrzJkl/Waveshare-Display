import time
from machine import Pin

from app import settings

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

    @micropython.native
    def scan_frame_once(self):
        r1_value = self.r1.value
        g1_value = self.g1.value
        b1_value = self.b1.value
        r2_value = self.r2.value
        g2_value = self.g2.value
        b2_value = self.b2.value
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
        frame_local = self.front_frame

        for row in range(scan_rows):
            oe_on()

            row0_value(row & 0x01)
            row1_value((row >> 1) & 0x01)
            row2_value((row >> 2) & 0x01)
            row3_value((row >> 3) & 0x01)

            top_index = row * width
            bot_index = (row + scan_rows) * width

            for x in range(width):
                top_on = frame_local[top_index + x]
                bot_on = frame_local[bot_index + x]

                r1_value(top_on)
                g1_value(top_on)
                b1_value(top_on)
                r2_value(bot_on)
                g2_value(bot_on)
                b2_value(bot_on)
                clk_on()
                clk_off()

            lat_on()
            lat_off()

            oe_off()
            sleep_us(on_time_us)

    def scan_batch(self, count):
        for _ in range(count):
            self.scan_frame_once()
