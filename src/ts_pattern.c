/* SPDX-License-Identifier: MIT */
#include "ts_pattern.h"
unsigned ts_pattern_fill(uint8_t *out,unsigned capacity){
    if(!out || capacity<32*188)return 0;
    for(unsigned packet=0;packet<32;packet++){
        uint8_t *p=out+packet*188;
        p[0]=0x47;p[1]=0x1f;p[2]=0xfe;p[3]=0x10|(packet&15);
        for(unsigned i=4;i<188;i++)p[i]=0xff;
    }
    return 32;
}

unsigned ts_pattern_dma_fill(uint8_t *out,unsigned capacity){
    if(ts_pattern_fill(out,capacity)!=32)return 0;
    for(unsigned packet=0;packet<32;packet++)
        for(unsigned i=4;i<188;i++)out[packet*188+i]=(uint8_t)(i*37+packet*11+3);
    return 32;
}
