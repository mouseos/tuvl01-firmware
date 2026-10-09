/* SPDX-License-Identifier: MIT */
#ifndef WIFI_NET_H
#define WIFI_NET_H
#include <stdint.h>
#define WIFI_NET_IP 0xc0a84a01UL
#define WIFI_NET_PEER_IP 0xc0a84a02UL
#define WIFI_NET_UDP_PORT 4201
/* Body may already occupy out+42; otherwise it must not overlap output. */
unsigned wifi_net_udp(const uint8_t *body,unsigned length,unsigned port,
                      const uint8_t *mac,const uint8_t *peer,uint8_t *out,unsigned capacity);
/* Single associated peer; no routing/DNS, no heap, no fragmented IP packets.
 * Request and output must not overlap. Zero means no response. */
unsigned wifi_net_reply(const uint8_t *frame,unsigned length,const uint8_t *mac,
                        const uint8_t *peer,uint8_t *out,unsigned capacity);
#endif
