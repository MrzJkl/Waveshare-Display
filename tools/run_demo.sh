#!/usr/bin/env bash
# Spielt eine visuelle Testsequenz auf dem Panel ab und startet danach main.py neu.
#   ./tools/run_demo.sh brightness   Helligkeit und Fading
#   ./tools/run_demo.sh color        Farben und Pixelzuordnung
# Konsole und Panel parallel beobachten; nichts wird geflasht.
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:-}"
script="tools/${name}_demo.py"
if [[ -z "$name" || ! -f "$script" ]]; then
  available=$(ls tools/*_demo.py | sed 's|tools/||; s|_demo.py||' | tr '\n' ' ')
  echo "Verwendung: $0 <name>   (verfuegbar: ${available})" >&2
  exit 1
fi
mpremote run "$script"
echo
echo "Starte main.py neu (mpremote reset) ..."
mpremote reset
