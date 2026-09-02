#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "py/runtime.h"
#include "py/mphal.h"

#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/pio_instructions.h"
#include "hardware/structs/sio.h"
#include "hardware/timer.h"

typedef struct {
    bool initialized;
    uint32_t width;
    uint32_t scan_rows;
    uint32_t row_n_pins;
    uint32_t on_time_us;
    uint32_t data_setup_nops;
    uint32_t clk_high_nops;
    uint32_t lat_high_nops;
    uint32_t data_shift;

    uint32_t lat_mask;
    uint32_t oe_mask;

    uint32_t row_mask_all;
    uint32_t *row_masks;

    size_t words_len;
    uint32_t *front_words;
    uint32_t *back_words;

    PIO pio;
    int sm;
    uint prog_offs;
    int dma_chan;
    dma_channel_config dma_cfg;
    bool pio_ready;
    bool dma_ready;
} hub75_scan_state_t;

static hub75_scan_state_t g_state = {0};

// Two-instruction loop:
// 1) output 6 RGB bits with CLK low
// 2) pulse CLK high
static uint16_t hub75_shift_program_instructions[2];

static const pio_program_t hub75_shift_program = {
    .instructions = hub75_shift_program_instructions,
    .length = 2,
    .origin = -1,
};

static void hub75_prepare_shift_program(void) {
    hub75_shift_program_instructions[0] = pio_encode_out(pio_pins, 6) | pio_encode_sideset(1, 0);
    hub75_shift_program_instructions[1] = pio_encode_nop() | pio_encode_sideset(1, 1);
}

static void hub75_release_state(void) {
    if (g_state.dma_ready) {
        dma_channel_abort((uint)g_state.dma_chan);
        dma_channel_unclaim((uint)g_state.dma_chan);
    }

    if (g_state.pio_ready) {
        pio_sm_set_enabled(g_state.pio, (uint)g_state.sm, false);
        pio_sm_unclaim(g_state.pio, (uint)g_state.sm);
        pio_remove_program(g_state.pio, &hub75_shift_program, g_state.prog_offs);
    }

    if (g_state.row_masks != NULL) {
        m_del(uint32_t, g_state.row_masks, g_state.scan_rows);
    }
    if (g_state.front_words != NULL) {
        m_del(uint32_t, g_state.front_words, g_state.words_len);
    }
    if (g_state.back_words != NULL) {
        m_del(uint32_t, g_state.back_words, g_state.words_len);
    }
    memset(&g_state, 0, sizeof(g_state));
}

static inline void hub75_assert_initialized(void) {
    if (!g_state.initialized) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("hub75_native_scan not initialized"));
    }
}

static inline void hub75_config_output_pin(uint32_t pin, bool level) {
    gpio_init((uint)pin);
    gpio_set_dir((uint)pin, GPIO_OUT);
    gpio_put((uint)pin, level);
}

static inline void hub75_blank_output(void) {
    sio_hw->gpio_set = g_state.oe_mask;
}

static inline void hub75_delay_nops(uint32_t nops) {
    while (nops--) {
        __asm volatile("nop");
    }
}

