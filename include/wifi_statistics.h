/* SPDX-License-Identifier: MIT */
#ifndef WIFI_STATISTICS_H
#define WIFI_STATISTICS_H
#include <stdint.h>
struct wifi_counter { uint32_t low,high; };
int wifi_statistics_decode(const uint8_t *packet,unsigned length,uint8_t sequence,
                           struct wifi_counter counters[12]);
#endif
