/* SPDX-License-Identifier: MIT */
#ifndef WIFI_MGMT_H
#define WIFI_MGMT_H
#include <stdint.h>
/* Input/output are 802.11 frames without the transport header. Returns the
 * response length, or zero for unsupported/malformed/non-local requests. */
unsigned wifi_mgmt_reply(const uint8_t *request,unsigned length,
                         const uint8_t mac[6],uint16_t sequence,
                         uint8_t *reply,unsigned capacity);
/* Association requires the MAC of a peer whose open-auth TX completed. */
unsigned wifi_assoc_reply(const uint8_t *request,unsigned length,
                         const uint8_t mac[6],const uint8_t peer[6],
                         uint16_t sequence,uint8_t *reply,unsigned capacity,
                         uint16_t *rates,uint16_t *listen_interval);
unsigned wifi_mgmt_reply_profile(const uint8_t *request,unsigned length,
                         const uint8_t mac[6],uint16_t sequence,
                         uint8_t *reply,unsigned capacity,unsigned profile);
unsigned wifi_mgmt_reply_channel(const uint8_t *request,unsigned length,
                         const uint8_t mac[6],uint16_t sequence,
                         uint8_t *reply,unsigned capacity,unsigned profile,unsigned channel);
unsigned wifi_assoc_reply_profile(const uint8_t *request,unsigned length,
                         const uint8_t mac[6],const uint8_t peer[6],
                         uint16_t sequence,uint8_t *reply,unsigned capacity,
                         uint16_t *rates,uint16_t *listen_interval,unsigned profile);
#endif