static bool hub75_try_setup_pio(PIO pio, uint32_t data_base_pin, uint32_t clk_pin, float clkdiv) {
    hub75_prepare_shift_program();

    if (!pio_can_add_program(pio, &hub75_shift_program)) {
        return false;
    }

    int sm = pio_claim_unused_sm(pio, false);
    if (sm < 0) {
        return false;
    }

    uint prog_offs = pio_add_program(pio, &hub75_shift_program);

    for (uint32_t i = 0; i < 6; i++) {
        pio_gpio_init(pio, data_base_pin + i);
    }
    pio_gpio_init(pio, clk_pin);

    pio_sm_config cfg = pio_get_default_sm_config();
    sm_config_set_wrap(&cfg, prog_offs, prog_offs + 1);
    sm_config_set_out_pins(&cfg, data_base_pin, 6);
    sm_config_set_sideset_pins(&cfg, clk_pin);
    sm_config_set_sideset(&cfg, 1, false, false);
    sm_config_set_out_shift(&cfg, true, true, 6);
    sm_config_set_fifo_join(&cfg, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv(&cfg, clkdiv);

    pio_sm_set_consecutive_pindirs(pio, (uint)sm, data_base_pin, 6, true);
    pio_sm_set_consecutive_pindirs(pio, (uint)sm, clk_pin, 1, true);

    pio_sm_init(pio, (uint)sm, prog_offs, &cfg);
    pio_sm_set_enabled(pio, (uint)sm, true);

    g_state.pio = pio;
    g_state.sm = sm;
    g_state.prog_offs = prog_offs;
    g_state.pio_ready = true;

    return true;
}

static void hub75_setup_dma(void) {
    int dma_chan = dma_claim_unused_channel(false);
    if (dma_chan < 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("no free DMA channel"));
    }

    dma_channel_config cfg = dma_channel_get_default_config((uint)dma_chan);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_32);
    channel_config_set_read_increment(&cfg, true);
    channel_config_set_write_increment(&cfg, false);
    channel_config_set_dreq(&cfg, pio_get_dreq(g_state.pio, (uint)g_state.sm, true));

    g_state.dma_chan = dma_chan;
    g_state.dma_cfg = cfg;
    g_state.dma_ready = true;
}

static inline void hub75_stream_row_dma(const uint32_t *row_words) {
    dma_channel_configure(
        (uint)g_state.dma_chan,
        &g_state.dma_cfg,
        &g_state.pio->txf[g_state.sm],
        row_words,
        g_state.width,
        true
    );

    dma_channel_wait_for_finish_blocking((uint)g_state.dma_chan);

    while (!pio_sm_is_tx_fifo_empty(g_state.pio, (uint)g_state.sm)) {
    }

    // Let the state machine flush the final pixel from OSR.
    hub75_delay_nops(8);
}

static inline void hub75_scan_once_impl(void) {
    const uint32_t *scan_words = g_state.front_words;
    const uint32_t width = g_state.width;
    const uint32_t scan_rows = g_state.scan_rows;
    const uint32_t lat_mask = g_state.lat_mask;
    const uint32_t oe_mask = g_state.oe_mask;
    const uint32_t row_mask_all = g_state.row_mask_all;
    const uint32_t *row_masks = g_state.row_masks;

    for (uint32_t row = 0; row < scan_rows; row++) {
        sio_hw->gpio_set = oe_mask;

        sio_hw->gpio_clr = row_mask_all;
        sio_hw->gpio_set = row_masks[row];

        hub75_delay_nops(g_state.data_setup_nops);
        size_t row_index = (size_t)row * width;
        hub75_stream_row_dma(scan_words + row_index);

        sio_hw->gpio_set = lat_mask;
        hub75_delay_nops(g_state.lat_high_nops);
        sio_hw->gpio_clr = lat_mask;

        sio_hw->gpio_clr = oe_mask;
        if (g_state.on_time_us > 0) {
            busy_wait_us_32(g_state.on_time_us);
        }
    }

    hub75_blank_output();
}

