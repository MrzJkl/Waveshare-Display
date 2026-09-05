# hub75_native_scan: driving a HUB75 panel from PIO and DMA

This directory holds the MicroPython user C module `hub75_native_scan`. It
refreshes a HUB75 LED matrix entirely in hardware, using one PIO state machine
and two DMA channels, with no CPU involvement at all. MicroPython only renders
frames and hands them over.

This document explains the mechanism from the bottom up. It assumes you know
MicroPython but not necessarily how PIO or DMA work.

## Contents

1. Files and reading order
2. How a HUB75 panel is driven
3. Why PIO and DMA instead of the CPU
4. PIO: tiny state machines with exact timing
5. The word stream: the data the PIO plays
6. The DMA chain: the endless feeder
7. Timing arithmetic
8. Lifecycle and interaction with MicroPython
9. Tuning and troubleshooting
10. Ideas for extensions

## 1. Files and reading order

| File | Purpose |
| --- | --- |
| `hub75.h` | Public C API: configuration, result codes, functions. Knows nothing about MicroPython. |
| `hub75_internal.h` | Shared state (`hub75_t`) and the contract for the word stream format. |
| `hub75_stream.c` | Builds the word stream from pixels, control words and delay counters; converts ns to PIO cycles. |
| `hub75_pio.c` | The PIO program, its state machine and taking over the pins. |
| `hub75_dma.c` | The DMA chain that feeds the word stream to the PIO forever, and the frame swap. |
| `hub75_driver.c` | Lifecycle: validate, derive, start, stop, diagnostics. Owns the single instance. |
| `mod_hub75_native_scan.c` | MicroPython binding: parse arguments, turn result codes into exceptions. |
| `micropython.cmake` | Hook into the MicroPython build (`-DUSER_C_MODULES=...`). |

Suggested order: this document, then `hub75_internal.h` (the format),
`hub75_stream.c`, `hub75_pio.c`, `hub75_dma.c`, `hub75_driver.c` and finally
the binding.

Dependencies only point one way: the binding knows `hub75.h`, the driver knows
the three building blocks, and those know only `hub75_internal.h` and the
pico-sdk.

## 2. How a HUB75 panel is driven

A 64x32 panel with 1/16 scan has no framebuffer. At any moment it can only
light **two rows**: row `n` in the upper half and row `n + 16` in the lower
half. Which pair that is comes from the address lines A to D (4 bits = 16 row
pairs). A complete picture only exists because the controller walks all 16
addresses fast enough for the eye to see a steady image.

Signals on the HUB75 connector (pin assignment in `app/settings.py`):

| Signal | GPIO | Meaning |
| --- | --- | --- |
| R1 G1 B1 | 0 1 2 | colour data for the upper half, one bit per channel (on/off) |
| R2 G2 B2 | 3 4 5 | colour data for the lower half |
| A B C D | 6 7 8 9 | row address 0..15 |
| CLK | 11 | shift clock: every rising edge moves one pixel into the shift registers |
| LAT (STB) | 12 | latch: copies the shift registers into the output latches |
| OE | 13 | output enable, **active low**: 0 = LEDs on, 1 = LEDs off |

Behind every colour line sits a 64 bit shift register. To set a row you present
the six colour bits for each of the 64 pixels and give a CLK pulse. The row is
then in the shift registers but not yet visible; the LAT pulse moves it into
the output latches. The address lines select the row pair and OE enables the
LED drivers.

The sequence this engine drives for one scan row:

```
1. shift in the 64 pixels of the NEXT row      the current row stays lit
2. OE = 1                                       panel dark (guard, 60 ns)
3. LAT = 1, then LAT = 0                        data into the latches (120 ns pulse, 120 ns settle)
4. address A..D = new row                       row drivers switch over (200 ns settle)
5. OE = 0                                       new row lit (lit phase)
6. OE = 1                                       dark phase; 5 + 6 together = ON_TIME_US (32 us)
   -> back to 1 for the next row
```

