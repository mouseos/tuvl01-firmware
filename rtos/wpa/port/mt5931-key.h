/* SPDX-License-Identifier: MIT; independent serialization of public ABI facts. */
#ifndef TUVL_MT5931_KEY_H
#define TUVL_MT5931_KEY_H
#include <stddef.h>
#include <stdint.h>
struct tuvl_mt5931_key {
    unsigned add, transmit, pairwise, index;
    const uint8_t *peer;
    const uint8_t *key;
    size_t key_length;
    /* Opaque firmware RSC bytes, not a supplicant sequence conversion.
     * Caller must establish that conversion before using a nonzero RSC.
     */
    const uint8_t *rsc;
    size_t rsc_length;
};
/* AIS network0, supplicant role, CCMP only. Returns body length64, else0.
 * Invalid inputs leave output intact; does not send/install any key.
 */
size_t tuvl_mt5931_key_body(uint8_t *,size_t,const struct tuvl_mt5931_key *);
/* Restricted bridge for a supplicant CCMP sequence: absent or six zero bytes
 * only. The reference CCMP OID zeroes the firmware RSC; its 16-byte PN copy
 * belongs to WPI, so no nonzero CCMP sequence conversion is asserted.
 * Nonzero/other-sized sequences and prefilled firmware RSC are refused before
 * output mutation. This does not send or verify a hardware key installation. */
size_t tuvl_mt5931_key_zero_sequence(uint8_t *,size_t,
    const struct tuvl_mt5931_key *,const uint8_t *,size_t);
/* Parse an optional generic CID08 result. Returns1 for a matched result,
 * with raw status; this is NOT a key-application completion guarantee.
 */
int tuvl_mt5931_key_result(const uint8_t *,size_t,uint8_t,uint8_t *);
#endif
