/* SPDX-License-Identifier: MIT */
#ifndef WIFI_RX_SINK_H
#define WIFI_RX_SINK_H
#include <stdint.h>
#define WIFI_RX_SINK_PORT 4203
struct wifi_rx_sink {
    uint32_t packets,bytes,missing,reordered,invalid,next_sequence;
    uint32_t first_tick,last_tick,max_gap_ticks,overflow;
};
/* Caller already validated HIF station and peer activation.
 * Dedicated unicast IPv4 UDP only; no reply is generated.
 * Returns 1 for a valid dedicated UDP envelope, including a bad test body,
 * so that such traffic does not enter the reply queue. */
int wifi_rx_sink_receive(struct wifi_rx_sink *s,const uint8_t *frame,unsigned length,
                        const uint8_t *mac,const uint8_t *peer,uint32_t tick);
#endif
