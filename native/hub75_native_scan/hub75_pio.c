// hub75_pio.c - the PIO program and its state machine
//
// A PIO state machine is a tiny processor that plays the word stream built by
// hub75_stream.c with cycle-exact timing: every instruction takes one PIO
// cycle plus its optional delay, and with autopull at 32 bits every
// "out ..., 32" consumes exactly one word from the TX FIFO.
//
//   .side_set 1                        ; the side-set bit drives CLK
//   .wrap_target
//       out x, 32            side 0    ; word 0: pixel count - 1 -> X
//   pixel:
//       out pins, 32 [h-1]   side 0    ; pixel word -> RGB, address, LAT, OE; CLK low (setup)
//       jmp x-- pixel [h-1]  side 1    ; CLK high: the panel samples the data (hold)
//   ; HUB75_CTRL_PHASES (six) times:
//       out pins, 32         side 0    ; pin state word
//       out x, 32            side 0    ; delay counter -> X
//   phase:
//       jmp x-- phase        side 0    ; spin X + 1 cycles
//   .wrap                              ; back to the top, free of charge
//
// h = clk_half_cycles, so one pixel takes 2 * h cycles.  21 instructions in
// total.  The program is assembled at runtime with pio_encode_* because h is
// a configuration value.
//
// Pin groups of the state machine:
//   OUT       out_base .. out_base + out_count - 1: RGB, address, LAT, OE and any
//             GPIOs in between.  Gap GPIOs are never switched to the PIO
//             function, so the state machine's writes never reach them.
//   SIDE-SET  CLK

#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/pio_instructions.h"

#include "hub75_internal.h"

#define HUB75_PROG_LEN (3u + 3u * HUB75_CTRL_PHASES)

static uint16_t hub75_prog_instr[HUB75_PROG_LEN];

static const pio_program_t hub75_prog = {
    .instructions = hub75_prog_instr,
    .length = HUB75_PROG_LEN,
    .origin = -1,   // relocatable: pio_add_program picks the offset and fixes the jumps
};

static void encode_program(uint32_t clk_half_cycles) {
    const uint16_t side0 = pio_encode_sideset(1, 0);
    const uint16_t side1 = pio_encode_sideset(1, 1);
    const uint16_t clk_delay = pio_encode_delay(clk_half_cycles - 1);

    size_t i = 0;
    hub75_prog_instr[i++] = pio_encode_out(pio_x, 32) | side0;
    hub75_prog_instr[i++] = pio_encode_out(pio_pins, 32) | side0 | clk_delay;
    hub75_prog_instr[i++] = pio_encode_jmp_x_dec(1) | side1 | clk_delay;   // target: the "out pins" above

    for (uint32_t phase = 0; phase < HUB75_CTRL_PHASES; phase++) {
        hub75_prog_instr[i++] = pio_encode_out(pio_pins, 32) | side0;
        hub75_prog_instr[i++] = pio_encode_out(pio_x, 32) | side0;
        hub75_prog_instr[i] = pio_encode_jmp_x_dec(i) | side0;             // target: itself
        i++;
    }
}

// Switch a GPIO from PIO back to software (SIO) control without a glitch:
// level and direction are set while the pad still listens to the PIO, then
// the pad function changes.
static void gpio_to_sio(uint32_t pin, bool level) {
    gpio_put((uint)pin, level);
    gpio_set_dir((uint)pin, GPIO_OUT);
    gpio_set_function((uint)pin, GPIO_FUNC_SIO);
}

static bool try_pio(hub75_t *st, PIO pio) {
    if (!pio_can_add_program(pio, &hub75_prog)) {
        return false;
    }
    int sm = pio_claim_unused_sm(pio, false);
    if (sm < 0) {
        return false;
    }
    uint offs = pio_add_program(pio, &hub75_prog);

    pio_sm_config cfg = pio_get_default_sm_config();
    sm_config_set_wrap(&cfg, offs, offs + HUB75_PROG_LEN - 1);
    sm_config_set_out_pins(&cfg, st->out_base, st->out_count);
    sm_config_set_sideset_pins(&cfg, st->cfg.clk_pin);
    sm_config_set_sideset(&cfg, 1, false, false);       // 1 bit, mandatory, drives levels
    sm_config_set_out_shift(&cfg, true, true, 32);      // shift right, autopull every 32 bits
    sm_config_set_fifo_join(&cfg, PIO_FIFO_JOIN_TX);    // 8-word TX FIFO
    sm_config_set_clkdiv(&cfg, st->cfg.pio_clkdiv);
    pio_sm_init(pio, (uint)sm, offs, &cfg);

    // Pin levels and directions as seen from the state machine: panel blanked
    // (OE high), everything else low, all outputs.  They reach the pads as soon
    // as the GPIO functions are switched to PIO below - no glitch in between.
    pio_sm_set_pins_with_mask(pio, (uint)sm, 1u << st->cfg.oe_pin, st->all_pins_mask);
    pio_sm_set_pindirs_with_mask(pio, (uint)sm, st->all_pins_mask, st->all_pins_mask);
    for (uint32_t pin = 0; pin < 32; pin++) {
        if (st->all_pins_mask & (1u << pin)) {
            pio_gpio_init(pio, pin);
        }
    }

    st->pio = pio;
    st->sm = sm;
    st->prog_offs = offs;
    st->pio_ready = true;
    return true;
}

// Load the program into the first PIO block with room and a free state
// machine, take over the pins and enable the machine.  It then waits at the
// first "out" until words arrive in its FIFO.
bool hub75_pio_start(hub75_t *st) {
    encode_program(st->cfg.clk_half_cycles);

    PIO candidates[] = {
        pio0,
        pio1,
        #if NUM_PIOS > 2
        pio2,
        #endif
    };
    for (size_t i = 0; i < sizeof(candidates) / sizeof(candidates[0]); i++) {
        if (try_pio(st, candidates[i])) {
            pio_sm_set_enabled(st->pio, (uint)st->sm, true);
            return true;
        }
    }
    return false;
}

// Push words into the TX FIFO from the CPU.  Used once for the start-up
// prologue; afterwards the DMA does this job.
void hub75_pio_feed_blocking(const hub75_t *st, const uint32_t *words, uint32_t n_words) {
    for (uint32_t i = 0; i < n_words; i++) {
        pio_sm_put_blocking(st->pio, (uint)st->sm, words[i]);
    }
}

// Stop the state machine, free the PIO resources and hand the pins back to
// software control with the panel blanked.
void hub75_pio_stop(hub75_t *st) {
    if (!st->pio_ready) {
        return;
    }
    pio_sm_set_enabled(st->pio, (uint)st->sm, false);
    pio_sm_clear_fifos(st->pio, (uint)st->sm);
    pio_remove_program(st->pio, &hub75_prog, st->prog_offs);
    pio_sm_unclaim(st->pio, (uint)st->sm);
    st->pio_ready = false;

    for (uint32_t pin = 0; pin < 32; pin++) {
        if (st->all_pins_mask & (1u << pin)) {
            gpio_to_sio(pin, pin == st->cfg.oe_pin);
        }
    }
}
