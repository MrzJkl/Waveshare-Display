// hub75_native_scan - autonomous HUB75 scan engine for MicroPython (RP2040 / RP2350)
//
// Design (same principle as the Waveshare / JuPfu hub75 reference driver):
//
//   * One PIO state machine shifts the pixel data and drives CLK, LAT, OE and
//     the row address lines from a pre-built 32-bit word stream.
//   * Two chained DMA channels play that stream in an endless loop:
//       data channel : frame buffer -> PIO TX FIFO, chains to the control channel
//       ctrl channel : writes the current front-buffer address into the data
//                      channel's READ_ADDR register and chains back to it
//     The CPU is never involved in the refresh.  Python may block for as long
//     as it wants (WLAN, NTP, HTTP, garbage collection, rendering) - the panel
//     keeps refreshing at a rock-steady rate.
//   * Frame updates are double buffered.  swap_scan_words() renders into the
//     back buffer and then republishes the front pointer; the DMA picks the new
//     buffer up at the next frame boundary, so frames never tear.
//   * Buffers are static (never garbage collected, never moved) - safe for DMA.
//
// Word stream per scan row (each word feeds exactly one PIO "out" instruction):
//
//   [0]           pixel count - 1
//   [1 .. width]  pixel words: RGB bits | address of the row that is currently
//                 lit (the previous row) | LAT=0 | OE=0
//                 -> the previous row stays lit while the next row is shifted in
//   then HUB75_CTRL_PHASES pairs of (pin state word, delay loop count):
//     1. OE=1                      blank, guard time before the latch
//     2. OE=1, LAT=1               latch pulse
//     3. OE=1, LAT=0               latch settle
//     4. OE=1, new row address     address settle (row driver switch-over)
//     5. OE=0                      row lit for on_time_us
//
// All pin bits inside a word are relative to the lowest GPIO used (out_base).
// The state machine's OUT pin group spans every GPIO from out_base to the
// highest pin; GPIOs inside that span that are not part of the panel wiring
// are never switched to the PIO function and therefore stay untouched.

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "py/runtime.h"
#include "py/mphal.h"
#include "py/objstr.h"

#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/pio_instructions.h"
#include "hardware/timer.h"

#ifndef HUB75_MAX_WIDTH
#define HUB75_MAX_WIDTH 128
#endif
#ifndef HUB75_MAX_SCAN_ROWS
#define HUB75_MAX_SCAN_ROWS 32
#endif

#define HUB75_RGB_PINS 6
#define HUB75_MAX_ROW_PINS 5
#define HUB75_CTRL_PHASES 5
#define HUB75_ROW_WORDS(width) (1u + (width) + 2u * HUB75_CTRL_PHASES)
#define HUB75_MAX_FRAME_WORDS (HUB75_MAX_SCAN_ROWS * HUB75_ROW_WORDS(HUB75_MAX_WIDTH))

// PIO program layout: 3 instructions for the pixel loop plus 3 per control phase.
#define HUB75_PROG_LEN (3u + 3u * HUB75_CTRL_PHASES)

// Each control phase costs "out pins" + "out x" + (count + 1) loop cycles.
#define HUB75_PHASE_FIXED_CYCLES 3u

typedef struct {
    bool initialized;

    uint32_t width;
    uint32_t scan_rows;
    uint32_t row_words;
    uint32_t frame_words;

    uint32_t rgb_pins[HUB75_RGB_PINS];
    uint32_t row_base_pin;
    uint32_t row_n_pins;
    uint32_t clk_pin;
    uint32_t lat_pin;
    uint32_t oe_pin;

    uint32_t out_base;
    uint32_t out_count;
    uint32_t all_pins_mask;   // absolute GPIO mask of every pin the SM drives
    uint32_t rgb_word_mask;   // RGB bits relative to out_base
    uint32_t lat_word;
    uint32_t oe_word;

    float pio_clkdiv;
    uint32_t pio_hz;
    uint32_t clk_half_cycles;
    uint32_t oe_guard_ns;
    uint32_t latch_ns;
    uint32_t addr_ns;
    uint32_t on_time_us;
    uint32_t phase_counts[HUB75_CTRL_PHASES];
    uint32_t row_cycles;
    uint32_t frame_us;

    uint32_t front;                     // index of the buffer the DMA plays
    volatile uint32_t dma_front_addr;   // read by the control DMA channel

    PIO pio;
    int sm;
    uint prog_offs;
    bool pio_ready;

    int dma_data;
    int dma_ctrl;
    bool dma_ready;
} hub75_state_t;

