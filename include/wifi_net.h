/* SPDX-License-Identifier: MIT */
#ifndef WIFI_NET_H
#define WIFI_NET_H
#include <stdint.h>
#define WIFI_NET_IP 0xc0a84a01UL
#define WIFI_NET_PEER_IP 0xc0a84a02UL
#define WIFI_NET_UDP_PORT 4201
/* Optional device service: UDP datagrams to WIFI_NET_SERVICE_PORT are passed to
 * wifi_net_service() and its reply (at most WIFI_NET_SERVICE_MAX bytes) is sent
 * back to the sender port. Datagrams to the echo port are also reported (with a
 * null reply buffer) so the service can track client liveness. */
#define WIFI_NET_SERVICE_PORT 4200
#define WIFI_NET_SERVICE_MAX 32
typedef unsigned (*wifi_net_service_fn)(unsigned port,const uint8_t *body,unsigned length,
                                        uint8_t *reply,unsigned capacity);
extern wifi_net_service_fn wifi_net_service;
/* Body may already occupy out+42; otherwise it must not overlap output. */
unsigned wifi_net_udp(const uint8_t *body,unsigned length,unsigned port,
                      const uint8_t *mac,const uint8_t *peer,uint8_t *out,unsigned capacity);
/* Single associated peer; no routing/DNS, no heap, no fragmented IP packets.
 * Request and output must not overlap. Zero means no response. */
unsigned wifi_net_reply(const uint8_t *frame,unsigned length,const uint8_t *mac,
                        const uint8_t *peer,uint8_t *out,unsigned capacity);
#endif
