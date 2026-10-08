/* SPDX-License-Identifier: MIT */
#ifndef WIFI_SCAN_H
#define WIFI_SCAN_H
#include <stdint.h>
/* Prefix8 + legacy scan body/padding112: AIS0 passive wildcard, explicit
 * contiguous 2.4GHz channels1..13, min/dwell fields100ms, empty probe IEs.
 * No I/O/activation; invalid input leaves output unchanged. */
unsigned wifi_scan_passive(uint8_t *,unsigned,unsigned sequence,
    unsigned first_channel,unsigned last_channel);
int wifi_scan_done(const uint8_t *,unsigned,unsigned sequence);
/* Prefix8 + cancellation body4: matching scan sequence, extension disabled. */
unsigned wifi_scan_cancel(uint8_t *,unsigned,unsigned sequence);
#endif
