// hub75_dma.c - the endless DMA loop that feeds the state machine
//
//                        chain_to                            chain_to
//   +--------------------+ ------> +------------------------+ ------> (data channel again)
//   | data channel       |         | control channel        |
//   | read : frame buffer|         | read : dma_front_addr  |
//   | write: PIO TX FIFO |         | write: data channel    |
//   | count: frame_words |         |        READ_ADDR       |
//   | pace : PIO DREQ    |         | count: 1, unpaced      |
//   +--------------------+         +------------------------+
//
// The data channel streams one frame into the TX FIFO.  It is paced by the
// FIFO's data request (DREQ), so it never runs ahead of the state machine.
// When the frame is done it triggers the control channel, which copies the
// current front-buffer address into the data channel's READ_ADDR register and
// triggers the data channel again.  A channel's TRANS_COUNT reloads to its
// last written value on every trigger, so every run plays exactly one frame.
// No interrupt, no CPU involvement.
//
// Publishing a new frame is a single 32-bit store to dma_front_addr; the DMA
// picks it up at the next frame boundary, so frames never tear.

#include "hardware/dma.h"
#include "hardware/timer.h"

#include "hub75_internal.h"

bool hub75_dma_setup(hub75_t *st) {
    int data = dma_claim_unused_channel(false);
    int ctrl = dma_claim_unused_channel(false);
    if (data < 0 || ctrl < 0) {
        if (data >= 0) {
            dma_channel_unclaim((uint)data);
        }
        if (ctrl >= 0) {
            dma_channel_unclaim((uint)ctrl);
        }
        return false;
    }

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
        &st->pio->txf[st->sm],      // write: TX FIFO of our state machine
        st->buffers[st->front],     // read: the front frame buffer
        st->frame_words,
        false                       // do not start yet
    );

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
        &dma_hw->ch[data].read_addr,    // write: READ_ADDR of the data channel (no trigger)
        &st->dma_front_addr,            // read: the published front-buffer address
        1,
        false
    );

    st->dma_data = data;
    st->dma_ctrl = ctrl;
    st->dma_ready = true;
    return true;
}

void hub75_dma_run(const hub75_t *st) {
    dma_channel_start((uint)st->dma_data);
}

void hub75_dma_stop(hub75_t *st) {
    if (!st->dma_ready) {
        return;
    }

    // Unchain (chain to self = no chain) and disable both channels before
    // aborting, so nothing can re-trigger while the abort is in progress.
    const int channels[2] = { st->dma_ctrl, st->dma_data };
    for (int i = 0; i < 2; i++) {
        const int ch = channels[i];
        uint32_t ctrl = dma_hw->ch[ch].al1_ctrl;
        ctrl &= ~(DMA_CH0_CTRL_TRIG_EN_BITS | DMA_CH0_CTRL_TRIG_CHAIN_TO_BITS);
        ctrl |= (uint32_t)ch << DMA_CH0_CTRL_TRIG_CHAIN_TO_LSB;
        dma_hw->ch[ch].al1_ctrl = ctrl;
    }
    dma_channel_abort((uint)st->dma_ctrl);
    dma_channel_abort((uint)st->dma_data);
    dma_channel_unclaim((uint)st->dma_ctrl);
    dma_channel_unclaim((uint)st->dma_data);
    st->dma_ready = false;
}

uint32_t hub75_dma_read_addr(const hub75_t *st) {
    return dma_hw->ch[st->dma_data].read_addr;
}

bool hub75_dma_busy(const hub75_t *st) {
    return dma_channel_is_busy((uint)st->dma_data) || dma_channel_is_busy((uint)st->dma_ctrl);
}

// Make buffer `index` the front buffer and wait (bounded) until the DMA has
// started reading it.  After that the other buffer is free to be overwritten.
void hub75_dma_publish(hub75_t *st, uint32_t index) {
    const uint32_t start = (uint32_t)st->buffers[index];
    const uint32_t end = start + st->frame_words * sizeof(uint32_t);

    st->front = index;
    st->dma_front_addr = start;

    if (!st->dma_ready) {
        return;
    }

    const uint32_t timeout_us = 2u * st->frame_us + 2000u;
    const uint32_t t0 = time_us_32();
    while ((uint32_t)(time_us_32() - t0) < timeout_us) {
        const uint32_t ra = hub75_dma_read_addr(st);
        if (ra >= start && ra < end) {
            break;
        }
    }
}
