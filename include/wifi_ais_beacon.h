/* SPDX-License-Identifier: MIT */
#ifndef WIFI_AIS_BEACON_H
#define WIFI_AIS_BEACON_H
#include <stdint.h>
struct wifi_ais_beacon {
    uint8_t ap[6],ssid[32],rsn[257];
    uint16_t interval,capability,operational,basic,rsn_length;
    uint8_t ssid_length,channel,rx_channel,tim_present,dtim_count,dtim_period;
    uint8_t short_preamble,short_slot,erp_protection;
};
/* Raw beacon without HIF/FCS; legacy 2.4GHz rates only. Copy all retained
 * values: output does not borrow an RX buffer. expected_ap may be NULL for
 * discovery; otherwise filter before parsing. RX channel is separate from DS
 * channel: caller must resolve mismatch before acquiring a channel.
 * Valid RSN framing/version is not cipher-policy validation. Missing TIM is
 * represented explicitly and cannot justify PM_BSS_CONNECTED notification.
 * Invalid input clears output. Input/output must not overlap. */
int wifi_ais_beacon_parse(const uint8_t *,unsigned,unsigned rx_channel,
    const uint8_t *expected_ap,unsigned rate_profile,struct wifi_ais_beacon *);
#endif