static hub75_state_t g_state;

// Static frame buffers: never touched by the MicroPython GC, never moved.
static uint32_t hub75_frame_buffers[2][HUB75_MAX_FRAME_WORDS] __attribute__((aligned(4)));

static uint16_t hub75_prog_instr[HUB75_PROG_LEN];

static const pio_program_t hub75_prog = {
    .instructions = hub75_prog_instr,
    .length = HUB75_PROG_LEN,
    .origin = -1,
};

// ---------------------------------------------------------------------------
// PIO program
//
//   .side_set 1                     ; CLK
//   .wrap_target
//       out x, 32          side 0   ; pixel count - 1
//   pixel:
//       out pins, 32 [h-1] side 0   ; RGB + control bits, CLK low  (data setup)
//       jmp x-- pixel [h-1] side 1  ; CLK high -> panel samples the data
//   ; repeated HUB75_CTRL_PHASES times:
//       out pins, 32       side 0   ; new pin state (OE / LAT / row address)
//       out x, 32          side 0   ; delay loop count
//   phaseN:
//       jmp x-- phaseN     side 0
//   .wrap
// ---------------------------------------------------------------------------
static void hub75_encode_program(uint32_t clk_half_cycles) {
    const uint16_t side0 = pio_encode_sideset(1, 0);
    const uint16_t side1 = pio_encode_sideset(1, 1);
    const uint16_t clk_delay = pio_encode_delay(clk_half_cycles - 1);

    size_t i = 0;
    hub75_prog_instr[i++] = pio_encode_out(pio_x, 32) | side0;
    hub75_prog_instr[i++] = pio_encode_out(pio_pins, 32) | side0 | clk_delay;
    hub75_prog_instr[i++] = pio_encode_jmp_x_dec(1) | side1 | clk_delay;

    for (uint32_t phase = 0; phase < HUB75_CTRL_PHASES; phase++) {
        hub75_prog_instr[i++] = pio_encode_out(pio_pins, 32) | side0;
        hub75_prog_instr[i++] = pio_encode_out(pio_x, 32) | side0;
        hub75_prog_instr[i] = pio_encode_jmp_x_dec(i) | side0;   // spin on itself
        i++;
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
static inline void hub75_assert_initialized(void) {
    if (!g_state.initialized) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("hub75_native_scan not initialized"));
    }
}

static inline uint32_t hub75_row_word(uint32_t row) {
    uint32_t word = 0;
    for (uint32_t bit = 0; bit < g_state.row_n_pins; bit++) {
        if (row & (1u << bit)) {
            word |= 1u << (g_state.row_base_pin + bit - g_state.out_base);
        }
    }
    return word;
}

static inline uint32_t hub75_ns_to_cycles(uint32_t ns) {
    uint64_t cycles = ((uint64_t)ns * g_state.pio_hz + 999999999ull) / 1000000000ull;
    return (uint32_t)cycles;
}

static inline uint32_t hub75_us_to_cycles(uint32_t us) {
    uint64_t cycles = ((uint64_t)us * g_state.pio_hz + 999999ull) / 1000000ull;
    return cycles > 0xffffffffull ? 0xffffffffu : (uint32_t)cycles;
}

static inline uint32_t hub75_phase_count(uint32_t cycles) {
    return cycles > HUB75_PHASE_FIXED_CYCLES ? cycles - HUB75_PHASE_FIXED_CYCLES : 0;
}

static void hub75_compute_timing(void) {
    hub75_state_t *st = &g_state;

    st->pio_hz = (uint32_t)((float)clock_get_hz(clk_sys) / st->pio_clkdiv);

    st->phase_counts[0] = hub75_phase_count(hub75_ns_to_cycles(st->oe_guard_ns));
    st->phase_counts[1] = hub75_phase_count(hub75_ns_to_cycles(st->latch_ns));
    st->phase_counts[2] = hub75_phase_count(hub75_ns_to_cycles(st->latch_ns));
    st->phase_counts[3] = hub75_phase_count(hub75_ns_to_cycles(st->addr_ns));
    st->phase_counts[4] = hub75_phase_count(hub75_us_to_cycles(st->on_time_us));

    uint64_t cycles = 1 + (uint64_t)st->width * 2u * st->clk_half_cycles;
    for (uint32_t i = 0; i < HUB75_CTRL_PHASES; i++) {
        cycles += (uint64_t)st->phase_counts[i] + HUB75_PHASE_FIXED_CYCLES;
    }
    st->row_cycles = cycles > 0xffffffffull ? 0xffffffffu : (uint32_t)cycles;
    st->frame_us = (uint32_t)((cycles * st->scan_rows * 1000000ull) / st->pio_hz);
}

