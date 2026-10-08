/* SPDX-License-Identifier: MIT */
#ifndef TUVL_SUPPLICANT_KEY_H
#define TUVL_SUPPLICANT_KEY_H
#include "session.h"
struct tuvl_key_transport {
    u8 ap[6];
    void *ctx;
    /* Consume/copy synchronously. Zero means accepted submission only,
     * not proof that hardware applied a key. The 64-byte body is wiped. */
    int (*submit)(void *,const u8 *,size_t);
};
/* Signature matches tuvl_rsn_driver.key. Initial CCMP pairwise RX/TX and
 * group RX only; unknown sequence/flags, MLO, other ciphers are refused.
 * Must not be called from an owner different from the radio/session owner. */
int tuvl_supplicant_key(void *,int,enum wpa_alg,const u8 *,int,int,
    const u8 *,size_t,const u8 *,size_t,enum key_flag);
#endif
