/* SPDX-License-Identifier: MIT */
#ifndef TS_CHECK_H
#define TS_CHECK_H
#include <stdint.h>
struct ts_check {
    uint32_t packets,sync,tei,adaptation,comparisons,cc_jumps,cc_repeats;
    uint8_t last[8192];
};
void ts_check_reset(struct ts_check *state);
void ts_check_packet(struct ts_check *state,const uint8_t packet[188]);
#endif
