// hub75_internal.h - shared state and the word-stream contract
//
// Included by the hub75_*.c files only; the MicroPython glue never sees it.

#pragma once

#include "hardware/pio.h"

#include "hub75.h"

// ---------------------------------------------------------------------------
// Word stream contract
//   producer: hub75_stream.c      consumer: the PIO program in hub75_pio.c
//
// The state machine executes exactly one "out" instruction per 32-bit word,
// so a frame is a flat list of words, one block per scan row:
//
//   index          content                       purpose
//   0              width - 1                     loop counter for the pixel loop
//   1 .. width     pixel words                   RGB bits + control bits per pixel
//   width + 1, 2   phase 0: pin state, delay     OE off (blank), guard before the latch
//   width + 3, 4   phase 1: pin state, delay     LAT high (latch pulse)
//   width + 5, 6   phase 2: pin state, delay     LAT low, latch settle
//   width + 7, 8   phase 3: pin state, delay     new row address, row driver settle
//   width + 9, 10  phase 4: pin state, delay     OE on: lit part of the time budget
//   width + 11, 12 phase 5: pin state, delay     OE off: dark part of the time budget
//
// Pin state words: bit (gpio - out_base) is the level of that GPIO.  The OUT
// pin group of the state machine spans out_base .. out_base + out_count - 1,
// so one "out pins, 32" sets RGB, address, LAT and OE together.  CLK is driven
// by side-set and is always 0 in the words.
//
// Pixel words carry the address of the PREVIOUS row: while row n is shifted
// into the panel's shift registers, row n-1 is still displayed from the
// output latches.  Only phase 3 (panel blanked) switches the address.
//
// Brightness: on_time_us is a time budget per row that is split between the
// lit phase 4 and the dark phase 5, so the row period and the refresh rate do
// not depend on brightness.  At high brightness the row additionally stays
// lit while the next row is shifted in (pixel words carry OE on); below that
// point the pixel words carry OE off and only phase 4 lights the row.  At
// brightness 0 the phase 4 word carries OE off as well.
//
// Delay words: loop counter N; the phase lasts N + HUB75_PHASE_FIXED_CYCLES
// PIO cycles ("out pins" + "out x" + the last loop iteration).
// ---------------------------------------------------------------------------

#define HUB75_CTRL_PHASES 6
#define HUB75_ROW_WORDS(width) (1u + (width) + 2u * HUB75_CTRL_PHASES)
#define HUB75_MAX_FRAME_WORDS (HUB75_MAX_SCAN_ROWS * HUB75_ROW_WORDS(HUB75_MAX_WIDTH))
#define HUB75_PHASE_FIXED_CYCLES 3u

enum hub75_phase {
    HUB75_PHASE_BLANK = 0,
    HUB75_PHASE_LATCH_HIGH,
    HUB75_PHASE_LATCH_LOW,
    HUB75_PHASE_ADDRESS,
    HUB75_PHASE_LIT,
    HUB75_PHASE_DARK,
};

typedef struct {
    bool initialized;
    hub75_config_t cfg;

    // Stream geometry.
    uint32_t row_words;
    uint32_t frame_words;

    // Pin mapping.  Word bits are relative to out_base.
    uint32_t out_base;
    uint32_t out_count;
    uint32_t all_pins_mask;     // absolute GPIO mask of every panel pin
    uint32_t rgb_word_mask;
    uint32_t lat_word;
    uint32_t oe_word;

    // Timing derived from cfg and the system clock.
    uint32_t pio_hz;
    uint32_t phase_counts[HUB75_CTRL_PHASES];
    uint32_t shift_cycles;      // pixel loop cycles per row
    uint32_t budget_cycles;     // phase 4 + phase 5 together (from on_time_us)
    bool lit_during_shift;      // pixel words carry OE on
    bool lit_phase_dark;        // brightness 0: phase 4 word carries OE off too
    uint32_t lit_cycles;        // cycles per row with OE on (diagnostics)
    uint32_t row_cycles;
    uint32_t frame_us;

    // Double buffering.  dma_front_addr is what the control DMA channel reads.
    uint32_t *buffers[2];
    uint32_t front;
    volatile uint32_t dma_front_addr;

    // Hardware resources.
    PIO pio;
    int sm;
    uint prog_offs;
    bool pio_ready;
    int dma_data;
    int dma_ctrl;
    bool dma_ready;
} hub75_t;

// hub75_stream.c
uint32_t *hub75_stream_buffer(uint32_t index);
void hub75_stream_compute_timing(hub75_t *st);
uint32_t hub75_stream_row_address_word(const hub75_t *st, uint32_t row);
void hub75_stream_build_row(const hub75_t *st, uint32_t *dst, const uint32_t *src, uint32_t row, bool blank);
void hub75_stream_build_frame(const hub75_t *st, uint32_t *dst, const uint32_t *src);
void hub75_stream_apply_control(const hub75_t *st, uint32_t *dst);

// hub75_pio.c
bool hub75_pio_start(hub75_t *st);
void hub75_pio_feed_blocking(const hub75_t *st, const uint32_t *words, uint32_t n_words);
void hub75_pio_stop(hub75_t *st);

// hub75_dma.c
bool hub75_dma_setup(hub75_t *st);
void hub75_dma_run(const hub75_t *st);
void hub75_dma_stop(hub75_t *st);
void hub75_dma_publish(hub75_t *st, uint32_t index);
uint32_t hub75_dma_read_addr(const hub75_t *st);
bool hub75_dma_busy(const hub75_t *st);
