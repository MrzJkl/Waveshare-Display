// mod_hub75_native_scan.c - MicroPython bindings for the HUB75 scan engine
//
// The only file that knows about MicroPython.  It converts arguments into a
// hub75_config_t, calls the plain C API from hub75.h and turns result codes
// into exceptions.  The Python-level API is documented in README.md.

#include "py/runtime.h"

#include "hub75.h"

static void raise_if_error(hub75_result_t result) {
    if (result == HUB75_OK) {
        return;
    }
    const mp_obj_type_t *type = hub75_result_is_value_error(result) ? &mp_type_ValueError : &mp_type_RuntimeError;
    mp_raise_msg_varg(type, MP_ERROR_TEXT("hub75: %s"), hub75_result_str(result));
}

static uint32_t arg_u32(mp_int_t value) {
    if (value < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("hub75: arguments must be >= 0"));
    }
    return (uint32_t)value;
}

// init(width, scan_rows, r1, g1, b1, r2, g2, b2, row_base_pin, row_n_pins,
//      clk_pin, lat_pin, oe_pin, *, on_time_us=32, pio_clkdiv=2.0,
//      clk_half_cycles=4, oe_guard_ns=60, latch_ns=120, addr_ns=200,
//      brightness=65535)
enum {
    ARG_width, ARG_scan_rows,
    ARG_r1, ARG_g1, ARG_b1, ARG_r2, ARG_g2, ARG_b2,
    ARG_row_base_pin, ARG_row_n_pins,
    ARG_clk_pin, ARG_lat_pin, ARG_oe_pin,
    ARG_on_time_us, ARG_pio_clkdiv, ARG_clk_half_cycles,
    ARG_oe_guard_ns, ARG_latch_ns, ARG_addr_ns, ARG_brightness,
};

static mp_obj_t mod_init(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
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
        { MP_QSTR_brightness, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = HUB75_BRIGHTNESS_MAX} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    hub75_config_t cfg = {
        .width = arg_u32(args[ARG_width].u_int),
        .scan_rows = arg_u32(args[ARG_scan_rows].u_int),
        .rgb_pins = {
            arg_u32(args[ARG_r1].u_int), arg_u32(args[ARG_g1].u_int), arg_u32(args[ARG_b1].u_int),
            arg_u32(args[ARG_r2].u_int), arg_u32(args[ARG_g2].u_int), arg_u32(args[ARG_b2].u_int),
        },
        .row_base_pin = arg_u32(args[ARG_row_base_pin].u_int),
        .row_n_pins = arg_u32(args[ARG_row_n_pins].u_int),
        .clk_pin = arg_u32(args[ARG_clk_pin].u_int),
        .lat_pin = arg_u32(args[ARG_lat_pin].u_int),
        .oe_pin = arg_u32(args[ARG_oe_pin].u_int),
        .pio_clkdiv = 2.0f,
        .clk_half_cycles = arg_u32(args[ARG_clk_half_cycles].u_int),
        .oe_guard_ns = arg_u32(args[ARG_oe_guard_ns].u_int),
        .latch_ns = arg_u32(args[ARG_latch_ns].u_int),
        .addr_ns = arg_u32(args[ARG_addr_ns].u_int),
        .on_time_us = arg_u32(args[ARG_on_time_us].u_int),
        .brightness = arg_u32(args[ARG_brightness].u_int),
    };
    if (args[ARG_pio_clkdiv].u_obj != mp_const_none) {
        cfg.pio_clkdiv = (float)mp_obj_get_float(args[ARG_pio_clkdiv].u_obj);
    }

    raise_if_error(hub75_init(&cfg));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mod_init_obj, 0, mod_init);

// show_frame(buf): width * height bytes, one colour index per pixel
// (bit 0 red, bit 1 green, bit 2 blue), e.g. the buffer of a framebuf GS8.
static mp_obj_t mod_show_frame(mp_obj_t buf_obj) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(buf_obj, &bufinfo, MP_BUFFER_READ);
    raise_if_error(hub75_show((const uint8_t *)bufinfo.buf, bufinfo.len));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_show_frame_obj, mod_show_frame);

