// hub75_driver.c - lifecycle, validation and diagnostics
//
// Owns the single engine instance and orchestrates the other files:
//   init    validate -> stop a running instance -> derive pin masks and timing
//           -> blank frames -> PIO -> DMA -> prologue -> run
//   deinit  DMA off -> PIO off (pins back to SIO, panel blanked) -> forget state

#include <string.h>

#include "hardware/clocks.h"
#include "hardware/timer.h"

#include "hub75_internal.h"

#define HUB75_MAX_GUARD_NS 1000000u     // 1 ms per guard phase is plenty
#define HUB75_MAX_ON_TIME_US 100000u    // 100 ms per row = 0.6 Hz refresh, absurd but harmless

static hub75_t hub75;

// ---------------------------------------------------------------------------
// Result codes
// ---------------------------------------------------------------------------

static const char *const result_text[HUB75_RESULT_COUNT] = {
    [HUB75_OK] = "ok",
    [HUB75_ERR_NOT_INITIALIZED] = "not initialized",
    [HUB75_ERR_WIDTH] = "width out of range",
    [HUB75_ERR_SCAN_ROWS] = "scan_rows out of range",
    [HUB75_ERR_ROW_PINS] = "row_n_pins must be 1..5",
    [HUB75_ERR_ADDRESS_RANGE] = "scan_rows exceeds the row address range",
    [HUB75_ERR_CLK_HALF_CYCLES] = "clk_half_cycles must be 1..16",
    [HUB75_ERR_CLKDIV] = "pio_clkdiv must be 1.0..65535",
    [HUB75_ERR_TIMING] = "timing value out of range",
    [HUB75_ERR_BRIGHTNESS] = "brightness must be 0..65535",
    [HUB75_ERR_GPIO] = "invalid GPIO number",
    [HUB75_ERR_PINS_NOT_DISTINCT] = "pins must be distinct",
    [HUB75_ERR_BUFFER_SIZE] = "scan_words buffer size mismatch",
    [HUB75_ERR_SAMPLE_MS] = "sample_ms must be 1..10000",
    [HUB75_ERR_NO_PIO] = "no free PIO state machine",
    [HUB75_ERR_NO_DMA] = "no free DMA channels",
};

const char *hub75_result_str(hub75_result_t result) {
    if ((unsigned)result >= HUB75_RESULT_COUNT || result_text[result] == NULL) {
        return "unknown error";
    }
    return result_text[result];
}

