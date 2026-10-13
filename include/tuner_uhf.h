/* SPDX-License-Identifier: MIT */
#ifndef TUNER_UHF_H
#define TUNER_UHF_H
#include <stdint.h>
#define TUNER_UHF_FIRST 13U
#define TUNER_UHF_LAST 52U
#define TUNER_UHF_COUNT (TUNER_UHF_LAST-TUNER_UHF_FIRST+1U)
struct tuner_uhf_entry {
    uint32_t fad,nco,p_k;
    uint8_t tncop1,tncop2,tncop3,tncop4,tncop7,adclksel,p_m,sysset;
};
extern const struct tuner_uhf_entry tuner_uhf_table[TUNER_UHF_COUNT];
/* Builds the fixed 32-byte tuner profile (see tuner_profile_valid) for a UHF
 * channel. partial=0: full segment, partial=1: one segment. Returns 0, or -1 for
 * a channel outside 13..52. */
int tuner_uhf_profile(unsigned channel,unsigned partial,uint8_t out[32]);
#endif
