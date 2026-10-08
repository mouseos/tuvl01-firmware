/* SPDX-License-Identifier: MIT. Independent serialization of public ABI facts. */
#include "wifi_fw_query.h"
static uint32_t le32(const uint8_t *p){
    return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
unsigned wifi_compile_query(uint8_t *out,unsigned capacity,unsigned index){
    if(!out || capacity<272 || index>1)return 0;
    for(unsigned n=0;n<272;n++)out[n]=0;
    out[8]=index;out[10]=0x24;out[11]=0xa0;
    return 272;
}
int wifi_compile_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                        unsigned index,uint32_t *flags){
    if(!p || !flags || index>1 || (length!=16 && length!=272) ||
       (p[0]|((unsigned)p[1]<<8))!=length || (p[2]|((unsigned)p[3]<<8))!=1 ||
       p[4]!=0x1f || p[5]!=sequence || le32(p+8)!=(0xa0240000UL|index))return 0;
    *flags=le32(p+12);return 1;
}
unsigned wifi_station_query(uint8_t *out,unsigned capacity,const uint8_t *peer){
    if(!out || !peer || capacity<36)return 0;
    for(unsigned n=0;n<36;n++)out[n]=0;
    /* station index0, flags0, read-clear0; exact peer MAC at body offset4. */
    for(unsigned n=0;n<6;n++)out[12+n]=peer[n];
    return 36;
}
/* B0000000: optional all-debug read, not a register write or a rate setter. */
unsigned wifi_radio_debug_query(uint8_t *out,unsigned capacity){
    return wifi_radio_debug_group_query(out,capacity,0);
}
unsigned wifi_radio_debug_group_query(uint8_t *out,unsigned capacity,unsigned group){
    if(!out || capacity<272 || group>3)return 0;
    for(unsigned n=0;n<272;n++)out[n]=0;
    out[8]=group;out[11]=0xb0;
    return 272;
}
int wifi_radio_debug_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                            uint32_t words[64]){
    return wifi_radio_debug_group_decode(p,length,sequence,0,words);
}
int wifi_radio_debug_group_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                                  unsigned group,uint32_t words[64]){
    if(!p || !words || group>3 || length!=272 ||
       (p[0]|((unsigned)p[1]<<8))!=length || (p[2]|((unsigned)p[3]<<8))!=1 ||
       p[4]!=0x1f || p[5]!=sequence || le32(p+8)!=(0xb0000000UL|group) || le32(p+12)!=group)return 0;
    for(unsigned n=0;n<64;n++)words[n]=le32(p+16+4*n);
    return 1;
}

/* Fixed firmware mailbox addresses only; no generic register access. */
unsigned wifi_rate_mailbox_query(uint8_t *out,unsigned capacity,unsigned index){
    if(!out || capacity<16 || index>1)return 0;
    for(unsigned n=0;n<16;n++)out[n]=0;
    out[8]=index*4;out[9]=1;out[11]=0x90;return 16;
}
int wifi_rate_mailbox_decode(const uint8_t *p,unsigned length,uint8_t sequence,
                              unsigned index,uint32_t *value){
    if(!p || !value || index>1 || length!=16 ||
       (p[0]|((unsigned)p[1]<<8))!=length || (p[2]|((unsigned)p[3]<<8))!=1 ||
       p[4]!=0x0a || p[5]!=sequence || le32(p+8)!=(0x90000100UL+index*4))return 0;
    *value=le32(p+12);return 1;
}

/* Independent fixed PER configuration, eight address/data commands. */
unsigned wifi_auto_per_command(uint8_t *out,unsigned capacity,unsigned step){
    if(!out || capacity<16 || step>7)return 0;
    static const uint32_t values[8]={1,0x00850000,1,0x00870000,0,0x009c0000,0,0x009d0000};
    for(unsigned n=0;n<16;n++)out[n]=0;
    out[8]=(step&1)?0:4;out[9]=1;out[11]=0x90;
    for(unsigned n=0;n<4;n++)out[12+n]=(uint8_t)(values[step]>>(n*8));
    return 16;
}