// Build the word stream for one scan row.  src is NULL or width words of
// absolute GPIO masks (as produced by the Python side).  With blank=true the
// row is shifted and latched with OE kept high (used once at start-up so the
// very first frame never shows stale shift-register content).
static void hub75_build_row_block(uint32_t *dst, const uint32_t *src, uint32_t row, bool blank) {
    const hub75_state_t *st = &g_state;
    const uint32_t prev = (row == 0) ? st->scan_rows - 1 : row - 1;
    const uint32_t addr_prev = hub75_row_word(prev);
    const uint32_t addr_new = hub75_row_word(row);
    const uint32_t oe = st->oe_word;
    const uint32_t lat = st->lat_word;
    const uint32_t lit_ctrl = blank ? oe : 0;

    size_t i = 0;
    dst[i++] = st->width - 1;

    const uint32_t pixel_ctrl = addr_prev | lit_ctrl;
    if (src != NULL) {
        const uint32_t shift = st->out_base;
        const uint32_t mask = st->rgb_word_mask;
        for (uint32_t x = 0; x < st->width; x++) {
            dst[i++] = ((src[x] >> shift) & mask) | pixel_ctrl;
        }
    } else {
        for (uint32_t x = 0; x < st->width; x++) {
            dst[i++] = pixel_ctrl;
        }
    }

    dst[i++] = addr_prev | oe;        dst[i++] = st->phase_counts[0];   // blank / guard
    dst[i++] = addr_prev | oe | lat;  dst[i++] = st->phase_counts[1];   // latch pulse
    dst[i++] = addr_prev | oe;        dst[i++] = st->phase_counts[2];   // latch settle
    dst[i++] = addr_new | oe;         dst[i++] = st->phase_counts[3];   // address settle
    dst[i++] = addr_new | lit_ctrl;   dst[i++] = blank ? 0 : st->phase_counts[4];   // lit
}

static void hub75_build_frame(uint32_t *dst, const uint32_t *src) {
    for (uint32_t row = 0; row < g_state.scan_rows; row++) {
        const uint32_t *src_row = src ? src + (size_t)row * g_state.width : NULL;
        hub75_build_row_block(dst + (size_t)row * g_state.row_words, src_row, row, false);
    }
}

static void hub75_update_lit_words(void) {
    for (uint32_t buf = 0; buf < 2; buf++) {
        for (uint32_t row = 0; row < g_state.scan_rows; row++) {
            hub75_frame_buffers[buf][(size_t)row * g_state.row_words + g_state.row_words - 1] = g_state.phase_counts[4];
        }
    }
}

static inline uint32_t hub75_dma_read_addr(void) {
    return dma_hw->ch[g_state.dma_data].read_addr;
}

// Publish buffer `index` as the new front buffer and wait (bounded) until the
// DMA has started to play it, so the caller may reuse the other buffer.
static void hub75_publish(uint32_t index) {
    const uint32_t start = (uint32_t)hub75_frame_buffers[index];
    const uint32_t end = start + g_state.frame_words * sizeof(uint32_t);

    g_state.front = index;
    g_state.dma_front_addr = start;

    if (!g_state.dma_ready) {
        return;
    }

    const uint32_t timeout_us = 2u * g_state.frame_us + 2000u;
    const uint32_t t0 = time_us_32();
    while ((uint32_t)(time_us_32() - t0) < timeout_us) {
        uint32_t ra = hub75_dma_read_addr();
        if (ra >= start && ra < end) {
            break;
        }
    }
}

// Switch a GPIO back to SIO control without glitching: value and direction
// are set while the pad still belongs to the PIO, then the function changes.
static void hub75_gpio_to_sio(uint32_t pin, bool level) {
    gpio_put((uint)pin, level);
    gpio_set_dir((uint)pin, GPIO_OUT);
    gpio_set_function((uint)pin, GPIO_FUNC_SIO);
}

