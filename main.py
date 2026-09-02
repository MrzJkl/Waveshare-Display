import time

import machine
import network
import socket
from machine import Pin, RTC

try:
    import micropython
except ImportError:
    class _MicroPythonCompat:
        @staticmethod
        def native(func):
            return func

    micropython = _MicroPythonCompat()


# Pure-MicroPython HUB75 clock demo (64x32, 1/16 scan).
MATRIX_WIDTH = 64
MATRIX_HEIGHT = 32
SCAN_ROWS = 16

DATA_BASE_PIN = 0
R1_PIN = DATA_BASE_PIN + 0
G1_PIN = DATA_BASE_PIN + 1
B1_PIN = DATA_BASE_PIN + 2
R2_PIN = DATA_BASE_PIN + 3
G2_PIN = DATA_BASE_PIN + 4
B2_PIN = DATA_BASE_PIN + 5

ROWSEL_BASE_PIN = 6
ROWSEL_N_PINS = 4
CLK_PIN = 11
LAT_PIN = 12
OE_PIN = 13

ON_TIME_US = 45
SERVICE_INTERVAL_MS = 700
SCAN_BATCH = 10
WIFI_RETRY_MS = 15000
NTP_RETRY_MS = 60000
NTP_RESYNC_MS = 60 * 60 * 1000
NTP_TIMEOUT_S = 0.1
CPU_FREQ_HZ = 250_000_000
WLAN_PM_PERF = 0xA11140
TEXT_SCALE = 2
UTC_OFFSET_HOURS = 2
NTP_HOST = "192.168.178.1"
NTP_PORT = 123
NTP_DELTA = 2208988800

try:
    from wifi_config import WIFI_PASSWORD, WIFI_SSID
except ImportError:
    WIFI_SSID = ""
    WIFI_PASSWORD = ""


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
}


status_led = Pin("LED", Pin.OUT, value=0)

r1 = Pin(R1_PIN, Pin.OUT, value=0)
g1 = Pin(G1_PIN, Pin.OUT, value=0)
b1 = Pin(B1_PIN, Pin.OUT, value=0)
r2 = Pin(R2_PIN, Pin.OUT, value=0)
g2 = Pin(G2_PIN, Pin.OUT, value=0)
b2 = Pin(B2_PIN, Pin.OUT, value=0)

row_pins = [Pin(ROWSEL_BASE_PIN + i, Pin.OUT, value=0) for i in range(ROWSEL_N_PINS)]

clk = Pin(CLK_PIN, Pin.OUT, value=0)
lat = Pin(LAT_PIN, Pin.OUT, value=0)
oe = Pin(OE_PIN, Pin.OUT, value=1)  # active-low OE, so 1 means blanked

front_frame = bytearray(MATRIX_WIDTH * MATRIX_HEIGHT)
back_frame = bytearray(MATRIX_WIDTH * MATRIX_HEIGHT)
rtc = RTC()


def led_set(is_on):
    status_led.value(1 if is_on else 0)


def led_blink(count, on_ms=100, off_ms=100, tail_ms=250):
    for _ in range(count):
        led_set(True)
        time.sleep_ms(on_ms)
        led_set(False)
        time.sleep_ms(off_ms)
    if tail_ms:
        time.sleep_ms(tail_ms)


def fatal_loop(code=5):
    while True:
        led_blink(code, on_ms=90, off_ms=90, tail_ms=800)


def clear_frame(buf):
    for i in range(len(buf)):
        buf[i] = 0


def set_pixel(buf, x, y, on=1):
    if 0 <= x < MATRIX_WIDTH and 0 <= y < MATRIX_HEIGHT:
        buf[y * MATRIX_WIDTH + x] = 1 if on else 0


def draw_char(buf, x, y, ch, scale=1):
    glyph = FONT_5X7.get(ch, FONT_5X7[" "])
    for gy, row_bits in enumerate(glyph):
        py = y + gy * scale
        for gx, bit in enumerate(row_bits):
            if bit == "1":
                px = x + gx * scale
                for sy in range(scale):
                    for sx in range(scale):
                        set_pixel(buf, px + sx, py + sy, 1)


def draw_text_center(buf, text, scale=1):
    clear_frame(buf)

    char_w = 5 * scale
    char_h = 7 * scale
    spacing = 1
    text_w = len(text) * (char_w + spacing) - spacing
    x = (MATRIX_WIDTH - text_w) // 2
    y = (MATRIX_HEIGHT - char_h) // 2

    for ch in text:
        draw_char(buf, x, y, ch, scale)
        x += char_w + spacing


def connect_wifi(timeout_s=20):
    if not WIFI_SSID or not WIFI_PASSWORD:
        raise RuntimeError("wifi_config missing or empty")

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print("wifi already connected:", wlan.ifconfig()[0])
        return wlan

    print("connecting wifi:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    start_ms = time.ticks_ms()
    pulse = False
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start_ms) > timeout_s * 1000:
            raise RuntimeError("wifi connect timeout")
        pulse = not pulse
        led_set(pulse)
        time.sleep_ms(120)

    print("wifi connected:", wlan.ifconfig()[0])
    led_set(True)
    return wlan


