/* SPDX-License-Identifier: MIT */
#ifndef WIFI_STATION_H
#define WIFI_STATION_H
#include <stdint.h>
struct wifi_station_config {
    uint8_t peer[6];
    uint16_t aid,listen,operational,basic;
    uint8_t network,phy,state,rcpi;
};
/* Prefix8 + station body40. Network0 is AIS legacy AP role0x41;
 * network1 is existing P2P client role0x22. Station index0, legacy PHY.
 * QoS/HT may be added by a separate negotiated-HT serializer afterwards.
 * Input may alias output; invalid input leaves output untouched. No I/O. */
unsigned wifi_station_pack(uint8_t *,unsigned,const struct wifi_station_config *);
#endif