static void hub75_stop_hardware(void) {
    hub75_state_t *st = &g_state;

    if (st->dma_ready) {
        // Break the chain (chain to self = no chain) and disable both channels
        // before aborting, so nothing can re-trigger during the abort.
        for (int pass = 0; pass < 2; pass++) {
            int ch = pass == 0 ? st->dma_ctrl : st->dma_data;
            uint32_t ctrl = dma_hw->ch[ch].al1_ctrl;
            ctrl &= ~(DMA_CH0_CTRL_TRIG_EN_BITS | DMA_CH0_CTRL_TRIG_CHAIN_TO_BITS);
            ctrl |= ((uint32_t)ch << DMA_CH0_CTRL_TRIG_CHAIN_TO_LSB);
            dma_hw->ch[ch].al1_ctrl = ctrl;
        }
        dma_channel_abort((uint)st->dma_ctrl);
        dma_channel_abort((uint)st->dma_data);
        dma_channel_unclaim((uint)st->dma_ctrl);
        dma_channel_unclaim((uint)st->dma_data);
        st->dma_ready = false;
    }

    if (st->pio_ready) {
        pio_sm_set_enabled(st->pio, (uint)st->sm, false);
        pio_sm_clear_fifos(st->pio, (uint)st->sm);
        pio_remove_program(st->pio, &hub75_prog, st->prog_offs);
        pio_sm_unclaim(st->pio, (uint)st->sm);
        st->pio_ready = false;

        // Hand the pins back to SIO: panel blanked (OE high), everything else low.
        for (uint32_t i = 0; i < HUB75_RGB_PINS; i++) {
            hub75_gpio_to_sio(st->rgb_pins[i], false);
        }
        for (uint32_t i = 0; i < st->row_n_pins; i++) {
            hub75_gpio_to_sio(st->row_base_pin + i, false);
        }
        hub75_gpio_to_sio(st->clk_pin, false);
        hub75_gpio_to_sio(st->lat_pin, false);
        hub75_gpio_to_sio(st->oe_pin, true);
    }
}

static void hub75_release_state(void) {
    hub75_stop_hardware();
    memset(&g_state, 0, sizeof(g_state));
}

static bool hub75_try_setup_pio(PIO pio) {
    hub75_state_t *st = &g_state;

    if (!pio_can_add_program(pio, &hub75_prog)) {
        return false;
    }
    int sm = pio_claim_unused_sm(pio, false);
    if (sm < 0) {
        return false;
    }
    uint prog_offs = pio_add_program(pio, &hub75_prog);

    pio_sm_config cfg = pio_get_default_sm_config();
    sm_config_set_wrap(&cfg, prog_offs, prog_offs + HUB75_PROG_LEN - 1);
    sm_config_set_out_pins(&cfg, st->out_base, st->out_count);
    sm_config_set_sideset_pins(&cfg, st->clk_pin);
    sm_config_set_sideset(&cfg, 1, false, false);
    sm_config_set_out_shift(&cfg, true, true, 32);     // shift right, autopull, one word per "out"
    sm_config_set_fifo_join(&cfg, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv(&cfg, st->pio_clkdiv);
    pio_sm_init(pio, (uint)sm, prog_offs, &cfg);

    // Initial pin state (takes effect once the pads are switched to PIO):
    // panel blanked, everything else low, all pins outputs.
    pio_sm_set_pins_with_mask(pio, (uint)sm, 1u << st->oe_pin, st->all_pins_mask);
    pio_sm_set_pindirs_with_mask(pio, (uint)sm, st->all_pins_mask, st->all_pins_mask);

    for (uint32_t i = 0; i < HUB75_RGB_PINS; i++) {
        pio_gpio_init(pio, st->rgb_pins[i]);
    }
    for (uint32_t i = 0; i < st->row_n_pins; i++) {
        pio_gpio_init(pio, st->row_base_pin + i);
    }
    pio_gpio_init(pio, st->clk_pin);
    pio_gpio_init(pio, st->lat_pin);
    pio_gpio_init(pio, st->oe_pin);

    st->pio = pio;
    st->sm = sm;
    st->prog_offs = prog_offs;
    st->pio_ready = true;
    return true;
}

static void hub75_setup_dma(void) {
    hub75_state_t *st = &g_state;

    int data = dma_claim_unused_channel(false);
    int ctrl = dma_claim_unused_channel(false);
    if (data < 0 || ctrl < 0) {
        if (data >= 0) {
            dma_channel_unclaim((uint)data);
        }
        if (ctrl >= 0) {
            dma_channel_unclaim((uint)ctrl);
        }
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("no free DMA channels"));
    }

    // Data channel: frame buffer -> PIO TX FIFO, paced by the PIO, then chains
    // to the control channel.  TRANS_COUNT reloads on every trigger.
    dma_channel_config dc = dma_channel_get_default_config((uint)data);
    channel_config_set_transfer_data_size(&dc, DMA_SIZE_32);
    channel_config_set_read_increment(&dc, true);
    channel_config_set_write_increment(&dc, false);
    channel_config_set_dreq(&dc, pio_get_dreq(st->pio, (uint)st->sm, true));
    channel_config_set_chain_to(&dc, (uint)ctrl);
    channel_config_set_high_priority(&dc, true);
    dma_channel_configure(
        (uint)data,
        &dc,
        &st->pio->txf[st->sm],
        hub75_frame_buffers[st->front],
        st->frame_words,
        false
    );

    // Control channel: copies the front-buffer address into the data channel's
    // READ_ADDR and chains back to the data channel -> endless loop.
    dma_channel_config cc = dma_channel_get_default_config((uint)ctrl);
    channel_config_set_transfer_data_size(&cc, DMA_SIZE_32);
    channel_config_set_read_increment(&cc, false);
    channel_config_set_write_increment(&cc, false);
    channel_config_set_dreq(&cc, DREQ_FORCE);
    channel_config_set_chain_to(&cc, (uint)data);
    channel_config_set_high_priority(&cc, true);
    dma_channel_configure(
        (uint)ctrl,
        &cc,
        &dma_hw->ch[data].read_addr,
        &st->dma_front_addr,
        1,
        false
    );

    st->dma_data = data;
    st->dma_ctrl = ctrl;
    st->dma_ready = true;
}

