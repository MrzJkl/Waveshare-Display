# Visueller Test fuer Farben und Pixelzuordnung auf dem Panel.
#
# Start vom Host:   ./tools/run_demo.sh color
#
# Laeuft ca. 25 s. Zu jedem Test steht auf der Konsole, was zu sehen sein soll.

import time

from app.shared.display import Hub75Display, BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE


def step(n, title, expect, seconds):
    print()
    print("=== Test %d: %s (%d s) ===" % (n, title, seconds))
    print("    Erwartung: " + expect)


def main():
    d = Hub75Display()
    w, h = d.width, d.height

    step(1, "Farbbalken",
         "Acht senkrechte Balken von links nach rechts: schwarz, rot, gruen, gelb, blau, "
         "magenta, cyan, weiss. Jeder 8 Pixel breit ueber die volle Hoehe, obere und untere "
         "Haelfte identisch. Stimmt die Reihenfolge nicht, sind R/G/B-Pins vertauscht.", 6)
    d.clear()
    for i, colour in enumerate((BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE)):
        d.fb.fill_rect(i * (w // 8), 0, w // 8, h, colour)
    d.show()
    time.sleep(6)

    step(2, "Rahmen, Ecken, Haelften",
         "Weisser Rahmen um das ganze Panel, kein Pixel fehlt. Innen in den Ecken je ein Pixel: "
         "oben links rot, oben rechts gruen, unten links blau, unten rechts gelb. "
         "In der Mitte zwei Linien direkt untereinander: Zeile 15 magenta (letzte Zeile der "
         "oberen Haelfte), Zeile 16 cyan (erste der unteren). Luecke oder Versatz dazwischen "
         "waere ein Fehler in der Haelften-Zuordnung.", 6)
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

    step(3, "Text in Farben",
         "Oben '12:34' gross in gelb, unten links 'T21C' klein in cyan, unten rechts 'HA' "
         "klein weiss auf blauem Hintergrund. Alle Zeichen scharf, keine Geisterpixel.", 6)
    d.clear()
    d.text_center("12:34", YELLOW, 2, 1)
    d.text("T21C", 2, 22, CYAN, 1)
    d.text("HA", w - 2 - d.font.text_width("HA"), 22, WHITE, 1, BLUE)
    d.show()
    time.sleep(6)

    step(4, "Update-Geschwindigkeit",
         "Ein weisser Balken laeuft in 2 s einmal von links nach rechts durch, fluessig.", 2)
    for x in range(w):
        d.clear()
        d.fb.fill_rect(x, 0, 2, h, WHITE)
        d.show()
        time.sleep_ms(2000 // w)

    step(5, "Zurueck", "'--:--' in der Standardfarbe.", 1)
    d.show_text("--:--")

    print()
    print("Fertig. Normale Anzeige zurueckholen mit: mpremote reset")


main()
