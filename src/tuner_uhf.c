/* SPDX-License-Identifier: MIT */
#include "tuner_uhf.h"
static void put(uint8_t *p,unsigned bytes,uint32_t v){while(bytes--)*p++=(uint8_t)(v>>(8*bytes));}
int tuner_uhf_profile(unsigned channel,unsigned partial,uint8_t out[32]){
    if(!out || channel<TUNER_UHF_FIRST || channel>TUNER_UHF_LAST)return -1;
    const struct tuner_uhf_entry *e=tuner_uhf_table+(channel-TUNER_UHF_FIRST);
    out[0]='T';out[1]='U';out[2]='N';out[3]='1';
    put(out+4,4,473143UL+6000UL*(channel-TUNER_UHF_FIRST));
    put(out+8,3,e->fad);put(out+11,3,e->nco);
    out[14]=e->sysset;out[15]=e->p_m;put(out+16,3,e->p_k);
    out[19]=e->tncop1;out[20]=e->tncop2;out[21]=e->tncop3;out[22]=e->tncop4;
    out[23]=0;out[24]=e->tncop7;out[25]=e->adclksel;
    out[26]=partial?0x56:0x16;out[27]=partial?1:2;
    uint32_t crc=0xffffffffUL;
    for(unsigned n=0;n<28;n++){
        crc^=out[n];
        for(unsigned b=0;b<8;b++)crc=(crc>>1)^((crc&1)?0xedb88320UL:0);
    }
    put(out+28,4,~crc);
    return 0;
}
