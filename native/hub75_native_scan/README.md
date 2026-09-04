# hub75_native_scan: autonome HUB75-Ansteuerung mit PIO und DMA

Dieses Verzeichnis enthaelt das User-C-Modul `hub75_native_scan`. Es refresht das HUB75-Panel
komplett in Hardware (PIO + DMA), ohne dass die CPU beteiligt ist. MicroPython zeichnet nur noch
Frames und uebergibt sie.

Dieses Dokument erklaert von unten nach oben, was dabei passiert. Es richtet sich an Leser, die
MicroPython kennen, aber noch wenig hardwarenah entwickelt haben.

## Inhalt

1. Dateien und Lesereihenfolge
2. Wie ein HUB75-Panel angesteuert wird
3. Warum PIO + DMA und nicht die CPU
4. PIO: kleine Zustandsautomaten mit exaktem Timing
5. Der Wortstrom: die Daten, die die PIO abspielt
6. Die DMA-Kette: der endlose Zubringer
7. Timing-Rechnung
8. Lebenszyklus und Zusammenspiel mit MicroPython
9. Tuning und Fehlersuche
10. Ideen fuer Erweiterungen

## 1. Dateien und Lesereihenfolge

| Datei | Aufgabe |
| --- | --- |
| `hub75.h` | Oeffentliche C-API: Konfiguration, Ergebniscodes, Funktionen. Kennt kein MicroPython. |
| `hub75_internal.h` | Gemeinsamer Zustand (`hub75_t`) und der Vertrag ueber das Wortstrom-Format. |
| `hub75_stream.c` | Baut den Wortstrom aus Pixeln, Steuerwoertern und Wartezaehlern; rechnet ns in Takte um. |
| `hub75_pio.c` | Das PIO-Programm, seine State-Machine und die Pin-Uebernahme. |
| `hub75_dma.c` | Die DMA-Kette, die den Wortstrom endlos in die PIO schiebt, und der Frame-Wechsel. |
| `hub75_driver.c` | Lebenszyklus: pruefen, ableiten, starten, stoppen, Diagnose. Haelt die einzige Instanz. |
| `mod_hub75_native_scan.c` | MicroPython-Anbindung: Argumente parsen, Ergebniscodes in Exceptions uebersetzen. |
| `micropython.cmake` | Einbindung in den MicroPython-Build (`-DUSER_C_MODULES=...`). |

Empfohlene Reihenfolge: dieses Dokument, dann `hub75_internal.h` (das Format), `hub75_stream.c`,
`hub75_pio.c`, `hub75_dma.c`, `hub75_driver.c`, zuletzt die Anbindung.

Abhaengigkeiten laufen nur in eine Richtung: die Anbindung kennt `hub75.h`, der Treiber kennt die
drei Bausteine, die Bausteine kennen nur `hub75_internal.h` und die pico-sdk.

## 2. Wie ein HUB75-Panel angesteuert wird

Ein 64x32-Panel mit 1/16-Scan hat keinen Framebuffer. Es kann zu jedem Zeitpunkt nur **zwei
Zeilen** anzeigen: Zeile `n` (obere Haelfte) und Zeile `n + 16` (untere Haelfte). Welche das sind,
bestimmen die Adressleitungen A..D (4 Bit = 16 Zeilenpaare). Das komplette Bild entsteht nur, weil
der Controller alle 16 Adressen so schnell nacheinander durchlaeuft, dass das Auge ein stehendes
Bild sieht.

Signale am HUB75-Stecker (Pinbelegung in `app/settings.py`):

| Signal | GPIO | Bedeutung |
| --- | --- | --- |
| R1 G1 B1 | 0 1 2 | Farbdaten obere Haelfte, 1 Bit pro Farbe (an/aus) |
| R2 G2 B2 | 3 4 5 | Farbdaten untere Haelfte |
| A B C D | 6 7 8 9 | Zeilenadresse 0..15 |
| CLK | 11 | Schiebetakt: bei jeder steigenden Flanke wandert ein Pixel in die Schieberegister |
| LAT (STB) | 12 | Latch: kopiert den Inhalt der Schieberegister in die Ausgangs-Latches |
| OE | 13 | Output Enable, **active low**: 0 = LEDs an, 1 = LEDs aus |

