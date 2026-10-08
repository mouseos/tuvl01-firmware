/* SPDX-License-Identifier: MIT */
#include "tuner_tmcc.h"
void tuner_tmcc_decode(const uint8_t raw[8],struct tuner_tmcc_info *info){
    info->system=(raw[0]>>5)&3;info->countdown=(raw[0]>>1)&15;
    info->emergency=raw[0]&1;info->partial=raw[1]>>6;info->phase=raw[7]&7;
    for(unsigned n=0;n<3;n++){
        info->layer[n].modulation=(raw[1+n*2]>>3)&7;
        info->layer[n].code_rate=raw[1+n*2]&7;
        info->layer[n].interleave=(raw[2+n*2]>>4)&7;
        info->layer[n].segments=raw[2+n*2]&15;
    }
}
