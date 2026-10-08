/* SPDX-License-Identifier: MIT */
#ifndef WIFI_SCAN_CACHE_H
#define WIFI_SCAN_CACHE_H
#include "wifi_ais_beacon.h"
#define WIFI_SCAN_CACHE_CAPACITY 16
struct wifi_scan_cache_entry {
    struct wifi_ais_beacon beacon;
    uint32_t seen,profile;
    uint8_t rcpi;
};
struct wifi_scan_cache {
    struct wifi_scan_cache_entry entries[WIFI_SCAN_CACHE_CAPACITY];
    unsigned count,next,active,complete;
};
void wifi_scan_cache_begin(struct wifi_scan_cache *);
void wifi_scan_cache_finish(struct wifi_scan_cache *,unsigned success);
void wifi_scan_cache_observe(struct wifi_scan_cache *,const struct wifi_ais_beacon *,
                             uint32_t tick,unsigned profile,uint8_t rcpi);
int wifi_scan_cache_select(const struct wifi_scan_cache *,uint32_t now,uint32_t age,
                          unsigned profile,const uint8_t *ap,unsigned channel,
                          struct wifi_ais_beacon *,uint8_t *rcpi);
#endif