Pro Farbleitung sitzt im Panel ein 64 Bit langes Schieberegister. Um eine Zeile zu setzen, legt man
fuer jedes der 64 Pixel die 6 Farbbits an und gibt einen CLK-Puls. Danach steht die Zeile in den
Schieberegistern, ist aber noch nicht sichtbar. Sichtbar wird sie mit dem LAT-Puls, der sie in die
Ausgangs-Latches uebernimmt. Die Adressleitungen waehlen das Zeilenpaar, OE schaltet die
LED-Treiber frei.

Sequenz fuer eine Scanzeile, wie diese Engine sie faehrt:

```
1. 64 Pixel der NAECHSTEN Zeile einschieben     die aktuelle Zeile leuchtet dabei weiter
2. OE = 1                                        Panel dunkel (Guard, 60 ns)
3. LAT = 1, dann LAT = 0                         Daten in die Latches (120 ns Puls, 120 ns Settle)
4. Adresse A..D = neue Zeile                     Zeilentreiber umschalten (200 ns Settle)
5. OE = 0                                        neue Zeile leuchtet (Leuchtphase)
6. OE = 1                                        Dunkelphase; 5 + 6 zusammen = ON_TIME_US (32 us)
   -> zurueck zu 1 fuer die naechste Zeile
```

Bei voller Helligkeit bleibt die Zeile auch in Schritt 1 an und die Dunkelphase ist minimal. Zum
Dimmen wandert Zeit von Schritt 5 nach Schritt 6, und unterhalb einer Schwelle ist auch Schritt 1
dunkel. Die Zeilendauer bleibt dabei immer gleich (Kapitel 5, "Helligkeit").

Als Zeitdiagramm (nicht massstaeblich):

```
        |<------ 1: 64 Pixel einschieben ------>| 2 | 3     | 4    |<----- 5: leuchten ----->| 6  |
RGB   --< p0 >< p1 >< p2 > ...... < p63 >-----------------------------------------------------------
CLK   __/--\__/--\__/--\__ ...... /--\______________________________________________________________
LAT   _________________________________________/-----\______________________________________________
A..D  ====== Adresse n-1 ==============================|====== Adresse n ===========================
OE    ______________________________________/------------------\_________________________/--------
        leuchtet: Zeile n-1                    dunkel            leuchtet: Zeile n          dunkel
```

(Volle Helligkeit: Schritt 6 ist dann nur drei Takte lang.)

Zwei Dinge sind fuer ein sauberes Bild entscheidend:

- **Gleichmaessigkeit.** Jede Zeile muss in jedem Durchlauf genau gleich lang leuchten. Leuchtet
  eine Zeile mal laenger, weil der Controller gerade etwas anderes tut, blitzt sie heller auf. Faellt
  ein Durchlauf aus, wird das Bild dunkel. Beides sieht man als Flackern.
- **Reihenfolge und Pausen beim Umschalten.** Wechselt die Adresse, waehrend OE noch aktiv ist,
  leuchtet kurz die falsche Zeile mit ("Ghosting"). Wird OE zu frueh wieder aktiv, sind die
  Zeilentreiber noch am Umschalten. Daher die kurzen Wartezeiten in den Schritten 2 bis 4.

## 3. Warum PIO + DMA und nicht die CPU

Die alte Loesung hat die Sequenz aus Kapitel 2 in einer C-Schleife auf der CPU gefahren, aufgerufen
aus dem Python-Hauptloop. Das Problem: MicroPython macht laufend Pausen, die die CPU komplett
beanspruchen: Garbage Collection (mehrere Millisekunden), WLAN-Treiber, blockierende Sockets
(NTP-Timeout 100 ms), Rendering des naechsten Textes. In jeder Pause stand der Scan, das Panel war
dunkel oder eine Zeile blieb zu lange an. Genau das war das Flackern.