// init(
//   width, scan_rows, on_time_us,
//   r1, g1, b1, r2, g2, b2,
//   row_base_pin, row_n_pins,
//   clk_pin, lat_pin, oe_pin,
//   [data_setup_nops, clk_high_nops, lat_high_nops]
// )
static mp_obj_t hub75_native_init(size_t n_args, const mp_obj_t *args) {
    if (n_args != 14 && n_args != 17) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected 14 or 17 arguments"));
    }

    uint32_t width = mp_obj_get_int(args[0]);
    uint32_t scan_rows = mp_obj_get_int(args[1]);
    uint32_t on_time_us = mp_obj_get_int(args[2]);

    uint32_t r1_pin = mp_obj_get_int(args[3]);
    uint32_t g1_pin = mp_obj_get_int(args[4]);
    uint32_t b1_pin = mp_obj_get_int(args[5]);
    uint32_t r2_pin = mp_obj_get_int(args[6]);
    uint32_t g2_pin = mp_obj_get_int(args[7]);
    uint32_t b2_pin = mp_obj_get_int(args[8]);

    uint32_t row_base_pin = mp_obj_get_int(args[9]);
    uint32_t row_n_pins = mp_obj_get_int(args[10]);

    uint32_t clk_pin = mp_obj_get_int(args[11]);
    uint32_t lat_pin = mp_obj_get_int(args[12]);
    uint32_t oe_pin = mp_obj_get_int(args[13]);

    uint32_t data_setup_nops = 2;
    uint32_t clk_high_nops = 6;
    uint32_t lat_high_nops = 6;
    if (n_args == 17) {
        data_setup_nops = mp_obj_get_int(args[14]);
        clk_high_nops = mp_obj_get_int(args[15]);
        lat_high_nops = mp_obj_get_int(args[16]);
    }

    if (width == 0 || scan_rows == 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("width/scan_rows must be > 0"));
    }
    if (row_n_pins == 0 || row_n_pins > 5) {
        mp_raise_ValueError(MP_ERROR_TEXT("row_n_pins must be 1..5"));
    }
    if (g1_pin != r1_pin + 1 ||
        b1_pin != r1_pin + 2 ||
        r2_pin != r1_pin + 3 ||
        g2_pin != r1_pin + 4 ||
        b2_pin != r1_pin + 5) {
        mp_raise_ValueError(MP_ERROR_TEXT("RGB pins must be contiguous"));
    }

    hub75_release_state();

    g_state.width = width;
    g_state.scan_rows = scan_rows;
    g_state.row_n_pins = row_n_pins;
    g_state.on_time_us = on_time_us;
    g_state.data_setup_nops = data_setup_nops;
    g_state.clk_high_nops = clk_high_nops;
    g_state.lat_high_nops = lat_high_nops;
    g_state.data_shift = r1_pin;

    g_state.lat_mask = 1u << lat_pin;
    g_state.oe_mask = 1u << oe_pin;

    g_state.row_mask_all = 0;
    for (uint32_t bit_idx = 0; bit_idx < row_n_pins; bit_idx++) {
        g_state.row_mask_all |= 1u << (row_base_pin + bit_idx);
    }

    g_state.row_masks = m_new(uint32_t, scan_rows);
    for (uint32_t row = 0; row < scan_rows; row++) {
        uint32_t row_mask = 0;
        for (uint32_t bit_idx = 0; bit_idx < row_n_pins; bit_idx++) {
            if (row & (1u << bit_idx)) {
                row_mask |= 1u << (row_base_pin + bit_idx);
            }
        }
        g_state.row_masks[row] = row_mask;
    }

    g_state.words_len = (size_t)width * (size_t)scan_rows;
    g_state.front_words = m_new(uint32_t, g_state.words_len);
    g_state.back_words = m_new(uint32_t, g_state.words_len);
    memset(g_state.front_words, 0, g_state.words_len * sizeof(uint32_t));
    memset(g_state.back_words, 0, g_state.words_len * sizeof(uint32_t));

    // CLK pulse width in the new PIO path is controlled by state machine clock.
    float pio_clkdiv = (float)(clk_high_nops > 0 ? clk_high_nops : 1);
    if (!hub75_try_setup_pio(pio0, r1_pin, clk_pin, pio_clkdiv) &&
        !hub75_try_setup_pio(pio1, r1_pin, clk_pin, pio_clkdiv)) {
        hub75_release_state();
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("PIO setup failed"));
    }

    hub75_setup_dma();

    for (uint32_t i = 0; i < row_n_pins; i++) {
        hub75_config_output_pin(row_base_pin + i, false);
    }
    hub75_config_output_pin(lat_pin, false);
    hub75_config_output_pin(oe_pin, true);

    g_state.initialized = true;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(hub75_native_init_obj, 14, 17, hub75_native_init);

