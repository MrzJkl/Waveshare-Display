# Visueller Test fuer Helligkeit und Fading auf dem Panel.
#
# Start vom Host:   ./tools/run_brightness_demo.sh
#   (entspricht: mpremote run tools/brightness_demo.py; mpremote reset)
#
# Das Skript laeuft ca. 60 s, zeigt auf dem Panel nacheinander acht Tests und
# schreibt zu jedem auf die Konsole, was zu sehen sein sollte. Danach main.py
# mit "mpremote reset" wieder starten (macht der Wrapper automatisch).

# Andere Gammakurve ausprobieren, z. B. 1.8 (untere Stufen heller) oder
# 2.8 (untere Stufen dunkler). None = Wert aus app/settings.py (2.2).
GAMMA = None

import time

from app import settings
from app.display import Hub75Display


def step(n, title, expect, seconds):
    print()
    print("=== Test %d: %s (%d s) ===" % (n, title, seconds))
    print("    Erwartung: " + expect)


def main():
    if GAMMA is not None:
        settings.BRIGHTNESS_GAMMA = GAMMA
    print("Gamma:", settings.BRIGHTNESS_GAMMA)

    d = Hub75Display()

    step(1, "Referenz", "Text '100' bei voller Helligkeit, ruhig, ohne Flackern.", 3)
    d.set_brightness(1.0)
    d.show_text("100")
    time.sleep(3)

    levels = (100, 75, 50, 35, 25, 10, 5, 0)
    step(2, "Treppe abwaerts",
         "Jede Stufe 1.5 s. Die Zahl zeigt den Prozentwert. Gleichmaessig dunkler, "
         "jede Stufe flackerfrei, 5 gerade noch sichtbar, 0 komplett schwarz. "
         "Sind 5 und 10 schon schwarz: GAMMA im Skript auf 1.8 setzen.", 12)
    for pct in levels:
        d.show_text(str(pct))
        d.set_brightness(pct / 100)
        s = d.stats()
        print("    %3d %% -> Tastgrad %6.2f %%  Einschieben beleuchtet: %s" % (pct, s["duty_percent"], s["lit_during_shift"]))
        time.sleep(1.5)

    step(3, "Langsamer Fade",
         "'12:34' wird in 5 s weich von dunkel auf hell und in 5 s wieder dunkel. "
         "Keine sichtbaren Spruenge, auch nicht im Bereich um 35-40 %, wo die Engine "
         "intern den Modus wechselt.", 10)
    d.set_brightness(0.0)
    d.show_text("12:34")
    d.fade_to(1.0, 5000)
    d.fade_to(0.0, 5000)

    step(4, "Atmen",
         "Sechs schnelle Zyklen zwischen 15 % und 100 %, je 0.6 s rauf und runter. "
         "Fluessig, kein Ruckeln, kein Flackern in den dunklen Phasen.", 8)
    for _ in range(6):
        d.fade_to(1.0, 600)
        d.fade_to(0.15, 600)
    d.fade_to(1.0, 300)

    texts = ("12:34", "T21C", "HAOK", "88:88")
    step(5, "Sanfter Wechsel",
         "Vier Textwechsel: 0.4 s ausblenden, Text wechseln, 0.4 s einblenden, 1.2 s halten. "
         "Der neue Text darf nie hart oder bei voller Helligkeit aufblitzen.", 8)
    for text in texts:
        d.fade_to(0.0, 400)
        d.show_text(text)
        d.fade_to(1.0, 400)
        time.sleep(1.2)

    step(6, "Harter Wechsel zum Vergleich",
         "Dieselben vier Texte ohne Fade, je 1.2 s. So sieht der Unterschied aus.", 5)
    for text in texts:
        d.show_text(text)
        time.sleep(1.2)

    step(7, "Ruhetest gedimmt",
         "'12:34' bei 10 % fuer 6 s. Aus dem Augenwinkel betrachten: kein Flackern, "
         "kein Wabern, alle Zeilen gleich hell.", 6)
    d.show_text("12:34")
    d.set_brightness(0.10)
    time.sleep(6)

    step(8, "Zurueck",
         "In 1 s zurueck auf den Startwert aus settings.py, dann '--:--'.", 1)
    d.fade_to(settings.BRIGHTNESS, 1000)
    d.show_text("--:--")

    print()
    print("Fertig. Normale Anzeige zurueckholen mit: mpremote reset")


main()
