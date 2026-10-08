/* SPDX-License-Identifier: MIT. Independent MT5931 passive scan ABI. */
#include "wifi_scan.h"
unsigned wifi_scan_passive(uint8_t *out,unsigned capacity,unsigned sequence,
    unsigned first_channel,unsigned last_channel){
    if(!out || capacity<120 || !sequence || sequence>255 || first_channel<1 ||
       last_channel>13 || first_channel>last_channel)return 0;
    for(unsigned i=0;i<120;i++)out[i]=0;
    out[8]=(uint8_t)sequence;out[11]=1;
    out[14]=100;out[48]=100;out[50]=4;
    unsigned count=last_channel-first_channel+1;out[51]=(uint8_t)count;
    for(unsigned i=0;i<count;i++){out[52+i*2]=1;out[53+i*2]=(uint8_t)(first_channel+i);}
    return 120;
}
int wifi_scan_done(const uint8_t *p,unsigned n,unsigned sequence){
    return p && n==12 && (p[0]|((unsigned)p[1]<<8))==n && (p[2]&3)==1 &&
        p[4]==0x15 && sequence && sequence<=255 && p[8]==sequence;
}
unsigned wifi_scan_cancel(uint8_t *out,unsigned capacity,unsigned sequence){
    if(!out || capacity<12 || !sequence || sequence>255)return 0;
    for(unsigned i=0;i<12;i++)out[i]=0;
    out[8]=(uint8_t)sequence;
    return 12;
}
