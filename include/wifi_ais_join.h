/* SPDX-License-Identifier: MIT */
#ifndef WIFI_AIS_JOIN_H
#define WIFI_AIS_JOIN_H
#include "wifi_ais_beacon.h"
#include "wifi_ais_mgmt.h"
struct wifi_ais_join {
    struct wifi_ais_beacon selected,connected_beacon;
    uint8_t own[6],rcpi,profile,watch,activated,beacon_seen;
    uint16_t aid,capability,operational,basic;
};
/* Legacy non-QoS association only. Values copied before RX buffer reuse.
 * This does not prove firmware applied BSS parameters or installed keys. */
int wifi_ais_join_prepare(struct wifi_ais_join *,const uint8_t own[6],
    const struct wifi_ais_beacon *,const struct wifi_ais_assoc *,unsigned profile,unsigned rcpi);
unsigned wifi_ais_join_bss(const struct wifi_ais_join *,uint8_t *,unsigned);
unsigned wifi_ais_join_station(const struct wifi_ais_join *,uint8_t *,unsigned);
/* Arm when starting the connected BSS update, before its command wait.
 * Receive hooks retain live beacons and activation in either order.
 * Scan-cache TIM never satisfies this gate. */
void wifi_ais_join_watch(struct wifi_ais_join *);
void wifi_ais_join_observe(struct wifi_ais_join *,const uint8_t *,unsigned);
/* Prefix8 + PM body12; only after matching AIS0 station0 activation and a
 * a validated on-channel beacon with TIM received after watch was armed.
 * The beacon may precede the activation event. No UAPSD negotiation. */
unsigned wifi_ais_join_pm(const struct wifi_ais_join *,uint8_t *,unsigned);
#endif