// ---------------------------------------------------------------------------
// init(width, scan_rows, r1, g1, b1, r2, g2, b2, row_base_pin, row_n_pins,
//      clk_pin, lat_pin, oe_pin, *, on_time_us=32, pio_clkdiv=2.0,
//      clk_half_cycles=4, oe_guard_ns=60, latch_ns=120, addr_ns=200)
// ---------------------------------------------------------------------------
enum {
    ARG_width, ARG_scan_rows,
    ARG_r1, ARG_g1, ARG_b1, ARG_r2, ARG_g2, ARG_b2,
    ARG_row_base_pin, ARG_row_n_pins,
    ARG_clk_pin, ARG_lat_pin, ARG_oe_pin,
    ARG_on_time_us, ARG_pio_clkdiv, ARG_clk_half_cycles,
    ARG_oe_guard_ns, ARG_latch_ns, ARG_addr_ns,
};

static mp_obj_t hub75_native_init(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_width, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_scan_rows, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_r1, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_g1, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_b1, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_r2, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_g2, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_b2, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_row_base_pin, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_row_n_pins, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_clk_pin, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_lat_pin, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_oe_pin, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_on_time_us, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 32} },
        { MP_QSTR_pio_clkdiv, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
        { MP_QSTR_clk_half_cycles, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 4} },
        { MP_QSTR_oe_guard_ns, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 60} },
        { MP_QSTR_latch_ns, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 120} },
        { MP_QSTR_addr_ns, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 200} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    mp_int_t width = args[ARG_width].u_int;
    mp_int_t scan_rows = args[ARG_scan_rows].u_int;
    mp_int_t row_n_pins = args[ARG_row_n_pins].u_int;
    mp_int_t on_time_us = args[ARG_on_time_us].u_int;
    mp_int_t clk_half_cycles = args[ARG_clk_half_cycles].u_int;
    mp_int_t oe_guard_ns = args[ARG_oe_guard_ns].u_int;
    mp_int_t latch_ns = args[ARG_latch_ns].u_int;
    mp_int_t addr_ns = args[ARG_addr_ns].u_int;

    float pio_clkdiv = 2.0f;
    if (args[ARG_pio_clkdiv].u_obj != mp_const_none) {
        pio_clkdiv = (float)mp_obj_get_float(args[ARG_pio_clkdiv].u_obj);
    }

    if (width < 1 || width > HUB75_MAX_WIDTH) {
        mp_raise_ValueError(MP_ERROR_TEXT("width out of range"));
    }
    if (scan_rows < 1 || scan_rows > HUB75_MAX_SCAN_ROWS) {
        mp_raise_ValueError(MP_ERROR_TEXT("scan_rows out of range"));
    }
    if (row_n_pins < 1 || row_n_pins > HUB75_MAX_ROW_PINS) {
        mp_raise_ValueError(MP_ERROR_TEXT("row_n_pins must be 1..5"));
    }
    if (scan_rows > (1 << row_n_pins)) {
        mp_raise_ValueError(MP_ERROR_TEXT("scan_rows exceeds row address range"));
    }
    if (on_time_us < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("on_time_us must be >= 0"));
    }
    if (clk_half_cycles < 1 || clk_half_cycles > 16) {
        mp_raise_ValueError(MP_ERROR_TEXT("clk_half_cycles must be 1..16"));
    }
    if (oe_guard_ns < 0 || latch_ns < 0 || addr_ns < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("timing values must be >= 0"));
    }
    if (!(pio_clkdiv >= 1.0f) || pio_clkdiv > 65535.0f) {
        mp_raise_ValueError(MP_ERROR_TEXT("pio_clkdiv must be 1.0..65535"));
    }

    // Collect and validate the pins.
    uint32_t pins[HUB75_RGB_PINS + HUB75_MAX_ROW_PINS + 3];
    size_t n_pins = 0;
    const mp_int_t rgb_args[HUB75_RGB_PINS] = {
        args[ARG_r1].u_int, args[ARG_g1].u_int, args[ARG_b1].u_int,
        args[ARG_r2].u_int, args[ARG_g2].u_int, args[ARG_b2].u_int,
    };
    for (size_t i = 0; i < HUB75_RGB_PINS; i++) {
        pins[n_pins++] = (uint32_t)rgb_args[i];
    }
    for (mp_int_t i = 0; i < row_n_pins; i++) {
        pins[n_pins++] = (uint32_t)(args[ARG_row_base_pin].u_int + i);
    }
    pins[n_pins++] = (uint32_t)args[ARG_clk_pin].u_int;
    pins[n_pins++] = (uint32_t)args[ARG_lat_pin].u_int;
    pins[n_pins++] = (uint32_t)args[ARG_oe_pin].u_int;

    uint32_t all_mask = 0;
    uint32_t min_pin = 0xffffffffu;
    uint32_t max_pin = 0;
    for (size_t i = 0; i < n_pins; i++) {
        mp_int_t raw = (i < HUB75_RGB_PINS) ? rgb_args[i] : (mp_int_t)pins[i];
        if (raw < 0 || raw >= (mp_int_t)NUM_BANK0_GPIOS || raw >= 32) {
            mp_raise_ValueError(MP_ERROR_TEXT("invalid GPIO number"));
        }
        uint32_t bit = 1u << pins[i];
        if (all_mask & bit) {
            mp_raise_ValueError(MP_ERROR_TEXT("pins must be distinct"));
        }
        all_mask |= bit;
        if (pins[i] < min_pin) {
            min_pin = pins[i];
        }
        if (pins[i] > max_pin) {
            max_pin = pins[i];
        }
    }

    // Tear down a previous instance (also blanks the panel).
    hub75_release_state();
    hub75_state_t *st = &g_state;

    st->width = (uint32_t)width;
    st->scan_rows = (uint32_t)scan_rows;
    st->row_words = HUB75_ROW_WORDS(st->width);
    st->frame_words = st->row_words * st->scan_rows;

    for (size_t i = 0; i < HUB75_RGB_PINS; i++) {
        st->rgb_pins[i] = (uint32_t)rgb_args[i];
    }
    st->row_base_pin = (uint32_t)args[ARG_row_base_pin].u_int;
    st->row_n_pins = (uint32_t)row_n_pins;
    st->clk_pin = (uint32_t)args[ARG_clk_pin].u_int;
    st->lat_pin = (uint32_t)args[ARG_lat_pin].u_int;
    st->oe_pin = (uint32_t)args[ARG_oe_pin].u_int;

    st->out_base = min_pin;
    st->out_count = max_pin - min_pin + 1;
    st->all_pins_mask = all_mask;
    st->rgb_word_mask = 0;
    for (size_t i = 0; i < HUB75_RGB_PINS; i++) {
        st->rgb_word_mask |= 1u << (st->rgb_pins[i] - st->out_base);
    }
    st->lat_word = 1u << (st->lat_pin - st->out_base);
    st->oe_word = 1u << (st->oe_pin - st->out_base);

    st->pio_clkdiv = pio_clkdiv;
    st->clk_half_cycles = (uint32_t)clk_half_cycles;
    st->oe_guard_ns = (uint32_t)oe_guard_ns;
    st->latch_ns = (uint32_t)latch_ns;
    st->addr_ns = (uint32_t)addr_ns;
    st->on_time_us = (uint32_t)on_time_us;
    hub75_compute_timing();

    // Start with a blank frame in buffer 0.
    st->front = 0;
    hub75_build_frame(hub75_frame_buffers[0], NULL);
    hub75_build_frame(hub75_frame_buffers[1], NULL);
    st->dma_front_addr = (uint32_t)hub75_frame_buffers[0];

    hub75_encode_program(st->clk_half_cycles);

    PIO candidates[] = {
        pio0,
        pio1,
        #if NUM_PIOS > 2
        pio2,
        #endif
    };
    bool pio_ok = false;
    for (size_t i = 0; i < MP_ARRAY_SIZE(candidates) && !pio_ok; i++) {
        pio_ok = hub75_try_setup_pio(candidates[i]);
    }
    if (!pio_ok) {
        hub75_release_state();
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("no free PIO state machine"));
    }

    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        hub75_setup_dma();
        nlr_pop();
    } else {
        hub75_release_state();
        nlr_jump(nlr.ret_val);
    }

    // Prologue: clock a blank row through the panel with OE held high, so the
    // first visible frame never shows whatever the shift registers held.
    // The state machine drains these words while they are pushed.
    static uint32_t prologue[HUB75_ROW_WORDS(HUB75_MAX_WIDTH)];
    hub75_build_row_block(prologue, NULL, st->scan_rows - 1, true);
    pio_sm_set_enabled(st->pio, (uint)st->sm, true);
    for (uint32_t i = 0; i < st->row_words; i++) {
        pio_sm_put_blocking(st->pio, (uint)st->sm, prologue[i]);
    }

    // From here on the DMA loop feeds the state machine forever.
    dma_channel_start((uint)st->dma_data);

    st->initialized = true;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(hub75_native_init_obj, 0, hub75_native_init);

