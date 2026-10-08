/* SPDX-License-Identifier: MIT */
#ifndef TUVL_PROVISION_H
#define TUVL_PROVISION_H
#include <stddef.h>
#include <stdint.h>
#define TUVL_PROVISION_BYTES 148u
struct tuvl_provision {
    uint8_t channel,ssid_length,ap[6],ssid[32],pmk[32],entropy[64];
};
/* Trusted local UART only: CRC detects corruption, not authentication.
 * apply must consume/copy before returning; zero means accepted only.
 * Packet (n<=148) and temporary credentials are wiped even on failure.
 * Caller must discard/wipe oversized input separately. One owner only.
 * Entropy quality cannot be measured here; PC must provide fresh CSPRNG data.
 */
int tuvl_provision_consume(uint8_t *,size_t,
    int (*apply)(void *,const struct tuvl_provision *),void *);
#endif
