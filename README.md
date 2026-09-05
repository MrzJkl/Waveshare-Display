# LED matrix display on a Raspberry Pi Pico 2 W

Drives a **Waveshare RGB full-colour LED matrix panel** (RGB-Matrix-Pxx series,
64x32 pixels, HUB75) from a **Raspberry Pi Pico 2 W** over WiFi. The board pulls
its values from **Home Assistant** over MQTT and shows them on the panel as a
rotating set of widgets: a clock, the current weather, the next bus departures,
the Rhine water level, German weather warnings and the cheapest fuel price
nearby.

The panel is refreshed by a small C module using PIO and DMA, so the image is
rock steady and never flickers. Everything above that, all widgets and all data
handling, is plain MicroPython.

This is a personal project for one specific display, so a few defaults (city,
transit stop, river gauge, German labels on the panel) are wired to Bonn,
Germany.

## Just here for the HUB75 driver?

Then take just that part. Driving the panel directly from C was the one real
hurdle in this project, and getting there meant reading a reference driver and
the RP2350 datasheet rather than any single document. So that piece is
deliberately self-contained and written up in detail:

**[native/hub75_native_scan](native/hub75_native_scan/README.md)**

It is a MicroPython user C module: point `-DUSER_C_MODULES` at it, and Python
gets `init()`, `show_frame(framebuffer)` and `set_brightness()` for a panel that
refreshes itself. Its C API in `hub75.h` has no MicroPython dependency, so the
same code works in a plain pico-sdk project. The README there explains the HUB75
protocol, the PIO program, the DMA chain, the double buffering and the timing
arithmetic from the ground up, including the mistakes that cause flicker and
ghosting, so you should not have to reverse engineer any of it.

The Python side of this repository is then one example of what you can build on
top of it.

## In short

| | |
| --- | --- |
| Panel | Waveshare RGB full-colour LED matrix, 64x32, HUB75, 1/16 scan |
| Board | Raspberry Pi Pico 2 W (RP2350, WiFi) |
| Firmware | MicroPython plus a HUB75 user C module (PIO + DMA) |
| Data | Home Assistant over MQTT (MQTT Statestream), no direct API calls |
| Time | SNTP with local daylight saving rules |
| Configuration | web page served by the board, no reflash needed |
| Refresh rate | about 1.7 kHz, no CPU involvement |

## What it shows

| Widget | Shows | Needs |
| --- | --- | --- |
| `clock` | time with seconds, weekday and date | nothing (always visible) |
| `weather` | condition icon, temperature, humidity, wind | a Home Assistant `weather` entity |
| `dwd` | German weather warning level, only while one is active | two DWD warning sensors |
| `bus` | next departures with line, minutes and delay | departure sensors with a `times` attribute |
| `pegel` | river level as an animated water surface with flood marks | a water level sensor in cm |
| `fuel` | cheapest station's price, large, with the name as a marquee | Tankerkoenig price sensors |

Widgets rotate every few seconds with a soft fade. A widget can hide itself
when it has nothing to say, which is why the warning level only shows up while
a warning is active and the departure board disappears at night.

## Beyond the panel

- **Configurable while running.** A small web server on the board serves a
  status page and a settings form: brightness, active widgets, rotation speed,
  colours and thresholds. Values are stored on the device and survive a reboot.
- **Webhooks.** `/on`, `/off` and `/toggle` switch the panel dark or bright and
  `/status` returns the state as JSON, so a Home Assistant automation can
  control the display.
- **Built for unattended operation.** A crashing widget is dropped instead of
  taking the display down, an error outside the widgets reboots the board, and
  an optional hardware watchdog covers a hang.

## How it works

Three layers, from the hardware upwards.

**Scan engine (C).** `native/hub75_native_scan` is a MicroPython user C module.
It builds a word stream that a PIO program plays with cycle-exact timing, and
two chained DMA channels loop that stream forever. Frames are double buffered,
so a new frame appears without tearing and without a dark gap. Brightness is a
duty cycle inside the same row period, which keeps the refresh rate constant.
The [module README](native/hub75_native_scan/README.md) explains the whole
mechanism from the HUB75 protocol upwards; it is the place to start if you want
to understand or reuse the driver.

**Rendering (Python).** `app/shared/display.py` owns a `framebuf.FrameBuffer`
in GS8 format: one byte per pixel holding a colour index from 0 to 7 (bit 0
red, bit 1 green, bit 2 blue). Passing a pair of colours draws a checkerboard
of both, which reads as a mixed colour on the panel, for example red and yellow
as orange. `app/shared/font.py` renders bitmap fonts through `framebuf.blit`,
so text costs almost nothing.

**Widgets and services (Python).** `app/runtime.py` runs one loop: it services
WiFi, time sync, MQTT and the web server, lets every widget update its data,
then draws the current widget and sleeps until the next interesting moment.
Widgets live in `app/widgets/<name>/` and implement three methods, described in
[app/widgets/base.py](app/widgets/base.py):

- `service(now, ctx)` fetches data without blocking and bumps `self.revision`
  when something changed
- `is_ready(ctx)` decides whether the widget is visible at all
- `draw(display, ctx)` paints a frame and returns the milliseconds until the
  next draw

Time comes from a non-blocking SNTP client with round-trip compensation and a
server list; the time zone including daylight saving is computed locally in
`app/shared/timezone.py`.