// swap_scan_words(words): words = array('I') of width * scan_rows absolute GPIO
// masks (top RGB pins for the upper half, bottom RGB pins for the lower half).
static mp_obj_t hub75_native_swap_scan_words(mp_obj_t words_obj) {
    hub75_assert_initialized();

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(words_obj, &bufinfo, MP_BUFFER_READ);

    size_t expected = (size_t)g_state.width * g_state.scan_rows * sizeof(uint32_t);
    if (bufinfo.len != expected) {
        mp_raise_ValueError(MP_ERROR_TEXT("scan_words buffer size mismatch"));
    }

    uint32_t back = g_state.front ^ 1u;
    hub75_build_frame(hub75_frame_buffers[back], (const uint32_t *)bufinfo.buf);
    hub75_publish(back);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(hub75_native_swap_scan_words_obj, hub75_native_swap_scan_words);

// clear(): show a blank frame.
static mp_obj_t hub75_native_clear(void) {
    hub75_assert_initialized();
    uint32_t back = g_state.front ^ 1u;
    hub75_build_frame(hub75_frame_buffers[back], NULL);
    hub75_publish(back);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hub75_native_clear_obj, hub75_native_clear);

// set_on_time_us(us): change the lit time per row (brightness / refresh rate)
// on the fly, in place in both buffers.
static mp_obj_t hub75_native_set_on_time_us(mp_obj_t value_obj) {
    hub75_assert_initialized();

    mp_int_t value = mp_obj_get_int(value_obj);
    if (value < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("on_time_us must be >= 0"));
    }

    g_state.on_time_us = (uint32_t)value;
    hub75_compute_timing();
    hub75_update_lit_words();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(hub75_native_set_on_time_us_obj, hub75_native_set_on_time_us);

// is_running(): True while the DMA loop is active.
static mp_obj_t hub75_native_is_running(void) {
    if (!g_state.initialized || !g_state.dma_ready) {
        return mp_const_false;
    }
    bool busy = dma_channel_is_busy((uint)g_state.dma_data) || dma_channel_is_busy((uint)g_state.dma_ctrl);
    return mp_obj_new_bool(busy);
}
static MP_DEFINE_CONST_FUN_OBJ_0(hub75_native_is_running_obj, hub75_native_is_running);

// measure_frame_rate(sample_ms=200): count frame wraps of the DMA read pointer
// for sample_ms and return the measured refresh rate in Hz (diagnostics).
static mp_obj_t hub75_native_measure_frame_rate(size_t n_args, const mp_obj_t *args) {
    hub75_assert_initialized();

    mp_int_t sample_ms = n_args > 0 ? mp_obj_get_int(args[0]) : 200;
    if (sample_ms < 1 || sample_ms > 10000) {
        mp_raise_ValueError(MP_ERROR_TEXT("sample_ms must be 1..10000"));
    }

    const uint32_t buf0 = (uint32_t)hub75_frame_buffers[0];
    const uint32_t buf1 = (uint32_t)hub75_frame_buffers[1];
    uint32_t frames = 0;
    uint32_t last_offset = 0xffffffffu;
    const uint32_t t0 = time_us_32();
    const uint32_t duration = (uint32_t)sample_ms * 1000u;
    while ((uint32_t)(time_us_32() - t0) < duration) {
        uint32_t ra = hub75_dma_read_addr();
        uint32_t offset = ra - (ra >= buf1 ? buf1 : buf0);
        if (offset < last_offset && last_offset != 0xffffffffu) {
            frames++;
        }
        last_offset = offset;
    }
    return mp_obj_new_float((mp_float_t)frames * 1000.0f / (mp_float_t)sample_ms);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(hub75_native_measure_frame_rate_obj, 0, 1, hub75_native_measure_frame_rate);

// stats(): dict with the resolved configuration and timing.
static mp_obj_t hub75_native_stats(void) {
    hub75_assert_initialized();
    const hub75_state_t *st = &g_state;

    mp_obj_t d = mp_obj_new_dict(14);
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_pio), mp_obj_new_int(pio_get_index(st->pio)));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_sm), mp_obj_new_int(st->sm));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_dma_data), mp_obj_new_int(st->dma_data));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_dma_ctrl), mp_obj_new_int(st->dma_ctrl));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_sys_hz), mp_obj_new_int_from_uint(clock_get_hz(clk_sys)));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_pio_hz), mp_obj_new_int_from_uint(st->pio_hz));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_pixel_clock_hz), mp_obj_new_int_from_uint(st->pio_hz / (2u * st->clk_half_cycles)));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_row_us), mp_obj_new_float((mp_float_t)st->row_cycles * 1000000.0f / (mp_float_t)st->pio_hz));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_frame_us), mp_obj_new_int_from_uint(st->frame_us));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_frame_hz), mp_obj_new_float(st->frame_us ? 1000000.0f / (mp_float_t)st->frame_us : 0.0f));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_frame_words), mp_obj_new_int_from_uint(st->frame_words));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_on_time_us), mp_obj_new_int_from_uint(st->on_time_us));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_front), mp_obj_new_int_from_uint(st->front));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_running), hub75_native_is_running());
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hub75_native_stats_obj, hub75_native_stats);

