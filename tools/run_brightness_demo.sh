#!/usr/bin/env bash
# Spielt die Helligkeits-/Fade-Testsequenz auf dem Panel ab und startet danach
# main.py neu. Konsole und Panel parallel beobachten.
set -euo pipefail
cd "$(dirname "$0")/.."
mpremote run tools/brightness_demo.py
echo
echo "Starte main.py neu (mpremote reset) ..."
mpremote reset
