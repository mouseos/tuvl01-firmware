/* SPDX-License-Identifier: MIT */
#ifndef WIFI_LINK_H
#define WIFI_LINK_H
#include <stdint.h>
struct wifi_link_entry { int rssi; unsigned quality_raw,speed_raw,busy_raw,ready; };
struct wifi_link_quality { unsigned count,ready_known; struct wifi_link_entry entry[2]; };
int wifi_link_decode(const uint8_t *packet,unsigned length,uint8_t sequence,
                     struct wifi_link_quality *quality);
#endif