At full brightness the row also stays lit during step 1 and the dark phase is
minimal. Dimming moves time from step 5 to step 6, and below a threshold step 1
goes dark as well. The row period never changes (chapter 5, "Brightness").

As a timing diagram, not to scale:

```
        |<------ 1: shift in 64 pixels -------->| 2 | 3     | 4    |<------- 5: lit --------->| 6  |
RGB   --< p0 >< p1 >< p2 > ...... < p63 >-----------------------------------------------------------
CLK   __/--\__/--\__/--\__ ...... /--\______________________________________________________________
LAT   _________________________________________/-----\______________________________________________
A..D  ====== address n-1 =============================|====== address n ===========================
OE    ______________________________________/------------------\_________________________/--------
        lit: row n-1                           dark             lit: row n                  dark
```

(At full brightness step 6 is only three cycles long.)

Two things decide whether the image looks clean:

- **Evenness.** Every row has to be lit for exactly the same time on every
  pass. A row that stays lit longer because the controller was busy elsewhere
  flashes brighter; a pass that is skipped entirely makes the image dip. Both
  are visible as flicker.
- **Order and settling when switching.** Changing the address while OE is
  still active briefly lights the wrong row ("ghosting"). Enabling OE too early
  catches the row drivers mid-switch. Hence the short waits in steps 2 to 4.

## 3. Why PIO and DMA instead of the CPU

Driving the sequence above from a CPU loop is the obvious approach and it does
not work well under MicroPython. The interpreter regularly takes the CPU for
itself: garbage collection for several milliseconds, the WiFi driver, blocking
sockets, rendering the next frame. During every one of those pauses the scan
stalls, so the panel goes dark or one row stays lit too long. That is exactly
what flicker looks like.

The fix is to hand the whole refresh to two hardware blocks of the RP2350 that
run independently of the CPU:

- **PIO** (programmable I/O) generates the pin signals with exact timing.
- **DMA** (direct memory access) copies data from RAM into the PIO without the
  CPU.

After `init()` the refresh runs until `deinit()` or a chip reset, no matter what
Python is doing. Python can even be stopped with `mpremote exec` and the image
stays on screen.

## 4. PIO: tiny state machines with exact timing

The RP2350 has three PIO blocks (RP2040: two) with four state machines each. A
state machine is a minimal processor with

- 32 instructions of program memory per block, shared between its four state machines,
- two scratch registers X and Y (32 bit),
- an output shift register (OSR) that shifts bits onto pins or into registers,
- a TX FIFO (8 words when the RX FIFO is joined in) filled by the CPU or DMA,
- its own clock divider (here 250 MHz / 2 = 125 MHz, so one cycle is 8 ns).

Every instruction takes **exactly one PIO cycle** plus up to 15 optional delay
cycles (`[n]`). There are no caches, interrupts or pipelines, so the timing is
reproducible down to the cycle. The one exception: an empty FIFO stalls the
state machine, so the DMA has to deliver faster than the machine consumes,
which it does by a wide margin.

The few instructions this program uses:

| Instruction | Effect |
| --- | --- |
| `out pins, 32` | shift 32 bits out of the OSR onto the OUT pin group |
| `out x, 32` | shift 32 bits out of the OSR into register X |
| `jmp x-- label` | jump while X is not zero, then decrement (a loop of X + 1 passes) |
| `side n` | side-set: drive the side-set pin (CLK here) together with the instruction |
| `[n]` | n extra delay cycles after the instruction |
| autopull | when the OSR runs empty the machine refills it from the TX FIFO by itself |
| wrap | after the last instruction the machine jumps back to the top for free |

With autopull at a threshold of 32, **every `out ..., 32` consumes exactly one
word from the FIFO**, which turns the program into a pure player for the word
stream of chapter 5.

The program, assembled at runtime in `hub75_pio.c` because the CLK rate is a
configuration value:

