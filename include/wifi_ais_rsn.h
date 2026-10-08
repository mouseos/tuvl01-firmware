/* SPDX-License-Identifier: MIT */
#ifndef WIFI_AIS_RSN_H
#define WIFI_AIS_RSN_H
#include <stdint.h>
/* Finite pre-key-exchange association probe policy: explicit WPA2 PSK/CCMP,
 * no cached PMKID, no MFP requirement. Generates a 22-byte selection IE.
 * This does not authenticate a PSK or replace the supplicant key exchange.
 * Malformed/unsupported AP IEs fail without changing output; aliasing is OK. */
unsigned wifi_ais_rsn_select(const uint8_t *,unsigned,uint8_t *,unsigned);
#endif
