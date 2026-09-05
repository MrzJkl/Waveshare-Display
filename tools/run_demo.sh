#!/usr/bin/env bash
# Plays a visual test sequence on the panel, then restarts main.py.
#   ./tools/run_demo.sh brightness   brightness and fading
#   ./tools/run_demo.sh color        colours and pixel mapping
# Watch the console and the panel side by side; nothing is flashed.
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:-}"
script="tools/${name}_demo.py"
if [[ -z "$name" || ! -f "$script" ]]; then
  available=$(ls tools/*_demo.py | sed 's|tools/||; s|_demo.py||' | tr '\n' ' ')
  echo "usage: $0 <name>   (available: ${available})" >&2
  exit 1
fi
mpremote run "$script"
echo
echo "Restarting main.py (mpremote reset) ..."
mpremote reset
