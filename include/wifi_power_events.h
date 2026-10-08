/* SPDX-License-Identifier: MIT */
#ifndef WIFI_POWER_EVENTS_H
#define WIFI_POWER_EVENTS_H
#include <stdint.h>
/* Observations only: PS quota is distinct from HIF buffer credits. */
struct wifi_power_events {
    uint32_t bss_events,ps_events,quota_events,foreign,invalid;
    uint32_t known,absent,in_ps,bss_quota,ps_mode,ps_quota,quota_mode,quota;
};
void wifi_power_events_reset(struct wifi_power_events *state);
/* 1 accepted target, 2 other target, 0 unrelated ID, -1 invalid layout.
 * known bits: 1 BSS absence, 2 station PS, 4 station quota. */
int wifi_power_events_observe(struct wifi_power_events *state,
    const uint8_t *packet,unsigned length,unsigned network,unsigned station);
#endif
