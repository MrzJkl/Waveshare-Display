// hub75.h - public C API of the autonomous HUB75 scan engine
//
// This header is all the MicroPython glue (mod_hub75_native_scan.c) needs.
// Everything behind it is plain C on top of the pico-sdk and could be reused
// in a bare pico-sdk project.
//
// Reading guide (README.md in this directory tells the whole story):
//   hub75_internal.h   shared state and the word-stream contract
//   hub75_stream.c     builds the word stream (pixels, control words, delays)
//   hub75_pio.c        the PIO program that turns the stream into pin signals
//   hub75_dma.c        the DMA loop that feeds the stream to the PIO forever
//   hub75_driver.c     lifecycle: validate, derive, start, stop, diagnostics

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Compile-time limits.  The frame buffers are static arrays sized for these
// limits, which keeps them out of the MicroPython heap (README, "Speicher").
#ifndef HUB75_MAX_WIDTH
#define HUB75_MAX_WIDTH 128
#endif
#ifndef HUB75_MAX_SCAN_ROWS
#define HUB75_MAX_SCAN_ROWS 32
#endif

#define HUB75_RGB_PINS 6
#define HUB75_MAX_ROW_PINS 5

typedef enum {
    HUB75_OK = 0,
    HUB75_ERR_NOT_INITIALIZED,
    HUB75_ERR_WIDTH,
    HUB75_ERR_SCAN_ROWS,
    HUB75_ERR_ROW_PINS,
    HUB75_ERR_ADDRESS_RANGE,
    HUB75_ERR_CLK_HALF_CYCLES,
    HUB75_ERR_CLKDIV,
    HUB75_ERR_TIMING,
    HUB75_ERR_GPIO,
    HUB75_ERR_PINS_NOT_DISTINCT,
    HUB75_ERR_BUFFER_SIZE,
    HUB75_ERR_SAMPLE_MS,
    HUB75_ERR_NO_PIO,
    HUB75_ERR_NO_DMA,
    HUB75_RESULT_COUNT,
} hub75_result_t;

// Human readable text for a result code (becomes the Python exception message).
const char *hub75_result_str(hub75_result_t result);

// True for configuration/argument problems (ValueError in Python), false for
// resource or state problems (RuntimeError).
bool hub75_result_is_value_error(hub75_result_t result);

// Everything the user decides.  Pins are GPIO numbers.
typedef struct {
    uint32_t width;                     // pixels per shift-register row, e.g. 64
    uint32_t scan_rows;                 // rows selected by A..E, e.g. 16 for 1/16 scan
    uint32_t rgb_pins[HUB75_RGB_PINS];  // GPIOs of R1 G1 B1 R2 G2 B2
    uint32_t row_base_pin;              // GPIO of address line A; B, C, ... follow
    uint32_t row_n_pins;                // address lines in use (4 for 16 rows)
    uint32_t clk_pin;
    uint32_t lat_pin;
    uint32_t oe_pin;                    // output enable, active low

    float pio_clkdiv;                   // PIO clock = system clock / pio_clkdiv
    uint32_t clk_half_cycles;           // PIO cycles per CLK half period (1..16)
    uint32_t oe_guard_ns;               // blanking before the latch pulse
    uint32_t latch_ns;                  // latch pulse width and latch settle time
    uint32_t addr_ns;                   // settle time after a row address change
    uint32_t on_time_us;                // lit time per row after switching it on
} hub75_config_t;

// Derived values for diagnostics.
typedef struct {
    uint32_t sys_hz;
    uint32_t pio_hz;
    uint32_t pixel_clock_hz;
    uint32_t row_cycles;                // PIO cycles per scan row
    uint32_t frame_us;                  // nominal frame period
    uint32_t frame_words;               // words in one frame's DMA stream
    uint32_t on_time_us;
    int pio_index;
    int sm;
    int dma_data;
    int dma_ctrl;
    uint32_t front;                     // buffer index the DMA currently plays
    bool running;
} hub75_stats_t;

// Start the engine with a blank panel.  A running instance is torn down first.
// On a configuration error the running instance is left untouched.
hub75_result_t hub75_init(const hub75_config_t *cfg);

// Stop the refresh, blank the panel, release PIO/DMA and hand the GPIOs back
// to software control.  Safe to call when not initialised.
void hub75_deinit(void);

bool hub75_is_initialized(void);

// Show a new frame.  scan_words holds width * scan_rows words, one per
// (scan row, column): the absolute GPIO mask of the RGB pins that are on.
// Returns once the DMA has switched to the new frame (about one frame time).
hub75_result_t hub75_show(const uint32_t *scan_words, size_t n_words);

// Show a blank frame.
hub75_result_t hub75_clear(void);

// Change the lit time per row on the fly (brightness and refresh rate).
hub75_result_t hub75_set_on_time_us(uint32_t on_time_us);

hub75_result_t hub75_get_stats(hub75_stats_t *out);

// Count frames for sample_ms (1..10000) and return the measured refresh rate.
hub75_result_t hub75_measure_frame_rate(uint32_t sample_ms, float *hz_out);

// True while the DMA loop is active.
bool hub75_is_running(void);
