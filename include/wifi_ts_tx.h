/* SPDX-License-Identifier: MIT */
#ifndef WIFI_TS_TX_H
#define WIFI_TS_TX_H
#include <stdint.h>
/* Single UART/SDIO task owner. Pack 1..14 TS packets in one or two HIF
 * frames, with 4-byte frame alignment and an explicit zero terminator.
 * Returns a 512-byte-rounded transfer size, zero on invalid arguments. */
unsigned wifi_ts_tx_pack(const uint8_t *data,unsigned count,unsigned sequence,
    unsigned index,unsigned flags,const uint8_t *mac,const uint8_t *peer,
    uint8_t *out,unsigned capacity);
/* Opt-in queue comparison: more_data 0 keeps the established descriptor;
 * 1 marks non-final aggregate frames as MORE_DATA_ENABLED=3. */
unsigned wifi_ts_tx_pack_forwarding(const uint8_t *data,unsigned count,unsigned sequence,
    unsigned index,unsigned flags,const uint8_t *mac,const uint8_t *peer,
    uint8_t *out,unsigned capacity,unsigned more_data);
#endif
