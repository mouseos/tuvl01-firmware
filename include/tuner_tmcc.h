/* SPDX-License-Identifier: MIT */
#ifndef TUNER_TMCC_H
#define TUNER_TMCC_H
#include <stdint.h>
struct tuner_tmcc_layer { uint8_t modulation,code_rate,interleave,segments; };
struct tuner_tmcc_info {
    uint8_t system,countdown,emergency,partial,phase;
    struct tuner_tmcc_layer layer[3];
};
void tuner_tmcc_decode(const uint8_t raw[8],struct tuner_tmcc_info *info);
void tuner_tmcc_read(void);
void tuner_band_base(unsigned value);
#endif