Der Waveshare-Referenztreiber (JuPfu hub75) loest das, indem er den gesamten Refresh an zwei
Hardware-Bloecke des RP2350 delegiert, die unabhaengig von der CPU arbeiten:

- **PIO** (Programmable I/O) erzeugt die Pin-Signale mit exaktem Timing.
- **DMA** (Direct Memory Access) kopiert die Daten aus dem RAM in die PIO, ohne CPU.

Diese Engine macht dasselbe, nur ohne Farbtiefe (an/aus statt Bitplanes). Nach `init()` laeuft
der Refresh, bis `deinit()` gerufen wird oder der Chip resettet, egal was Python gerade tut. Python
kann sogar mit `mpremote exec` gestoppt werden, das Bild bleibt stehen.

## 4. PIO: kleine Zustandsautomaten mit exaktem Timing

Der RP2350 hat drei PIO-Bloecke (RP2040: zwei) mit je vier State-Machines (SM). Eine SM ist ein
winziger Prozessor mit

- 32 Instruktionen Programmspeicher pro Block, geteilt zwischen den vier SMs,
- zwei Scratch-Registern X und Y (32 Bit),
- einem Output Shift Register (OSR), aus dem Bits auf Pins oder in Register geschoben werden,
- einer TX-FIFO (8 Woerter, wenn die RX-FIFO dazugeschaltet wird), die CPU oder DMA fuellen,
- einem eigenen Taktteiler (hier 250 MHz / 2 = 125 MHz, ein Takt = 8 ns).

Jede Instruktion dauert **genau einen PIO-Takt** plus optional bis zu 15 Wartetakte (`[n]`). Es
gibt keine Caches, Interrupts oder Pipelines, deshalb ist das Timing auf den Takt reproduzierbar.
Einzige Ausnahme: ist die FIFO leer, wartet die SM. Die DMA muss also schneller liefern, als die
SM verbraucht, was sie mit grossem Abstand tut.

Die wenigen Instruktionen, die dieses Programm nutzt:

| Instruktion | Wirkung |
| --- | --- |
| `out pins, 32` | schiebt 32 Bit aus dem OSR und schreibt sie auf die OUT-Pingruppe |
| `out x, 32` | schiebt 32 Bit aus dem OSR in Register X |
| `jmp x-- label` | springt, wenn X != 0, und zaehlt X danach herunter (Schleife mit X + 1 Durchlaeufen) |
| `side n` | Side-Set: setzt den Side-Set-Pin (hier CLK) gleichzeitig mit der Instruktion |
| `[n]` | n zusaetzliche Wartetakte nach der Instruktion |
| Autopull | ist das OSR leer, holt die SM selbst das naechste Wort aus der TX-FIFO |
| Wrap | nach der letzten Instruktion springt die SM ohne Zeitverlust zum Anfang |

Mit Autopull und Schwelle 32 gilt: **jedes `out ..., 32` verbraucht genau ein Wort aus der FIFO.**
Das macht das Programm zu einem reinen Abspieler des Wortstroms aus Kapitel 5.

Das Programm (in `hub75_pio.c` zur Laufzeit kodiert, weil der CLK-Takt konfigurierbar ist):

```
.side_set 1                       ; ein Side-Set-Bit: CLK
.wrap_target
    out x, 32          side 0     ; Wort 0: Pixelanzahl - 1 nach X
pixel:
    out pins, 32 [3]   side 0     ; Pixelwort auf RGB/Adresse/LAT/OE, CLK low   (4 Takte Setup)
    jmp x-- pixel [3]  side 1     ; CLK high, Panel uebernimmt die Daten         (4 Takte Hold)
; sechs Steuerphasen, jede:
    out pins, 32       side 0     ; Pin-Zustand (OE, LAT, Adresse)
    out x, 32          side 0     ; Wartezaehler nach X
phase:
    jmp x-- phase      side 0     ; warten
.wrap
```