## Build and flash

You need the MicroPython source tree with its submodules (tested against the
rp2 port at 1.30-dev with pico-sdk 2.3.0), `arm-none-eabi-gcc`, `cmake` and
`mpremote`.

```bash
export MPY=~/micropython          # MicroPython checkout
export APP=~/pico/led-display     # this repository

cd "$MPY/ports/rp2"
cmake -S . -B build-display \
  -DMICROPY_BOARD=RPI_PICO2_W \
  -DMICROPY_FROZEN_MANIFEST="$APP/manifest.py" \
  -DUSER_C_MODULES="$APP/native/hub75_native_scan/micropython.cmake"
cmake --build build-display -j"$(nproc)"
```

`-DUSER_C_MODULES` is required; without the native module the application
refuses to start. The manifest freezes the whole `app` package into the
firmware, so there is nothing to copy but the credentials.

Write the credentials and copy them to the board:

```bash
cd "$APP"
WIFI_SSID='your-ssid' WIFI_PASSWORD='your-password' \
MQTT_HOST='192.168.1.2' MQTT_USER='display' MQTT_PASSWORD='secret' \
  ./tools/generate_local_config.sh --deploy
```

That writes `local_config.py` (gitignored, never frozen) and copies it to the
device filesystem, so a password change needs no rebuild.

Flash the firmware:

```bash
mpremote bootloader
cp "$MPY/ports/rp2/build-display/firmware.uf2" /run/media/$USER/RP2350/
```

The board prints its address on the serial console after booting
(`web: http://192.168.1.42/`); that page shows the status and the settings.

## Configuration

`app/settings.py` holds the defaults for everything: wiring, panel timing,
brightness, rotation, the entity ids each widget reads, and the colours.

A curated subset of those settings is editable at runtime through the web page.
The chosen values are stored as `settings_override.json` on the device and
applied on top of the defaults at boot, so they survive a reboot without a new
firmware. Only real deviations are stored, which means a later change to a
default in `settings.py` still takes effect. "Factory reset" deletes the file.
The editable list lives in `app/shared/config.py`; credentials are deliberately
not part of it and never appear on the page. There is **no authentication**:
anybody on the network can change the display and reboot it. Set
`WEB_ENABLED = False` to switch the server off.

## Adding a widget

Create `app/widgets/<name>/` with an `__init__.py` and a `widget.py`, derive
from `Widget` and list it in `app/widgets/__init__.py`. The manifest freezes the
package recursively, so there is nothing else to register. Fonts available to a
widget are `display.font` (5x7 text) and `app.shared.font.FONT_DIGITAL` (3x7
digits); colours are the indices 0 to 7 from `app/shared/display.py`.

## Home Assistant

Install the Mosquitto broker add-on, create a user for the display, connect the
MQTT integration, then publish the entity states with
[MQTT Statestream](https://www.home-assistant.io/integrations/mqtt_statestream/):

```yaml
mqtt_statestream:
  base_topic: statestream
  publish_attributes: true
  publish_timestamps: false
```

`base_topic` has to match `HASS_BASE_TOPIC` in `app/settings.py`. Statestream
publishes every entity as retained topics
(`statestream/<domain>/<object_id>/state` plus one topic per attribute), and a
widget subscribes to exactly the topics it needs, so the board only receives
those. `mosquitto_sub -t 'statestream/#' -v` shows what is available.

Switching the panel from an automation:

```yaml
rest_command:
  display_on:
    url: "http://192.168.1.42/on"
    method: post
  display_off:
    url: "http://192.168.1.42/off"
    method: post

binary_sensor:
  - platform: rest
    name: LED Display
    resource: "http://192.168.1.42/status"
    value_template: "{{ value_json.display_on }}"
    scan_interval: 60
```

"Off" means brightness zero: the scan engine keeps running, so switching back
on is instant and fades in softly. The state is persisted, so it also survives
a reboot.

## Unattended operation

- A widget that raises in `service`, `is_ready` or `draw` is logged once,
  marked as failed and dropped from the rotation. The others keep running and
  the web page lists the failure.
- An error outside the widgets blinks the error code on the on-board LED and
  reboots, instead of leaving a frozen image behind.
- `WATCHDOG_MS = 8000` arms the hardware watchdog, which reboots the board if
  the main loop hangs. Leave it at `0` while developing: once armed it also
  reboots whenever `mpremote` interrupts `main.py`, which includes the test
  sequences below.

## Panel test sequences

```bash
./tools/run_demo.sh brightness   # brightness steps, fades, soft widget change
./tools/run_demo.sh color        # colour bars, pixel mapping, text, speed
```

Both run over `mpremote` without flashing anything, print what should be
visible for every step, and restart the application afterwards.

## Notes

- Text on the panel is German, because the data sources are (DWD warnings,
  Bonn transit, Rhine gauge). Weekday abbreviations are a setting; the rest sits
  in the widget that draws it.
- The flood marks for the Bonn gauge (620 cm and 750 cm) are placeholders and
  should be checked against the official values.
- The PIO and DMA approach of the scan engine follows the
  [JuPfu/hub75](https://github.com/JuPfu/hub75) driver that Waveshare ships as
  its Pico example, which in turn goes back to the Raspberry Pi HUB75 example.
  The code here was written from scratch for MicroPython and only borrows the
  design.
