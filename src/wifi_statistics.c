/* SPDX-License-Identifier: MIT */
#include "wifi_statistics.h"
static uint32_t le32(const uint8_t *p){
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
int wifi_statistics_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                           struct wifi_counter counters[12]){
    if(length<104 || (unsigned)(p[0]|((unsigned)p[1]<<8))!=length ||
       (p[2]|((unsigned)p[3]<<8))!=1 || p[4]!=6 || p[5]!=sequence)return 0;
    for(unsigned n=0;n<12;n++){
        counters[n].low=le32(p+8+n*8);
        counters[n].high=le32(p+12+n*8);
    }
    return 1;
}