Insgesamt 21 Instruktionen. Pro Pixel 8 Takte = 64 ns, also 15.6 MHz Pixeltakt. Das entspricht dem
Waveshare-Beispiel (`SM_CLOCKDIV_FACTOR = 2`), das ebenfalls 8 bis 9 Takte pro Pixel braucht.

Wie kommt ein Wort auf 14 Pins? Die OUT-Pingruppe der SM beginnt beim niedrigsten Panel-Pin
(`out_base`, hier GPIO 0) und reicht bis zum hoechsten (GPIO 13, also 14 Pins). `out pins, 32`
schreibt Bit 0 des Wortes auf GPIO 0, Bit 1 auf GPIO 1 und so weiter. GPIO 10 liegt zwar in der
Gruppe, wird aber nie auf die PIO-Funktion geschaltet und bleibt unberuehrt. CLK (GPIO 11) liegt
ebenfalls in der Gruppe; in den Woertern ist Bit 11 immer 0, gesteuert wird CLK nur ueber Side-Set.

## 5. Der Wortstrom

Pro Scanzeile erzeugt `hub75_stream.c` diesen Block (das Format ist als Vertrag in
`hub75_internal.h` festgehalten):

| Index | Wort | Bedeutung |
| --- | --- | --- |
| 0 | `width - 1` | Schleifenzaehler fuer die Pixel |
| 1 .. 64 | Pixelwoerter | RGB-Bits des Pixels, Adresse der **vorigen** Zeile, LAT = 0, OE je nach Helligkeit |
| 65, 66 | Phase 0 | Pin-Zustand OE = 1; Wartezaehler fuer `oe_guard_ns` |
| 67, 68 | Phase 1 | OE = 1, LAT = 1; Wartezaehler fuer `latch_ns` |
| 69, 70 | Phase 2 | OE = 1, LAT = 0; Wartezaehler fuer `latch_ns` |
| 71, 72 | Phase 3 | OE = 1, neue Adresse; Wartezaehler fuer `addr_ns` |
| 73, 74 | Phase 4 | OE = 0, neue Adresse; Wartezaehler = Leuchtanteil des Budgets |
| 75, 76 | Phase 5 | OE = 1, neue Adresse; Wartezaehler = Dunkelanteil des Budgets |

77 Woerter pro Zeile, 16 Zeilen = 1232 Woerter = 4.9 KB pro Frame.

Warum tragen die Pixelwoerter die Adresse der *vorigen* Zeile? Weil waehrend des Einschiebens noch
die vorige Zeile angezeigt wird. Wuerde die Adresse schon wechseln, saehe man Ghosting. Erst in
Phase 3, bei dunklem Panel, wechselt die Adresse. Bei voller Helligkeit bleibt die Zeile waehrend
des Einschiebens an ("Pipelining"): dunkel ist das Panel dann nur in den Phasen 0 bis 3 und der
minimalen Phase 5, zusammen etwa 0.6 us pro Zeile.

**Helligkeit.** `on_time_us` ist ein Zeitbudget, das `split_budget()` in `hub75_stream.c` zwischen
Phase 4 (leuchten) und Phase 5 (dunkel) aufteilt. Die Summe ist konstant, also aendert Dimmen weder
Zeilendauer noch Bildrate. Die maximale Leuchtzeit ist Einschieben + Budget; solange die gewuenschte
Leuchtzeit groesser als das Einschieben ist, bleibt OE in den Pixelwoertern an und Phase 4 wird
gekuerzt. Darunter tragen die Pixelwoerter OE = 1 und nur Phase 4 leuchtet. Bei Helligkeit 0 traegt
auch das Phase-4-Wort OE = 1. Die Skala (0..65535) ist ein linearer Tastgrad; die wahrgenommene
Helligkeit rechnet `display.py` mit Gamma 2.2 um. Eine Aenderung kopiert den angezeigten Frame in
den Hintergrundpuffer, schreibt dort nur die Steuerwoerter und das OE-Bit der Pixelwoerter neu und
veroeffentlicht ihn (`hub75_stream_apply_control()`), also ohne Tearing.