```
.side_set 1                       ; one side-set bit: CLK
.wrap_target
    out x, 32          side 0     ; word 0: pixel count - 1 into X
pixel:
    out pins, 32 [3]   side 0     ; pixel word onto RGB/address/LAT/OE, CLK low  (4 cycles setup)
    jmp x-- pixel [3]  side 1     ; CLK high, the panel samples the data          (4 cycles hold)
; six control phases, each:
    out pins, 32       side 0     ; pin state (OE, LAT, address)
    out x, 32          side 0     ; delay counter into X
phase:
    jmp x-- phase      side 0     ; wait
.wrap
```

21 instructions in total. Eight cycles per pixel is 64 ns, so a 15.6 MHz pixel
clock, which matches the Waveshare example (`SM_CLOCKDIV_FACTOR = 2`) that also
needs eight to nine cycles per pixel.

How does one word reach 14 pins? The OUT pin group of the state machine starts
at the lowest panel pin (`out_base`, GPIO 0 here) and spans up to the highest
(GPIO 13, so 14 pins). `out pins, 32` writes bit 0 of the word to GPIO 0, bit 1
to GPIO 1 and so on. GPIO 10 sits inside that range but is never switched to
the PIO function, so it stays untouched. CLK (GPIO 11) is inside the range too;
bit 11 is always 0 in the words, CLK is driven only through side-set.

## 5. The word stream

For every scan row `hub75_stream.c` produces this block; the format is written
down as a contract in `hub75_internal.h`:

| Index | Word | Meaning |
| --- | --- | --- |
| 0 | `width - 1` | loop counter for the pixels |
| 1 .. 64 | pixel words | RGB bits of the pixel, address of the **previous** row, LAT = 0, OE depending on brightness |
| 65, 66 | phase 0 | pin state OE = 1; delay counter for `oe_guard_ns` |
| 67, 68 | phase 1 | OE = 1, LAT = 1; delay counter for `latch_ns` |
| 69, 70 | phase 2 | OE = 1, LAT = 0; delay counter for `latch_ns` |
| 71, 72 | phase 3 | OE = 1, new address; delay counter for `addr_ns` |
| 73, 74 | phase 4 | OE = 0, new address; delay counter = lit share of the budget |
| 75, 76 | phase 5 | OE = 1, new address; delay counter = dark share of the budget |

77 words per row, 16 rows = 1232 words = 4.9 KB per frame.

Why do the pixel words carry the address of the *previous* row? Because that
row is still on display while the next one is shifted in. Changing the address
early would show ghosting; the address only changes in phase 3, with the panel
blanked. At full brightness the row also stays lit during the shift
("pipelining"), so the panel is dark only during phases 0 to 3 plus the minimal
phase 5, about 0.6 us per row.

**Brightness.** `on_time_us` is a time budget that `split_budget()` in
`hub75_stream.c` divides between phase 4 (lit) and phase 5 (dark). The sum is
constant, so dimming changes neither the row period nor the frame rate. The
maximum lit time is shift time plus budget: as long as the requested lit time
exceeds the shift time, OE stays on in the pixel words and phase 4 is
shortened. Below that the pixel words carry OE = 1 and only phase 4 lights the
row; at brightness 0 the phase 4 word carries OE = 1 as well. The scale
(0..65535) is a linear duty cycle; perceived brightness is mapped through gamma
2.2 in `display.py`. A change copies the frame on screen into the back buffer,
rewrites only its control words and the OE bit of the pixel words
(`hub75_stream_apply_control()`) and publishes it, so it never tears.

The delay counters are PIO cycles. A phase lasts `counter + 3` cycles
(`out pins`, `out x` and the final loop pass). `hub75_stream_compute_timing()`
converts the nanoseconds from `settings.py` into cycles, rounding up, and
subtracts those three.

The pixel words come from the framebuffer Python provides: `width * height`
bytes, one colour index per pixel (bit 0 red, bit 1 green, bit 2 blue). For scan
row `r` the engine reads the byte from image row `r` (upper half) and from image
row `r + scan_rows` (lower half) and looks both up in a table: `colour_top[]`
yields the R1/G1/B1 bits, `colour_bot[]` the R2/G2/B2 bits. Address and control
bits are added on top. That byte layout is exactly `framebuf.GS8`, which is why
`display.py` can hand over its buffer directly.

