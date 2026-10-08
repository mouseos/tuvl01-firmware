/* SPDX-License-Identifier: MIT */
#ifndef WIFI_AIS_MGMT_H
#define WIFI_AIS_MGMT_H
#include <stdint.h>
struct wifi_ais_assoc {
    uint16_t status,capability,aid,operational,basic;
    const uint8_t *ies;
    unsigned ie_length;
};
/* Raw 802.11 management frames, no HIF or FCS. No I/O or state transition.
 * Own/AP must be distinct nonzero unicast MACs; output must not alias inputs.
 * Sequence is a 12-bit sequence number. Failure leaves output untouched. */
unsigned wifi_ais_auth_request(const uint8_t own[6],const uint8_t ap[6],
    unsigned sequence,uint8_t *out,unsigned capacity);
/* Return 1 for a structurally valid response, including AP rejection.
 * Only status==0 is successful authentication. Failure clears status to 0xffff. */
int wifi_ais_auth_response(const uint8_t *,unsigned,const uint8_t own[6],
    const uint8_t ap[6],uint16_t *status);
/* RSN IE is generated/validated by the supplicant before this call; this
 * serializer checks only IE framing. No privacy/crypto capability is inferred.
 * Capability may contain ESS/privacy/short-preamble/short-slot only. */
unsigned wifi_ais_assoc_request(const uint8_t own[6],const uint8_t ap[6],
    unsigned sequence,uint16_t capability,uint16_t listen,
    const uint8_t *ssid,unsigned ssid_length,const uint8_t *rsn,unsigned rsn_length,
    unsigned rate_profile,uint8_t *out,unsigned capacity);
/* On status==0, decode actual AID, capability, supported/basic rates. IEs borrow
 * input lifetime for later WMM/RLM handling. No HT/WMM processing here.
 * Return 1 also for structurally valid rejection, which has aid/rates zero.
 * Invalid input clears the result; callers must never activate on return alone. */
int wifi_ais_assoc_response(const uint8_t *,unsigned,const uint8_t own[6],
    const uint8_t ap[6],unsigned rate_profile,struct wifi_ais_assoc *);
#endif
