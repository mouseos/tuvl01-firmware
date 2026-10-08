/* SPDX-License-Identifier: MIT */
#include "tuner_profile.h"
static uint32_t be32(const uint8_t *p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
int tuner_profile_valid(const uint8_t *p){
    if(!p || be32(p)!=0x54554e31UL || p[27]>2 || p[16]>15 || !p[15])return 0;
    uint32_t frequency=be32(p+4),crc=0xffffffffUL;
    if((!p[27] && (frequency<90000 || frequency>108000)) ||
       (p[27] && (frequency<470000 || frequency>770000)))return 0;
    if(p[27]==2){if(p[26]!=0x16)return 0;}
    else if((p[26]&0xc0)!=(p[27]?0x40:0xc0))return 0;
    for(unsigned n=0;n<28;n++){
        crc^=p[n];
        for(unsigned b=0;b<8;b++)crc=(crc>>1)^((crc&1)?0xedb88320UL:0);
    }
    return ~crc==be32(p+28);
}
