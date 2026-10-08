/* SPDX-License-Identifier: MIT */
#ifndef WIFI_HT_H
#define WIFI_HT_H
#include <stdint.h>
struct wifi_ht_peer {uint16_t capability;uint8_t ampdu,mcs,present,qos;};
/* Complete bounded IE list; malformed/duplicate capability leaves out intact. */
int wifi_ht_parse(const uint8_t *ies,unsigned length,struct wifi_ht_peer *out);
int wifi_ht_active(const struct wifi_ht_peer *peer);
/* Optional 20MHz, single-stream, long-GI HT and non-UAPSD WMM parameters. */
unsigned wifi_ht_ies(uint8_t *out,unsigned capacity,unsigned channel,unsigned ht,unsigned qos);
/* Update only QoS/HT fields in the existing 8B-prefix+40B station command. */
int wifi_ht_station(uint8_t *command,unsigned length,const struct wifi_ht_peer *peer);
/* WMM AC parameters agreeing with the advertised IE, prefix8/network1. */
unsigned wifi_ht_queues(uint8_t *out,unsigned capacity);
/* Beacon command with explicit IE length and zero transport alignment. */
unsigned wifi_beacon_pack(uint8_t *out,unsigned capacity,const uint8_t *ies,unsigned length);
#endif
