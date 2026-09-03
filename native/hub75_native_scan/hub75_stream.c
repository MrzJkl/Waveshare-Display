// hub75_stream.c - builds the word stream that the PIO program plays
//
// Pure data work, no hardware registers.  This file answers one question:
// which 32-bit words must the state machine see so that one scan row is
// shifted in, latched, addressed and lit correctly?  The word layout is the
// contract in hub75_internal.h; the program that consumes it is in hub75_pio.c.

#include <string.h>

#include "hardware/clocks.h"

#include "hub75_internal.h"

// The two frame buffers.  Static, so the MicroPython garbage collector never
// frees or moves them while the DMA reads from them.  Sized for the compile
// time maximum; only the first frame_words entries are in use.
static uint32_t hub75_buffers[2][HUB75_MAX_FRAME_WORDS] __attribute__((aligned(4)));

uint32_t *hub75_stream_buffer(uint32_t index) {
    return hub75_buffers[index & 1u];
}

// ---------------------------------------------------------------------------
// Timing: configuration in ns/us -> PIO cycles -> loop counters
// ---------------------------------------------------------------------------

static uint32_t ns_to_cycles(uint32_t pio_hz, uint32_t ns) {
    // Round up so a guard time is never shorter than requested.
    return (uint32_t)(((uint64_t)ns * pio_hz + 999999999ull) / 1000000000ull);
}

static uint32_t us_to_cycles(uint32_t pio_hz, uint32_t us) {
    uint64_t cycles = ((uint64_t)us * pio_hz + 999999ull) / 1000000ull;
    return cycles > 0xffffffffull ? 0xffffffffu : (uint32_t)cycles;
}

// A phase lasts HUB75_PHASE_FIXED_CYCLES + counter cycles, so the counter is
// the requested length minus the fixed part (never below zero).
static uint32_t phase_count(uint32_t cycles) {
    return cycles > HUB75_PHASE_FIXED_CYCLES ? cycles - HUB75_PHASE_FIXED_CYCLES : 0;
}

void hub75_stream_compute_timing(hub75_t *st) {
    const hub75_config_t *cfg = &st->cfg;

    st->pio_hz = (uint32_t)((float)clock_get_hz(clk_sys) / cfg->pio_clkdiv);

    st->phase_counts[HUB75_PHASE_BLANK] = phase_count(ns_to_cycles(st->pio_hz, cfg->oe_guard_ns));
    st->phase_counts[HUB75_PHASE_LATCH_HIGH] = phase_count(ns_to_cycles(st->pio_hz, cfg->latch_ns));
    st->phase_counts[HUB75_PHASE_LATCH_LOW] = phase_count(ns_to_cycles(st->pio_hz, cfg->latch_ns));
    st->phase_counts[HUB75_PHASE_ADDRESS] = phase_count(ns_to_cycles(st->pio_hz, cfg->addr_ns));
    st->phase_counts[HUB75_PHASE_LIT] = phase_count(us_to_cycles(st->pio_hz, cfg->on_time_us));

    // One row: the counter word, 2 * clk_half_cycles per pixel, then the phases.
    uint64_t cycles = 1u + (uint64_t)cfg->width * 2u * cfg->clk_half_cycles;
    for (uint32_t i = 0; i < HUB75_CTRL_PHASES; i++) {
        cycles += (uint64_t)st->phase_counts[i] + HUB75_PHASE_FIXED_CYCLES;
    }
    st->row_cycles = cycles > 0xffffffffull ? 0xffffffffu : (uint32_t)cycles;
    st->frame_us = (uint32_t)((cycles * cfg->scan_rows * 1000000ull + st->pio_hz / 2u) / st->pio_hz);
}

// ---------------------------------------------------------------------------
// Content
// ---------------------------------------------------------------------------

// Word bits of the address lines for `row` (line A is bit 0 of the row number).
uint32_t hub75_stream_row_address_word(const hub75_t *st, uint32_t row) {
    uint32_t word = 0;
    for (uint32_t bit = 0; bit < st->cfg.row_n_pins; bit++) {
        if (row & (1u << bit)) {
            word |= 1u << (st->cfg.row_base_pin + bit - st->out_base);
        }
    }
    return word;
}

// Build the block for one scan row.
//   dst    row_words entries
//   src    width words of absolute GPIO masks (RGB pins that are on), or NULL for a dark row
//   blank  keep OE off during the whole block (start-up prologue)
void hub75_stream_build_row(const hub75_t *st, uint32_t *dst, const uint32_t *src, uint32_t row, bool blank) {
    const uint32_t width = st->cfg.width;
    const uint32_t prev_row = (row == 0) ? st->cfg.scan_rows - 1 : row - 1;
    const uint32_t addr_prev = hub75_stream_row_address_word(st, prev_row);
    const uint32_t addr_new = hub75_stream_row_address_word(st, row);
    const uint32_t oe_off = st->oe_word;            // OE is active low: bit set = LEDs off
    const uint32_t lat = st->lat_word;
    const uint32_t oe_lit = blank ? oe_off : 0;

    size_t i = 0;
    dst[i++] = width - 1;

    // Pixel words: RGB bits of this row, address of the previous row (still
    // lit while we shift), LAT low, OE on.
    const uint32_t pixel_ctrl = addr_prev | oe_lit;
    if (src != NULL) {
        const uint32_t shift = st->out_base;
        const uint32_t mask = st->rgb_word_mask;
        for (uint32_t x = 0; x < width; x++) {
            dst[i++] = ((src[x] >> shift) & mask) | pixel_ctrl;
        }
    } else {
        for (uint32_t x = 0; x < width; x++) {
            dst[i++] = pixel_ctrl;
        }
    }

    // Control phases as (pin state, delay counter) pairs, see hub75_internal.h.
    dst[i++] = addr_prev | oe_off;
    dst[i++] = st->phase_counts[HUB75_PHASE_BLANK];
    dst[i++] = addr_prev | oe_off | lat;
    dst[i++] = st->phase_counts[HUB75_PHASE_LATCH_HIGH];
    dst[i++] = addr_prev | oe_off;
    dst[i++] = st->phase_counts[HUB75_PHASE_LATCH_LOW];
    dst[i++] = addr_new | oe_off;
    dst[i++] = st->phase_counts[HUB75_PHASE_ADDRESS];
    dst[i++] = addr_new | oe_lit;
    dst[i++] = blank ? 0 : st->phase_counts[HUB75_PHASE_LIT];
}

void hub75_stream_build_frame(const hub75_t *st, uint32_t *dst, const uint32_t *src) {
    for (uint32_t row = 0; row < st->cfg.scan_rows; row++) {
        const uint32_t *src_row = (src != NULL) ? src + (size_t)row * st->cfg.width : NULL;
        hub75_stream_build_row(st, dst + (size_t)row * st->row_words, src_row, row, false);
    }
}

// The lit counter is the last word of every row block.  Rewriting it in place
// is safe: the DMA reads each word once per frame as an aligned 32-bit access,
// so it sees either the old or the new value, never a mix.
void hub75_stream_update_on_time(const hub75_t *st) {
    for (uint32_t b = 0; b < 2; b++) {
        uint32_t *buf = hub75_buffers[b];
        for (uint32_t row = 0; row < st->cfg.scan_rows; row++) {
            buf[(size_t)row * st->row_words + st->row_words - 1] = st->phase_counts[HUB75_PHASE_LIT];
        }
    }
}