def set_rtc_from_unix_epoch(unix_seconds):
    tm = time.localtime(unix_seconds)
    rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))


def sync_ntp(max_tries=4):
    for attempt in range(1, max_tries + 1):
        sock = None
        try:
            addr = socket.getaddrinfo(NTP_HOST, NTP_PORT)[0][-1]
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(NTP_TIMEOUT_S)

            packet = bytearray(48)
            packet[0] = 0x1B
            sock.sendto(packet, addr)
            data = sock.recv(48)

            if len(data) < 48:
                raise RuntimeError("short ntp response")

            ntp_seconds = (data[40] << 24) | (data[41] << 16) | (data[42] << 8) | data[43]
            unix_seconds = ntp_seconds - NTP_DELTA
            if unix_seconds <= 0:
                raise RuntimeError("invalid ntp timestamp")

            set_rtc_from_unix_epoch(unix_seconds)
            print("ntp sync ok via", NTP_HOST, "unix", unix_seconds)
            return True
        except Exception as exc:
            print("ntp retry", attempt, exc)
            led_set(False)
        finally:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass

    return False


@micropython.native
def scan_frame_once():
    r1_value = r1.value
    g1_value = g1.value
    b1_value = b1.value
    r2_value = r2.value
    g2_value = g2.value
    b2_value = b2.value
    row0_value = row_pins[0].value
    row1_value = row_pins[1].value
    row2_value = row_pins[2].value
    row3_value = row_pins[3].value
    clk_on = clk.on
    clk_off = clk.off
    lat_on = lat.on
    lat_off = lat.off
    oe_on = oe.on
    oe_off = oe.off
    sleep_us = time.sleep_us
    width = MATRIX_WIDTH
    frame_local = front_frame

    for row in range(SCAN_ROWS):
        oe_on()

        row0_value(row & 0x01)
        row1_value((row >> 1) & 0x01)
        row2_value((row >> 2) & 0x01)
        row3_value((row >> 3) & 0x01)

        top_index = row * width
        bot_index = (row + SCAN_ROWS) * width

        for x in range(width):
            top_on = frame_local[top_index + x]
            bot_on = frame_local[bot_index + x]

            # White text: drive all three channels with the same monochrome bit.
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
        sleep_us(ON_TIME_US)


def run_clock_loop():
    global front_frame
    global back_frame

    print("hub75 micropython ntp clock start")
    led_blink(2, on_ms=80, off_ms=80, tail_ms=180)

    try:
        machine.freq(CPU_FREQ_HZ)
    except Exception as exc:
        print("cpu freq unchanged:", exc)

    # Draw immediately so the panel is visibly alive even if Wi-Fi/NTP is slow.
    draw_text_center(back_frame, "--:--", TEXT_SCALE)
    front_frame, back_frame = back_frame, front_frame

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.config(pm=WLAN_PM_PERF)
    except Exception:
        pass

    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add

    next_wifi_try = ticks_ms()
    next_ntp_try = ticks_ms()
    next_service = ticks_ms()
    ntp_synced = False

    last_second = -1
    last_minute_key = -1
    force_redraw = True

    while True:
        for _ in range(SCAN_BATCH):
            scan_frame_once()

        now_ticks = ticks_ms()
        if ticks_diff(now_ticks, next_service) < 0:
            continue
        next_service = ticks_add(now_ticks, SERVICE_INTERVAL_MS)

        if ticks_diff(now_ticks, next_wifi_try) >= 0 and not wlan.isconnected():
            if WIFI_SSID and WIFI_PASSWORD:
                try:
                    print("wifi connect request")
                    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
                except Exception as exc:
                    print("wifi connect error:", exc)
            next_wifi_try = ticks_add(now_ticks, WIFI_RETRY_MS)

        if wlan.isconnected() and ticks_diff(now_ticks, next_ntp_try) >= 0:
            if sync_ntp(max_tries=1):
                ntp_synced = True
                force_redraw = True
                next_ntp_try = ticks_add(now_ticks, NTP_RESYNC_MS)
            else:
                next_ntp_try = ticks_add(now_ticks, NTP_RETRY_MS)

        now = time.localtime()
        sec = now[5]
        if sec != last_second:
            # Solid beat when NTP synced, blink beat before first successful sync.
            led_set((sec & 1) == 0 if ntp_synced else (sec % 3 == 0))
            last_second = sec

        hour = (now[3] + UTC_OFFSET_HOURS) % 24
        minute = now[4]
        minute_key = hour * 60 + minute
        if force_redraw or minute_key != last_minute_key:
            draw_text_center(back_frame, "{:02d}:{:02d}".format(hour, minute), TEXT_SCALE)
            front_frame, back_frame = back_frame, front_frame
            last_minute_key = minute_key
            force_redraw = False


try:
    run_clock_loop()
except Exception as exc:
    print("fatal:", exc)
    fatal_loop(code=5)