Die Wartezaehler sind PIO-Takte. Eine Phase dauert `Zaehler + 3` Takte (`out pins`, `out x` und
der letzte Schleifendurchlauf). `hub75_stream_compute_timing()` rechnet die Nanosekunden aus
`settings.py` in Takte um, rundet auf und zieht die 3 ab.

Die Pixelwoerter entstehen aus dem Framebuffer, den Python liefert: `width * height` Bytes, ein
Farbindex pro Pixel (Bit 0 rot, Bit 1 gruen, Bit 2 blau). Fuer Scanzeile `r` liest die Engine das
Byte aus Bildzeile `r` (obere Haelfte) und aus Bildzeile `r + scan_rows` (untere Haelfte) und
schlaegt beide in einer Tabelle nach: `colour_top[]` liefert die R1/G1/B1-Bits, `colour_bot[]` die
R2/G2/B2-Bits. Dazu kommen Adresse und Steuerbits. Das Byte-Format ist genau das von
`framebuf.GS8`, deshalb kann `display.py` den Puffer ohne Umweg uebergeben.

## 6. Die DMA-Kette

DMA-Kanaele kopieren Speicher ohne CPU. Ein Kanal hat eine Lese- und eine Schreibadresse, einen
Zaehler (TRANS_COUNT), optional einen Taktgeber (DREQ, "data request", hier die TX-FIFO der SM)
und ein Feld CHAIN_TO: welcher Kanal gestartet wird, wenn dieser fertig ist.

```
                       chain_to                             chain_to
  +--------------------+ ------> +------------------------+ ------> zurueck zum Datenkanal
  | Datenkanal         |         | Steuerkanal            |
  | liest:  Frame      |         | liest:  1 Wort         |
  |         (1200 W.)  |         |         dma_front_addr |
  | schreibt: TX-FIFO  |         | schreibt: READ_ADDR    |
  |         der SM     |         |         des Datenkanals|
  | Takt:   DREQ FIFO  |         | Takt:   sofort         |
  +--------------------+         +------------------------+
```

- Der Datenkanal kopiert 1200 Woerter aus dem Frame-Puffer in die TX-FIFO der SM. Ueber DREQ kommt
  das naechste Wort erst, wenn die FIFO Platz hat. So laeuft die DMA exakt im Tempo der PIO.
- Ist der Frame durch, startet der Datenkanal per CHAIN_TO den Steuerkanal. Der kopiert ein einziges
  Wort, `dma_front_addr`, in das READ_ADDR-Register des Datenkanals und startet ihn per CHAIN_TO
  wieder. TRANS_COUNT eines Kanals wird bei jedem Start automatisch auf den zuletzt geschriebenen
  Wert (1200) zurueckgesetzt, deshalb spielt jeder Durchlauf genau einen Frame.

Kein Interrupt, keine CPU. Die Kette laeuft, bis `deinit()` sie abbricht.

**Frame-Wechsel.** `hub75_show()` baut den neuen Frame in den gerade nicht abgespielten Puffer und
schreibt danach dessen Adresse nach `dma_front_addr` (ein 32-Bit-Schreibzugriff, atomar). Der
laufende Frame wird zu Ende gespielt, der naechste kommt aus dem neuen Puffer: kein Tearing, keine
Luecke. Danach wartet `hub75_show()` (hoechstens etwa zwei Frame-Zeiten), bis der DMA den neuen
Puffer liest, damit der alte beim naechsten Aufruf gefahrlos ueberschrieben werden kann.

