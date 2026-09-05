# Visual test for colours and pixel mapping on the panel.
#
# Run from the host:  ./tools/run_demo.sh color
#
# Takes about 25 s and prints for every test what should be visible.

import time

from app.shared.display import Hub75Display, BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE


def step(n, title, expect, seconds):
    print()
    print("=== test %d: %s (%d s) ===" % (n, title, seconds))
    print("    expect: " + expect)


def main():
    d = Hub75Display()
    w, h = d.width, d.height

    step(1, "colour bars",
         "eight vertical bars from left to right: black, red, green, yellow, blue, "
         "magenta, cyan, white. Each 8 pixels wide over the full height, upper and "
         "lower half identical. A wrong order means the R/G/B pins are swapped.", 6)
    d.clear()
    for i, colour in enumerate((BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE)):
        d.fb.fill_rect(i * (w // 8), 0, w // 8, h, colour)
    d.show()
    time.sleep(6)

    step(2, "border, corners, halves",
         "a white border around the whole panel with no pixel missing. One pixel "
         "inside each corner: top left red, top right green, bottom left blue, "
         "bottom right yellow. In the middle two lines directly above each other: "
         "row 15 magenta (last row of the upper half), row 16 cyan (first of the "
         "lower half). A gap or an offset between them would mean the half mapping "
         "is wrong.", 6)
    d.clear()
    d.fb.rect(0, 0, w, h, WHITE)
    d.fb.pixel(1, 1, RED)
    d.fb.pixel(w - 2, 1, GREEN)
    d.fb.pixel(1, h - 2, BLUE)
    d.fb.pixel(w - 2, h - 2, YELLOW)
    d.fb.hline(2, h // 2 - 1, w - 4, MAGENTA)
    d.fb.hline(2, h // 2, w - 4, CYAN)
    d.show()
    time.sleep(6)

    step(3, "coloured text",
         "'12:34' large in yellow at the top, 'T21C' small in cyan at the bottom "
         "left, 'HA' small in white on a blue background at the bottom right. All "
         "characters crisp, no ghost pixels.", 6)
    d.clear()
    d.text_center("12:34", YELLOW, 2, 1)
    d.text("T21C", 2, 22, CYAN, 1)
    d.text("HA", w - 2 - d.font.text_width("HA"), 22, WHITE, 1, BLUE)
    d.show()
    time.sleep(6)

    step(4, "update speed",
         "a white bar sweeps once from left to right over 2 s, smoothly.", 2)
    for x in range(w):
        d.clear()
        d.fb.fill_rect(x, 0, 2, h, WHITE)
        d.show()
        time.sleep_ms(2000 // w)

    step(5, "back", "'--:--' in the default colour.", 1)
    d.show_text("--:--")

    print()
    print("done. Bring back the normal display with: mpremote reset")


main()
