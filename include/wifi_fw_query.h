/* SPDX-License-Identifier: MIT */
#ifndef WIFI_FW_QUERY_H
#define WIFI_FW_QUERY_H
#include <stdint.h>
unsigned wifi_compile_query(uint8_t *out,unsigned capacity,unsigned index);
int wifi_compile_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                        unsigned index,uint32_t *flags);
unsigned wifi_station_query(uint8_t *out,unsigned capacity,const uint8_t *peer);
unsigned wifi_radio_debug_query(uint8_t *out,unsigned capacity);
unsigned wifi_radio_debug_group_query(uint8_t *out,unsigned capacity,unsigned group);
int wifi_radio_debug_group_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                                  unsigned group,uint32_t words[64]);
int wifi_radio_debug_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                            uint32_t words[64]);
unsigned wifi_rate_mailbox_query(uint8_t *out,unsigned capacity,unsigned index);
int wifi_rate_mailbox_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                              unsigned index,uint32_t *value);
unsigned wifi_auto_per_command(uint8_t *out,unsigned capacity,unsigned step);
#endif