## 6. The DMA chain

DMA channels copy memory without the CPU. A channel has a read and a write
address, a counter (TRANS_COUNT), an optional pacing signal (DREQ, "data
request", here the TX FIFO of the state machine) and a CHAIN_TO field naming
the channel to start when this one finishes.

```
                       chain_to                             chain_to
  +--------------------+ ------> +------------------------+ ------> back to the data channel
  | data channel       |         | control channel        |
  | reads:  frame      |         | reads:  1 word         |
  |         (1232 w.)  |         |         dma_front_addr |
  | writes: TX FIFO    |         | writes: READ_ADDR      |
  |         of the SM  |         |         of the data ch. |
  | paced:  FIFO DREQ  |         | paced:  immediately    |
  +--------------------+         +------------------------+
```

- The data channel copies 1232 words from the frame buffer into the TX FIFO of
  the state machine. DREQ only releases the next word once the FIFO has room,
  so the DMA runs exactly at the pace of the PIO.
- When the frame is done the data channel triggers the control channel through
  CHAIN_TO. That channel copies a single word, `dma_front_addr`, into the
  READ_ADDR register of the data channel and triggers it again. A channel's
  TRANS_COUNT reloads to the last written value (1232) on every trigger, so
  every run plays exactly one frame.

No interrupt, no CPU. The chain runs until `deinit()` aborts it.

**Frame swap.** `hub75_show()` builds the new frame in whichever buffer is not
being played and then writes its address to `dma_front_addr`, a single atomic
32 bit store. The frame in flight finishes, the next one comes from the new
buffer: no tearing, no gap. `hub75_show()` then waits, bounded by roughly two
frame periods, until the DMA actually reads the new buffer, so the old one is
safe to overwrite on the next call.

**Memory.** Both buffers are static C arrays. The MicroPython garbage collector
only knows its own heap; memory from `m_new()` without a registered root
pointer could be freed and handed out again while the DMA is still reading from
it. Static arrays live outside the heap and are never freed or moved. The price
is about 36 KB of RAM for the compile-time maximum (`HUB75_MAX_WIDTH` 128,
`HUB75_MAX_SCAN_ROWS` 32).

## 7. Timing arithmetic

With the defaults from `settings.py` and a 250 MHz system clock:

| Quantity | Calculation | Value |
| --- | --- | --- |
| PIO clock | 250 MHz / 2.0 | 125 MHz, 8 ns per cycle |
| pixel clock | 125 MHz / (2 * 4 cycles) | 15.6 MHz |
| shifting | 1 + 64 * 8 cycles | 513 cycles = 4.1 us |
| phase 0 (guard) | ceil(60 ns / 8 ns) | 8 cycles |
| phases 1, 2 (latch) | ceil(120 / 8) | 15 cycles each |
| phase 3 (address) | ceil(200 / 8) | 25 cycles |
| phases 4 + 5 (budget) | 32 us / 8 ns | 4000 cycles, at full brightness 3997 + 3 |
| row | sum | 4576 cycles = 36.6 us |
| frame | 16 rows | 586 us, so 1707 Hz |
| lit share at full brightness | (512 + 3997) / 4576 | 98.5 % |
| lit share at 25 % duty | 0.25 * 4509 / 4576 | 24.6 %, phase 4 = 1127 cycles, shifting dark |

`stats()` reports these numbers for the actual configuration and
`measure_frame_rate()` measures the real frame rate from the DMA read pointer
(measured: 1708 Hz).

## 8. Lifecycle and interaction with MicroPython

- `init()` validates the configuration (on an error a running instance is left
  untouched), then tears down the old instance, derives pin masks and cycle
  counts, builds two dark frames, loads the PIO program, configures the DMA
  channels, clocks one dark row through the panel with OE = 1 (a prologue, so
  no leftover shift register content flashes up) and starts the DMA chain.
- `deinit()` aborts the DMA, stops the state machine, releases PIO and DMA and
  hands the GPIOs back to software control (SIO) with OE = 1, so the panel is
  dark. The switch from PIO to SIO is glitch free: level and direction are set
  before the pin function changes.
- **Soft reset** (Ctrl-D, `mpremote soft-reset`): MicroPython only releases the
  PIO and DMA resources it claimed itself, not those claimed through the
  pico-sdk. The refresh keeps running and the image stays up until `main.py`
  calls `init()` again. The panel also stays lit while `mpremote exec`
  interrupts the program.
- **The pins belong to the PIO.** While the engine runs, Python must not create
  a `machine.Pin()` on any of the 13 panel GPIOs; that would switch the pin
  function back to SIO and freeze the image.
- **System clock.** `pio_hz` is derived from the current system clock inside
  `init()`, so call `machine.freq()` before creating the display, the way
  `runtime.py` does.
- The binding in `mod_hub75_native_scan.c` only translates arguments and result
  codes: configuration errors become `ValueError`, resource and state errors
  `RuntimeError`.

Python API:

| Function | Purpose |
| --- | --- |
| `init(width, scan_rows, r1, g1, b1, r2, g2, b2, row_base_pin, row_n_pins, clk_pin, lat_pin, oe_pin, *, on_time_us=32, pio_clkdiv=2.0, clk_half_cycles=4, oe_guard_ns=60, latch_ns=120, addr_ns=200, brightness=65535)` | start the refresh, panel dark at first |
| `show_frame(buf)` | show a new frame: `width * height` bytes, one colour index per pixel |
| `set_brightness(level)` | brightness 0..65535 (linear duty) at a constant frame rate |
| `set_on_time_us(us)` | change the per-row time budget (frame rate) |
| `stats()` | dict with the PIO/DMA assignment, pixel clock, row and frame time |
| `measure_frame_rate(ms=200)` | measured refresh rate in Hz |
| `is_running()` | `True` while the DMA chain is active |
| `deinit()` | stop the refresh, panel dark, release the resources |

## 9. Tuning and troubleshooting

| Symptom | Likely cause | What to change |
| --- | --- | --- |
| image flickers | the refresh is not running | check `is_running()` and that `measure_frame_rate()` is above zero |
| faint ghost rows above or below | row drivers still switching when OE turns on | raise `NATIVE_ADDR_NS` (400, say) |
| bright neighbouring pixels, smearing | guards around the latch too short | raise `NATIVE_OE_GUARD_NS` and `NATIVE_LATCH_NS` |
| shifted or random pixels | pixel clock too fast for the cable and panel | raise `NATIVE_PIO_CLKDIV` (3.0) or `NATIVE_CLK_HALF_CYCLES` (6) |
| too dark or too bright | brightness | `BRIGHTNESS` in `settings.py`, at runtime `display.set_brightness()` |
| panel dark although `init()` succeeded | OE pin, connector, or a `machine.Pin` on a panel pin | check the pin assignment in `settings.py`, do not use a pin twice |
| `RuntimeError: hub75: no free PIO state machine` | PIO memory or state machines taken (by `rp2.StateMachine`, say) | look for other PIO users; the module tries every PIO block |

A logic analyser on CLK, LAT, OE and A shows the sequence from chapter 2
directly; the timings should match chapter 7.

## 10. Ideas for extensions

- **Soft transitions between screens:** `display.fade_to(0.0)`, show the next
  frame, `display.fade_to(1.0)`. Each brightness step costs about one frame
  period.
- **Grey scale and mixed colours:** several bit planes per row with different
  lit times (binary code modulation). The word stream would be built several
  times per row with different pixel words and budgets; PIO and DMA stay as
  they are. Today the panel shows the eight primary colours, one bit per
  channel.
- **Larger panels or chains:** set `width` to the total width of the chain,
  adjust `scan_rows` and `row_n_pins`, and raise the limits at build time
  (`-DHUB75_MAX_WIDTH=256`).
