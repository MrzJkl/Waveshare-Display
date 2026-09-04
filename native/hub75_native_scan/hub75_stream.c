// hub75_stream.c - builds the word stream that the PIO program plays
//
// Pure data work, no hardware registers.  This file answers one question:
// which 32-bit words must the state machine see so that one scan row is
// shifted in, latched, addressed and lit for the right time?  The word layout
// is the contract in hub75_internal.h; the program that consumes it is in
// hub75_pio.c.

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

// Split the per-row time budget between the lit phase 4 and the dark phase 5
// according to the brightness, and decide whether the row also stays lit
// while the next row is shifted in.  The total row length never changes.
static void split_budget(hub75_t *st) {
    const uint32_t fixed = HUB75_PHASE_FIXED_CYCLES;
    const uint32_t budget = st->budget_cycles;              // >= 2 * fixed
    const uint32_t max_lit = st->shift_cycles + budget - fixed;   // all but guards and a minimal dark phase

    uint32_t target = (uint32_t)(((uint64_t)max_lit * st->cfg.brightness + HUB75_BRIGHTNESS_MAX / 2u) / HUB75_BRIGHTNESS_MAX);

    // Prefer to keep the row lit during the shift (the pipelined maximum
    // brightness mode) and trim phase 4; below that, blank the shift and let
    // phase 4 alone provide the light.
    uint32_t lit;   // length of phase 4 in cycles, fixed part included
    if (target >= st->shift_cycles + fixed) {
        st->lit_during_shift = true;
        lit = target - st->shift_cycles;
    } else {
        st->lit_during_shift = false;
        lit = target;
    }
    if (lit > budget - fixed) {
        lit = budget - fixed;           // small budgets: keep a minimal dark phase
    }
    st->lit_phase_dark = (lit == 0);    // brightness 0: phase 4 runs with OE off
    if (lit < fixed) {
        lit = fixed;                    // a phase cannot be shorter than its fixed cost
    }

    st->phase_counts[HUB75_PHASE_LIT] = lit - fixed;
    st->phase_counts[HUB75_PHASE_DARK] = budget - lit - fixed;
    st->lit_cycles = (st->lit_during_shift ? st->shift_cycles : 0) + (st->lit_phase_dark ? 0 : lit);
}

void hub75_stream_compute_timing(hub75_t *st) {
    const hub75_config_t *cfg = &st->cfg;

    st->pio_hz = (uint32_t)((float)clock_get_hz(clk_sys) / cfg->pio_clkdiv);

    st->phase_counts[HUB75_PHASE_BLANK] = phase_count(ns_to_cycles(st->pio_hz, cfg->oe_guard_ns));
    st->phase_counts[HUB75_PHASE_LATCH_HIGH] = phase_count(ns_to_cycles(st->pio_hz, cfg->latch_ns));
    st->phase_counts[HUB75_PHASE_LATCH_LOW] = phase_count(ns_to_cycles(st->pio_hz, cfg->latch_ns));
    st->phase_counts[HUB75_PHASE_ADDRESS] = phase_count(ns_to_cycles(st->pio_hz, cfg->addr_ns));

    st->shift_cycles = 2u * cfg->clk_half_cycles * cfg->width;
    st->budget_cycles = us_to_cycles(st->pio_hz, cfg->on_time_us);
    if (st->budget_cycles < 2u * HUB75_PHASE_FIXED_CYCLES) {
        st->budget_cycles = 2u * HUB75_PHASE_FIXED_CYCLES;
    }
    split_budget(st);

    // One row: the counter word, the pixel loop, then the six phases.
    uint64_t cycles = 1u + (uint64_t)st->shift_cycles;
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

// OE bit for the pixel words: on while shifting only in the pipelined mode.
static uint32_t shift_oe_bits(const hub75_t *st, bool blank) {
    return (st->lit_during_shift && !blank) ? 0 : st->oe_word;
}

// The 2 * HUB75_CTRL_PHASES control words that follow the pixel words of `row`.
static void write_control_words(const hub75_t *st, uint32_t *ctrl, uint32_t row, bool blank) {
    const uint32_t prev_row = (row == 0) ? st->cfg.scan_rows - 1 : row - 1;
    const uint32_t addr_prev = hub75_stream_row_address_word(st, prev_row);
    const uint32_t addr_new = hub75_stream_row_address_word(st, row);
    const uint32_t oe_off = st->oe_word;            // OE is active low: bit set = LEDs off
    const uint32_t lat = st->lat_word;
    const uint32_t oe_lit = (st->lit_phase_dark || blank) ? oe_off : 0;

    size_t i = 0;
    ctrl[i++] = addr_prev | oe_off;
    ctrl[i++] = st->phase_counts[HUB75_PHASE_BLANK];
    ctrl[i++] = addr_prev | oe_off | lat;
    ctrl[i++] = st->phase_counts[HUB75_PHASE_LATCH_HIGH];
    ctrl[i++] = addr_prev | oe_off;
    ctrl[i++] = st->phase_counts[HUB75_PHASE_LATCH_LOW];
    ctrl[i++] = addr_new | oe_off;
    ctrl[i++] = st->phase_counts[HUB75_PHASE_ADDRESS];
    ctrl[i++] = addr_new | oe_lit;
    ctrl[i++] = blank ? 0 : st->phase_counts[HUB75_PHASE_LIT];
    ctrl[i++] = addr_new | oe_off;
    ctrl[i++] = blank ? 0 : st->phase_counts[HUB75_PHASE_DARK];
}

// Build the block for one scan row.
//   dst    row_words entries
//   src    width words of absolute GPIO masks (RGB pins that are on), or NULL for a dark row
//   blank  keep OE off during the whole block (start-up prologue)
void hub75_stream_build_row(const hub75_t *st, uint32_t *dst, const uint32_t *src, uint32_t row, bool blank) {
    const uint32_t width = st->cfg.width;
    const uint32_t prev_row = (row == 0) ? st->cfg.scan_rows - 1 : row - 1;

    // Pixel words: RGB bits of this row, address of the previous row (still
    // displayed while we shift), LAT low, OE as the brightness mode dictates.
    const uint32_t pixel_ctrl = hub75_stream_row_address_word(st, prev_row) | shift_oe_bits(st, blank);

    size_t i = 0;
    dst[i++] = width - 1;
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
    write_control_words(st, dst + i, row, blank);
}

void hub75_stream_build_frame(const hub75_t *st, uint32_t *dst, const uint32_t *src) {
    for (uint32_t row = 0; row < st->cfg.scan_rows; row++) {
        const uint32_t *src_row = (src != NULL) ? src + (size_t)row * st->cfg.width : NULL;
        hub75_stream_build_row(st, dst + (size_t)row * st->row_words, src_row, row, false);
    }
}

// Rewrite everything in a built frame that depends on timing and brightness
// (the OE bit of the pixel words and all control words) and keep the pixels.
// Used after set_brightness / set_on_time_us on a copy of the frame on screen.
void hub75_stream_apply_control(const hub75_t *st, uint32_t *dst) {
    const uint32_t width = st->cfg.width;
    const uint32_t oe_off = st->oe_word;
    const uint32_t oe_shift = shift_oe_bits(st, false);

    for (uint32_t row = 0; row < st->cfg.scan_rows; row++) {
        uint32_t *block = dst + (size_t)row * st->row_words;
        for (uint32_t x = 1; x <= width; x++) {
            block[x] = (block[x] & ~oe_off) | oe_shift;
        }
        write_control_words(st, block + 1 + width, row, false);
    }
}