// deinit(): stop the refresh, blank the panel and release PIO/DMA.
static mp_obj_t hub75_native_deinit(void) {
    hub75_release_state();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hub75_native_deinit_obj, hub75_native_deinit);

static const mp_rom_map_elem_t hub75_native_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_hub75_native_scan) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&hub75_native_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_swap_scan_words), MP_ROM_PTR(&hub75_native_swap_scan_words_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear), MP_ROM_PTR(&hub75_native_clear_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_on_time_us), MP_ROM_PTR(&hub75_native_set_on_time_us_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_running), MP_ROM_PTR(&hub75_native_is_running_obj) },
    { MP_ROM_QSTR(MP_QSTR_measure_frame_rate), MP_ROM_PTR(&hub75_native_measure_frame_rate_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats), MP_ROM_PTR(&hub75_native_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&hub75_native_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_MAX_WIDTH), MP_ROM_INT(HUB75_MAX_WIDTH) },
    { MP_ROM_QSTR(MP_QSTR_MAX_SCAN_ROWS), MP_ROM_INT(HUB75_MAX_SCAN_ROWS) },
};
static MP_DEFINE_CONST_DICT(hub75_native_module_globals, hub75_native_module_globals_table);

const mp_obj_module_t hub75_native_scan_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&hub75_native_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hub75_native_scan, hub75_native_scan_module);
