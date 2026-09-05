# Visual test for brightness and fading on the panel.
#
# Run from the host:  ./tools/run_demo.sh brightness
#   (equivalent to: mpremote run tools/brightness_demo.py; mpremote reset)
#
# Takes about 60 s, shows eight tests on the panel and prints for each of them
# what should be visible. Afterwards restart main.py with "mpremote reset";
# the wrapper script does that for you.

# Try a different gamma curve, for example 1.8 (lower steps brighter) or
# 2.8 (lower steps darker). None uses the value from app/settings.py (2.2).
GAMMA = None

import time

from app import settings
from app.shared.display import Hub75Display


def step(n, title, expect, seconds):
    print()
    print("=== test %d: %s (%d s) ===" % (n, title, seconds))
    print("    expect: " + expect)


def main():
    if GAMMA is not None:
        settings.BRIGHTNESS_GAMMA = GAMMA
    print("gamma:", settings.BRIGHTNESS_GAMMA)

    d = Hub75Display()

    step(1, "reference", "the text '100' at full brightness, steady, no flicker.", 3)
    d.set_brightness(1.0)
    d.show_text("100")
    time.sleep(3)

    levels = (100, 75, 50, 35, 25, 10, 5, 0)
    step(2, "staircase down",
         "1.5 s per step, the number is the percentage. Evenly darker, every step "
         "flicker free, 5 just barely visible, 0 completely black. If 5 and 10 are "
         "already black, set GAMMA in this script to 1.8.", 12)
    for pct in levels:
        d.show_text(str(pct))
        d.set_brightness(pct / 100)
        s = d.stats()
        print("    %3d %% -> duty %6.2f %%  lit while shifting: %s" % (pct, s["duty_percent"], s["lit_during_shift"]))
        time.sleep(1.5)

    step(3, "slow fade",
         "'12:34' fades from dark to bright over 5 s and back over 5 s. No visible "
         "steps, especially not around 35-40 % where the engine switches its "
         "internal mode.", 10)
    d.set_brightness(0.0)
    d.show_text("12:34")
    d.fade_to(1.0, 5000)
    d.fade_to(0.0, 5000)

    step(4, "breathing",
         "six quick cycles between 15 % and 100 %, 0.6 s each way. Smooth, no "
         "stutter, no flicker in the dark phases.", 8)
    for _ in range(6):
        d.fade_to(1.0, 600)
        d.fade_to(0.15, 600)
    d.fade_to(1.0, 300)

    texts = ("12:34", "T21C", "HAOK", "88:88")
    step(5, "soft change",
         "four text changes: fade out 0.4 s, swap the text, fade in 0.4 s, hold 1.2 s. "
         "The new text must never appear abruptly or at full brightness.", 8)
    for text in texts:
        d.fade_to(0.0, 400)
        d.show_text(text)
        d.fade_to(1.0, 400)
        time.sleep(1.2)

    step(6, "hard change for comparison",
         "the same four texts without a fade, 1.2 s each. That is the difference.", 5)
    for text in texts:
        d.show_text(text)
        time.sleep(1.2)

    step(7, "steady test, dimmed",
         "'12:34' at 10 % for 6 s. Look at it from the corner of your eye: no "
         "flicker, no shimmer, all rows equally bright.", 6)
    d.show_text("12:34")
    d.set_brightness(0.10)
    time.sleep(6)

    step(8, "back",
         "one second back to the start value from settings.py, then '--:--'.", 1)
    d.fade_to(settings.BRIGHTNESS, 1000)
    d.show_text("--:--")

    print()
    print("done. Bring back the normal display with: mpremote reset")


main()