static mp_obj_t mod_set_on_time_us(mp_obj_t value_obj) {
    raise_if_error(hub75_set_on_time_us(arg_u32(mp_obj_get_int(value_obj))));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_set_on_time_us_obj, mod_set_on_time_us);

// set_brightness(level): 0..65535, linear duty; refresh rate stays constant.
static mp_obj_t mod_set_brightness(mp_obj_t value_obj) {
    raise_if_error(hub75_set_brightness(arg_u32(mp_obj_get_int(value_obj))));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mod_set_brightness_obj, mod_set_brightness);

static mp_obj_t mod_is_running(void) {
    return mp_obj_new_bool(hub75_is_running());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_is_running_obj, mod_is_running);

// measure_frame_rate(sample_ms=200) -> Hz
static mp_obj_t mod_measure_frame_rate(size_t n_args, const mp_obj_t *args) {
    const uint32_t sample_ms = n_args > 0 ? arg_u32(mp_obj_get_int(args[0])) : 200;
    float hz = 0.0f;
    raise_if_error(hub75_measure_frame_rate(sample_ms, &hz));
    return mp_obj_new_float((mp_float_t)hz);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mod_measure_frame_rate_obj, 0, 1, mod_measure_frame_rate);

static mp_obj_t mod_stats(void) {
    hub75_stats_t s;
    raise_if_error(hub75_get_stats(&s));

    mp_obj_t d = mp_obj_new_dict(17);
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_pio), mp_obj_new_int(s.pio_index));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_sm), mp_obj_new_int(s.sm));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_dma_data), mp_obj_new_int(s.dma_data));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_dma_ctrl), mp_obj_new_int(s.dma_ctrl));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_sys_hz), mp_obj_new_int_from_uint(s.sys_hz));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_pio_hz), mp_obj_new_int_from_uint(s.pio_hz));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_pixel_clock_hz), mp_obj_new_int_from_uint(s.pixel_clock_hz));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_row_us), mp_obj_new_float((mp_float_t)s.row_cycles * 1000000.0f / (mp_float_t)s.pio_hz));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_frame_us), mp_obj_new_int_from_uint(s.frame_us));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_frame_hz), mp_obj_new_float(s.frame_us ? 1000000.0f / (mp_float_t)s.frame_us : 0.0f));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_frame_words), mp_obj_new_int_from_uint(s.frame_words));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_on_time_us), mp_obj_new_int_from_uint(s.on_time_us));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_brightness), mp_obj_new_int_from_uint(s.brightness));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_duty_percent), mp_obj_new_float(s.row_cycles ? 100.0f * (mp_float_t)s.lit_cycles / (mp_float_t)s.row_cycles : 0.0f));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_lit_during_shift), mp_obj_new_bool(s.lit_during_shift));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_front), mp_obj_new_int_from_uint(s.front));
    mp_obj_dict_store(d, MP_ROM_QSTR(MP_QSTR_running), mp_obj_new_bool(s.running));
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_stats_obj, mod_stats);

static mp_obj_t mod_deinit(void) {
    hub75_deinit();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mod_deinit_obj, mod_deinit);

static const mp_rom_map_elem_t module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_hub75_native_scan) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&mod_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_show_frame), MP_ROM_PTR(&mod_show_frame_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_on_time_us), MP_ROM_PTR(&mod_set_on_time_us_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_brightness), MP_ROM_PTR(&mod_set_brightness_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_running), MP_ROM_PTR(&mod_is_running_obj) },
    { MP_ROM_QSTR(MP_QSTR_measure_frame_rate), MP_ROM_PTR(&mod_measure_frame_rate_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats), MP_ROM_PTR(&mod_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&mod_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_MAX_WIDTH), MP_ROM_INT(HUB75_MAX_WIDTH) },
    { MP_ROM_QSTR(MP_QSTR_MAX_SCAN_ROWS), MP_ROM_INT(HUB75_MAX_SCAN_ROWS) },
    { MP_ROM_QSTR(MP_QSTR_BRIGHTNESS_MAX), MP_ROM_INT(HUB75_BRIGHTNESS_MAX) },
};
static MP_DEFINE_CONST_DICT(module_globals, module_globals_table);

const mp_obj_module_t hub75_native_scan_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hub75_native_scan, hub75_native_scan_module);