static mp_obj_t hub75_native_swap_scan_words(mp_obj_t words_obj) {
    hub75_assert_initialized();

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(words_obj, &bufinfo, MP_BUFFER_READ);

    size_t expected = g_state.words_len * sizeof(uint32_t);
    if (bufinfo.len != expected) {
        mp_raise_ValueError(MP_ERROR_TEXT("scan_words buffer size mismatch"));
    }

    const uint32_t *src = (const uint32_t *)bufinfo.buf;
    uint32_t *dst = g_state.back_words;
    uint32_t shift = g_state.data_shift;

    for (size_t i = 0; i < g_state.words_len; i++) {
        // Convert absolute GPIO bitmasks to packed 6-bit RGB words for PIO OUT.
        dst[i] = (src[i] >> shift) & 0x3fu;
    }

    uint32_t *tmp = g_state.front_words;
    g_state.front_words = g_state.back_words;
    g_state.back_words = tmp;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(hub75_native_swap_scan_words_obj, hub75_native_swap_scan_words);

static mp_obj_t hub75_native_scan_once(void) {
    hub75_assert_initialized();
    hub75_scan_once_impl();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hub75_native_scan_once_obj, hub75_native_scan_once);

static mp_obj_t hub75_native_scan_batch(mp_obj_t count_obj) {
    hub75_assert_initialized();

    mp_int_t count = mp_obj_get_int(count_obj);
    if (count < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("count must be >= 0"));
    }

    for (mp_int_t i = 0; i < count; i++) {
        hub75_scan_once_impl();
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(hub75_native_scan_batch_obj, hub75_native_scan_batch);

static mp_obj_t hub75_native_set_on_time_us(mp_obj_t value_obj) {
    hub75_assert_initialized();

    mp_int_t value = mp_obj_get_int(value_obj);
    if (value < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("on_time_us must be >= 0"));
    }

    g_state.on_time_us = (uint32_t)value;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(hub75_native_set_on_time_us_obj, hub75_native_set_on_time_us);

static mp_obj_t hub75_native_set_pulse_nops(mp_obj_t data_setup_obj, mp_obj_t clk_high_obj, mp_obj_t lat_high_obj) {
    hub75_assert_initialized();

    mp_int_t data_setup = mp_obj_get_int(data_setup_obj);
    mp_int_t clk_high = mp_obj_get_int(clk_high_obj);
    mp_int_t lat_high = mp_obj_get_int(lat_high_obj);

    if (data_setup < 0 || clk_high < 0 || lat_high < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("pulse nops must be >= 0"));
    }

    g_state.data_setup_nops = (uint32_t)data_setup;
    g_state.clk_high_nops = (uint32_t)clk_high;
    g_state.lat_high_nops = (uint32_t)lat_high;

    if (g_state.pio_ready) {
        float pio_clkdiv = (float)(g_state.clk_high_nops > 0 ? g_state.clk_high_nops : 1);
        pio_sm_set_clkdiv(g_state.pio, (uint)g_state.sm, pio_clkdiv);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(hub75_native_set_pulse_nops_obj, hub75_native_set_pulse_nops);

static mp_obj_t hub75_native_deinit(void) {
    if (g_state.initialized) {
        hub75_blank_output();
    }
    hub75_release_state();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hub75_native_deinit_obj, hub75_native_deinit);

static const mp_rom_map_elem_t hub75_native_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_hub75_native_scan) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&hub75_native_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_swap_scan_words), MP_ROM_PTR(&hub75_native_swap_scan_words_obj) },
    { MP_ROM_QSTR(MP_QSTR_scan_once), MP_ROM_PTR(&hub75_native_scan_once_obj) },
    { MP_ROM_QSTR(MP_QSTR_scan_batch), MP_ROM_PTR(&hub75_native_scan_batch_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_on_time_us), MP_ROM_PTR(&hub75_native_set_on_time_us_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_pulse_nops), MP_ROM_PTR(&hub75_native_set_pulse_nops_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&hub75_native_deinit_obj) },
};
static MP_DEFINE_CONST_DICT(hub75_native_module_globals, hub75_native_module_globals_table);

const mp_obj_module_t hub75_native_scan_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&hub75_native_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hub75_native_scan, hub75_native_scan_module);