**Speicher.** Die beiden Puffer sind statische C-Arrays. Der Garbage Collector von MicroPython
kennt nur seinen eigenen Heap. Speicher aus `m_new()` ohne registrierten Root-Pointer haette er
jederzeit freigeben und neu vergeben koennen, waehrend der DMA noch daraus liest. Statische Arrays
liegen ausserhalb des Heaps und werden weder freigegeben noch verschoben. Preis: rund 36 KB RAM fuer
die Maximalgroesse (`HUB75_MAX_WIDTH` 128, `HUB75_MAX_SCAN_ROWS` 32).

## 7. Timing-Rechnung

Mit den Defaults aus `settings.py` und 250 MHz CPU-Takt:

| Groesse | Rechnung | Wert |
| --- | --- | --- |
| PIO-Takt | 250 MHz / 2.0 | 125 MHz, 8 ns pro Takt |
| Pixeltakt | 125 MHz / (2 * 4 Takte) | 15.6 MHz |
| Einschieben | 1 + 64 * 8 Takte | 513 Takte = 4.1 us |
| Phase 0 (Guard) | ceil(60 ns / 8 ns) | 8 Takte |
| Phasen 1, 2 (Latch) | ceil(120 / 8) | je 15 Takte |
| Phase 3 (Adresse) | ceil(200 / 8) | 25 Takte |
| Phasen 4 + 5 (Budget) | 32 us / 8 ns | 4000 Takte, bei voller Helligkeit 3997 + 3 |
| Zeile | Summe | 4576 Takte = 36.6 us |
| Frame | 16 Zeilen | 586 us, also 1707 Hz |
| Leuchtanteil bei voller Helligkeit | (512 + 3997) / 4576 | 98.5 % |
| Leuchtanteil bei 25 % Tastgrad | 0.25 * 4509 / 4576 | 24.6 %, Phase 4 = 1127 Takte, Einschieben dunkel |

`stats()` liefert diese Werte fuer die tatsaechliche Konfiguration, `measure_frame_rate()` misst
die reale Bildrate am DMA-Lesezeiger (gemessen: 1708 Hz).

## 8. Lebenszyklus und Zusammenspiel mit MicroPython

- `init()` prueft die Konfiguration (bei Fehlern bleibt eine laufende Instanz unangetastet), stoppt
  dann die alte Instanz, leitet Pin-Masken und Takte ab, baut zwei dunkle Frames, laedt das
  PIO-Programm, konfiguriert die DMA-Kanaele, schiebt einmal eine dunkle Zeile mit OE = 1 durch das
  Panel (Prolog, damit kein Muell aus den Schieberegistern aufblitzt) und startet die DMA-Kette.
- `deinit()` bricht die DMA ab, stoppt die SM, gibt PIO und DMA frei und uebergibt die GPIOs mit
  OE = 1 (dunkel) wieder an die Software-Steuerung (SIO). Auch der Wechsel von PIO zu SIO passiert
  ohne Glitch: Pegel und Richtung werden gesetzt, bevor die Pin-Funktion umschaltet.
- **Soft-Reset** (Strg-D, `mpremote soft-reset`): MicroPython gibt nur seine eigenen PIO/DMA-
  Ressourcen frei, nicht die ueber die pico-sdk beanspruchten. Der Refresh laeuft weiter, das Bild
  bleibt stehen, bis `main.py` erneut `init()` ruft. Genauso bleibt das Panel an, wenn
  `mpremote exec` das Programm unterbricht.
- **Die Pins gehoeren der PIO.** Solange die Engine laeuft, darf Python kein `machine.Pin()` auf den
  13 Panel-GPIOs anlegen. Das wuerde die Pin-Funktion auf SIO zurueckschalten und das Bild einfrieren.
- **CPU-Takt.** `pio_hz` wird beim `init()` aus dem aktuellen Systemtakt berechnet. `machine.freq()`
  deshalb vor dem Erzeugen des Displays setzen, so wie `runtime.py` es tut.
- Die Anbindung in `mod_hub75_native_scan.c` uebersetzt nur Argumente und Ergebniscodes:
  Konfigurationsfehler werden `ValueError`, Ressourcen- und Zustandsfehler `RuntimeError`.