bool hub75_result_is_value_error(hub75_result_t result) {
    switch (result) {
        case HUB75_ERR_NOT_INITIALIZED:
        case HUB75_ERR_NO_PIO:
        case HUB75_ERR_NO_DMA:
            return false;
        default:
            return true;
    }
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// All panel pins in one list: RGB, address lines, CLK, LAT, OE.
static uint32_t collect_pins(const hub75_config_t *cfg, uint32_t *pins) {
    uint32_t n = 0;
    for (uint32_t i = 0; i < HUB75_RGB_PINS; i++) {
        pins[n++] = cfg->rgb_pins[i];
    }
    for (uint32_t i = 0; i < cfg->row_n_pins; i++) {
        pins[n++] = cfg->row_base_pin + i;
    }
    pins[n++] = cfg->clk_pin;
    pins[n++] = cfg->lat_pin;
    pins[n++] = cfg->oe_pin;
    return n;
}

static hub75_result_t validate(const hub75_config_t *cfg) {
    if (cfg->width < 1 || cfg->width > HUB75_MAX_WIDTH) {
        return HUB75_ERR_WIDTH;
    }
    if (cfg->scan_rows < 1 || cfg->scan_rows > HUB75_MAX_SCAN_ROWS) {
        return HUB75_ERR_SCAN_ROWS;
    }
    if (cfg->row_n_pins < 1 || cfg->row_n_pins > HUB75_MAX_ROW_PINS) {
        return HUB75_ERR_ROW_PINS;
    }
    if (cfg->scan_rows > (1u << cfg->row_n_pins)) {
        return HUB75_ERR_ADDRESS_RANGE;
    }
    if (cfg->clk_half_cycles < 1 || cfg->clk_half_cycles > 16) {
        return HUB75_ERR_CLK_HALF_CYCLES;
    }
    if (!(cfg->pio_clkdiv >= 1.0f) || cfg->pio_clkdiv > 65535.0f) {
        return HUB75_ERR_CLKDIV;
    }
    if (cfg->oe_guard_ns > HUB75_MAX_GUARD_NS || cfg->latch_ns > HUB75_MAX_GUARD_NS ||
        cfg->addr_ns > HUB75_MAX_GUARD_NS || cfg->on_time_us > HUB75_MAX_ON_TIME_US) {
        return HUB75_ERR_TIMING;
    }
    if (cfg->brightness > HUB75_BRIGHTNESS_MAX) {
        return HUB75_ERR_BRIGHTNESS;
    }

    uint32_t pins[HUB75_RGB_PINS + HUB75_MAX_ROW_PINS + 3];
    const uint32_t n = collect_pins(cfg, pins);
    uint32_t seen = 0;
    for (uint32_t i = 0; i < n; i++) {
        if (pins[i] >= NUM_BANK0_GPIOS || pins[i] >= 32) {
            return HUB75_ERR_GPIO;
        }
        if (seen & (1u << pins[i])) {
            return HUB75_ERR_PINS_NOT_DISTINCT;
        }
        seen |= 1u << pins[i];
    }
    return HUB75_OK;
}

// The OUT pin group spans from the lowest to the highest panel pin; word bits
// are relative to that base (see hub75_internal.h).
static void derive_pins(hub75_t *st) {
    uint32_t pins[HUB75_RGB_PINS + HUB75_MAX_ROW_PINS + 3];
    const uint32_t n = collect_pins(&st->cfg, pins);

    uint32_t min_pin = 31, max_pin = 0, mask = 0;
    for (uint32_t i = 0; i < n; i++) {
        mask |= 1u << pins[i];
        if (pins[i] < min_pin) {
            min_pin = pins[i];
        }
        if (pins[i] > max_pin) {
            max_pin = pins[i];
        }
    }

    st->out_base = min_pin;
    st->out_count = max_pin - min_pin + 1;
    st->all_pins_mask = mask;
    st->rgb_word_mask = 0;
    for (uint32_t i = 0; i < HUB75_RGB_PINS; i++) {
        st->rgb_word_mask |= 1u << (st->cfg.rgb_pins[i] - min_pin);
    }
    st->lat_word = 1u << (st->cfg.lat_pin - min_pin);
    st->oe_word = 1u << (st->cfg.oe_pin - min_pin);
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

hub75_result_t hub75_init(const hub75_config_t *cfg) {
    const hub75_result_t check = validate(cfg);
    if (check != HUB75_OK) {
        return check;   // a running instance keeps running
    }

    hub75_deinit();
    hub75_t *st = &hub75;

    st->cfg = *cfg;
    st->row_words = HUB75_ROW_WORDS(cfg->width);
    st->frame_words = st->row_words * cfg->scan_rows;
    derive_pins(st);
    hub75_stream_compute_timing(st);

    // Both buffers start as dark frames; buffer 0 is played first.
    st->buffers[0] = hub75_stream_buffer(0);
    st->buffers[1] = hub75_stream_buffer(1);
    st->front = 0;
    hub75_stream_build_frame(st, st->buffers[0], NULL);
    hub75_stream_build_frame(st, st->buffers[1], NULL);
    st->dma_front_addr = (uint32_t)st->buffers[0];

    if (!hub75_pio_start(st)) {
        hub75_deinit();
        return HUB75_ERR_NO_PIO;
    }
    if (!hub75_dma_setup(st)) {
        hub75_deinit();
        return HUB75_ERR_NO_DMA;
    }

    // Prologue: shift one dark row through the panel with OE kept off, so the
    // first visible frame never shows whatever the shift registers held.  The
    // state machine drains these words while they are pushed.
    static uint32_t prologue[HUB75_ROW_WORDS(HUB75_MAX_WIDTH)];
    hub75_stream_build_row(st, prologue, NULL, cfg->scan_rows - 1, true);
    hub75_pio_feed_blocking(st, prologue, st->row_words);

    // From here on the DMA loop feeds the state machine forever.
    hub75_dma_run(st);
    st->initialized = true;
    return HUB75_OK;
}

void hub75_deinit(void) {
    hub75_t *st = &hub75;
    hub75_dma_stop(st);
    hub75_pio_stop(st);
    memset(st, 0, sizeof(*st));
}

bool hub75_is_initialized(void) {
    return hub75.initialized;
}

// ---------------------------------------------------------------------------
// Frames
// ---------------------------------------------------------------------------

hub75_result_t hub75_show(const uint32_t *scan_words, size_t n_words) {
    hub75_t *st = &hub75;
    if (!st->initialized) {
        return HUB75_ERR_NOT_INITIALIZED;
    }
    if (n_words != (size_t)st->cfg.width * st->cfg.scan_rows) {
        return HUB75_ERR_BUFFER_SIZE;
    }
    const uint32_t back = st->front ^ 1u;
    hub75_stream_build_frame(st, st->buffers[back], scan_words);
    hub75_dma_publish(st, back);
    return HUB75_OK;
}

hub75_result_t hub75_clear(void) {
    hub75_t *st = &hub75;
    if (!st->initialized) {
        return HUB75_ERR_NOT_INITIALIZED;
    }
    const uint32_t back = st->front ^ 1u;
    hub75_stream_build_frame(st, st->buffers[back], NULL);
    hub75_dma_publish(st, back);
    return HUB75_OK;
}

// Timing or brightness changed: copy the frame on screen into the back buffer,
// rewrite its control words and publish it.  Pixels stay, no tearing, and the
// change lands at the next frame boundary.
static void republish_control(hub75_t *st) {
    const uint32_t back = st->front ^ 1u;
    memcpy(st->buffers[back], st->buffers[st->front], st->frame_words * sizeof(uint32_t));
    hub75_stream_apply_control(st, st->buffers[back]);
    hub75_dma_publish(st, back);
}

hub75_result_t hub75_set_on_time_us(uint32_t on_time_us) {
    hub75_t *st = &hub75;
    if (!st->initialized) {
        return HUB75_ERR_NOT_INITIALIZED;
    }
    if (on_time_us > HUB75_MAX_ON_TIME_US) {
        return HUB75_ERR_TIMING;
    }
    st->cfg.on_time_us = on_time_us;
    hub75_stream_compute_timing(st);
    republish_control(st);
    return HUB75_OK;
}

hub75_result_t hub75_set_brightness(uint32_t brightness) {
    hub75_t *st = &hub75;
    if (!st->initialized) {
        return HUB75_ERR_NOT_INITIALIZED;
    }
    if (brightness > HUB75_BRIGHTNESS_MAX) {
        return HUB75_ERR_BRIGHTNESS;
    }
    st->cfg.brightness = brightness;
    hub75_stream_compute_timing(st);
    republish_control(st);
    return HUB75_OK;
}

// ---------------------------------------------------------------------------
// Diagnostics
// ---------------------------------------------------------------------------

bool hub75_is_running(void) {
    const hub75_t *st = &hub75;
    return st->initialized && st->dma_ready && hub75_dma_busy(st);
}

hub75_result_t hub75_get_stats(hub75_stats_t *out) {
    const hub75_t *st = &hub75;
    if (!st->initialized) {
        return HUB75_ERR_NOT_INITIALIZED;
    }
    out->sys_hz = clock_get_hz(clk_sys);
    out->pio_hz = st->pio_hz;
    out->pixel_clock_hz = st->pio_hz / (2u * st->cfg.clk_half_cycles);
    out->row_cycles = st->row_cycles;
    out->frame_us = st->frame_us;
    out->frame_words = st->frame_words;
    out->on_time_us = st->cfg.on_time_us;
    out->brightness = st->cfg.brightness;
    out->lit_cycles = st->lit_cycles;
    out->lit_during_shift = st->lit_during_shift;
    out->pio_index = (int)pio_get_index(st->pio);
    out->sm = st->sm;
    out->dma_data = st->dma_data;
    out->dma_ctrl = st->dma_ctrl;
    out->front = st->front;
    out->running = hub75_is_running();
    return HUB75_OK;
}

// The DMA read pointer walks from the start of the front buffer to its end
// once per frame; counting the jumps back gives the real refresh rate.
hub75_result_t hub75_measure_frame_rate(uint32_t sample_ms, float *hz_out) {
    const hub75_t *st = &hub75;
    if (!st->initialized) {
        return HUB75_ERR_NOT_INITIALIZED;
    }
    if (sample_ms < 1 || sample_ms > 10000) {
        return HUB75_ERR_SAMPLE_MS;
    }

    const uint32_t buf0 = (uint32_t)st->buffers[0];
    const uint32_t buf1 = (uint32_t)st->buffers[1];
    uint32_t frames = 0;
    uint32_t last_offset = 0xffffffffu;
    const uint32_t duration_us = sample_ms * 1000u;
    const uint32_t t0 = time_us_32();
    while ((uint32_t)(time_us_32() - t0) < duration_us) {
        const uint32_t ra = hub75_dma_read_addr(st);
        const uint32_t offset = ra - (ra >= buf1 ? buf1 : buf0);   // position inside whichever buffer plays
        if (last_offset != 0xffffffffu && offset < last_offset) {
            frames++;
        }
        last_offset = offset;
    }
    *hz_out = (float)frames * 1000.0f / (float)sample_ms;
    return HUB75_OK;
}
