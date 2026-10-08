/* SPDX-License-Identifier: MIT */
#ifndef WIFI_CHANNEL_H
#define WIFI_CHANNEL_H
#include <stdint.h>
unsigned wifi_channel_next(unsigned channel);
int wifi_channel_request(uint8_t *out,unsigned capacity,unsigned channel,unsigned token,const uint8_t *mac);
/* AP acquisition uses zero BSSID; mode1 preserves the former local-MAC request. */
int wifi_channel_request_ap(uint8_t *out,unsigned capacity,unsigned channel,unsigned token,unsigned mode,const uint8_t *mac);
int wifi_channel_grant(const uint8_t *packet,unsigned length,unsigned channel,unsigned token);
/* AIS0 JOIN, 2.4GHz channel1..13, selected AP BSSID and bounded explicit lease.
 * No radio I/O. Request input/output alias supported; failure output unchanged.
 * Grant requires matching network/token/channel/band/SCO/JOIN and nonzero lease;
 * caller must finish within granted_ms, not the originally requested interval. */
int wifi_channel_request_ais(uint8_t *,unsigned,unsigned channel,unsigned token,
    uint32_t max_interval_ms,const uint8_t ap[6]);
int wifi_channel_grant_ais(const uint8_t *,unsigned,unsigned channel,unsigned token,
    uint32_t *granted_ms);
#endif