Python-API (siehe auch die Haupt-README):

| Funktion | Zweck |
| --- | --- |
| `init(width, scan_rows, r1, g1, b1, r2, g2, b2, row_base_pin, row_n_pins, clk_pin, lat_pin, oe_pin, *, on_time_us=32, pio_clkdiv=2.0, clk_half_cycles=4, oe_guard_ns=60, latch_ns=120, addr_ns=200)` | Refresh starten, Panel zunaechst dunkel |
| `show_frame(buf)` | neuen Frame anzeigen: `width * height` Bytes, ein Farbindex pro Pixel |
| `set_brightness(level)` | Helligkeit 0..65535 (linearer Tastgrad) bei konstanter Bildrate |
| `set_on_time_us(us)` | Zeitbudget pro Zeile aendern (Bildrate) |
| `stats()` | Dict mit PIO/DMA-Zuordnung, Pixeltakt, Zeilen- und Frame-Zeit |
| `measure_frame_rate(ms=200)` | gemessene Bildwiederholrate in Hz |
| `is_running()` | `True`, solange die DMA-Kette laeuft |
| `deinit()` | Refresh stoppen, Panel dunkel, Ressourcen freigeben |

## 9. Tuning und Fehlersuche

| Symptom | Wahrscheinliche Ursache | Stellschraube |
| --- | --- | --- |
| Bild flackert | Refresh laeuft nicht | `is_running()`, `measure_frame_rate()` muss > 0 sein |
| Schwache Geisterzeilen ober-/unterhalb | Zeilentreiber beim Einschalten noch am Umschalten | `NATIVE_ADDR_NS` erhoehen (z. B. 400) |
| Helle Nachbarpixel, Schmieren | Guards vor/nach dem Latch zu kurz | `NATIVE_OE_GUARD_NS`, `NATIVE_LATCH_NS` erhoehen |
| Verschobene oder zufaellige Pixel | Pixeltakt zu schnell fuer Kabel und Panel | `NATIVE_PIO_CLKDIV` erhoehen (3.0) oder `NATIVE_CLK_HALF_CYCLES` (6) |
| Zu dunkel oder zu hell | Helligkeit | `BRIGHTNESS` in `settings.py`, zur Laufzeit `display.set_brightness()` |
| Panel dunkel, `init()` ohne Fehler | OE-Pin, Stecker, oder `machine.Pin` auf Panel-Pins | Pinbelegung in `settings.py` pruefen, keine Pins doppelt nutzen |
| `RuntimeError: hub75: no free PIO state machine` | PIO-Speicher oder SMs belegt (z. B. `rp2.StateMachine`) | andere PIO-Nutzer pruefen; das Modul probiert alle PIO-Bloecke |

Mit einem Logic Analyzer an CLK, LAT, OE und A sieht man die Sequenz aus Kapitel 2 direkt; die
Zeiten muessen den Werten aus Kapitel 7 entsprechen.

## 10. Ideen fuer Erweiterungen

- **Sanfte Uebergaenge zwischen Anzeigen:** `display.fade_to(0.0)`, neuen Frame zeigen,
  `display.fade_to(1.0)`. Die Helligkeitsaenderung kostet pro Schritt etwa eine Frame-Zeit.
- **Graustufen und Mischfarben:** mehrere Bitplanes pro Zeile mit unterschiedlich langer
  Leuchtphase (Binary Code Modulation). Der Wortstrom wird pro Zeile mehrfach mit anderen
  Pixelwoertern und anderem Budget aufgebaut; PIO und DMA bleiben unveraendert. Heute gibt es die
  acht Grundfarben (ein Bit pro Kanal).
- **Groessere Panels oder Ketten:** `width` = Gesamtbreite der Kette, `scan_rows` und `row_n_pins`
  anpassen, Grenzen `HUB75_MAX_*` beim Build erhoehen (`-DHUB75_MAX_WIDTH=256`).
