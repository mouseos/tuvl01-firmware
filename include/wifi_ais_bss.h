/* SPDX-License-Identifier: MIT */
#ifndef WIFI_AIS_BSS_H
#define WIFI_AIS_BSS_H
#include <stdint.h>
struct wifi_ais_bss_config {
    uint8_t own[6],ap[6],ssid[32];
    uint16_t operational,basic;
    uint8_t ssid_length,channel,connected,phy,enc_status;
    uint8_t short_preamble,short_slot,erp_protection;
};
/* Prefix8 + BSS body80 for AIS0/infra0/WPA2PSK7/station0. Legacy PHY only.
 * Cipher status6=CCMP enabled,7=key absent, selected explicitly by caller.
 * connected is a host Boolean, translated to wire media state0/1 for
 * connected/disconnected. It means association, not WPA completion.
 * Caller supplies negotiated rate sets and beacon/RLM-derived parameters.
 * This serializer neither installs keys nor emits PM_BSS_CONNECTED.
 * Input may alias output; invalid input leaves output untouched. */
unsigned wifi_ais_bss_pack(uint8_t *,unsigned,const struct wifi_ais_bss_config *);
#endif
