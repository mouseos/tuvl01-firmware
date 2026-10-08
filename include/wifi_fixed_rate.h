/* SPDX-License-Identifier: MIT */
#ifndef WIFI_FIXED_RATE_H
#define WIFI_FIXED_RATE_H
#include <stdint.h>
#include "wifi_ht.h"
/* Apply validated fixed-rate fields to a48B station command. MCS mode
 * 0=auto,1=MCS0,2=MCS7. Reject conflicting/unnegotiated rates unchanged. */
int wifi_fixed_rate_apply(uint8_t *command,unsigned length,unsigned legacy54,unsigned mcs,const struct wifi_ht_peer *peer);
#endif
