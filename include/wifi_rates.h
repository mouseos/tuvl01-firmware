/* SPDX-License-Identifier: MIT */
#ifndef WIFI_RATES_H
#define WIFI_RATES_H
#include <stdint.h>
struct wifi_rates {uint16_t operational,basic;uint8_t phy;const uint8_t *ies;unsigned length;};
const struct wifi_rates *wifi_rates_get(unsigned profile);
/* kind 0: probe SSID/rates/DS/ERP, 1: beacon with TIM, 2: association rates. */
unsigned wifi_rates_ies(unsigned profile,unsigned kind,uint8_t *out,unsigned capacity);
unsigned wifi_rates_ies_channel(unsigned profile,unsigned kind,unsigned channel,uint8_t *out,unsigned capacity);
#endif
