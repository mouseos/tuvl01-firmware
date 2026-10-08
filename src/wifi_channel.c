/* SPDX-License-Identifier: MIT. Independent bounded AP channel protocol. */
#include "wifi_channel.h"
unsigned wifi_channel_next(unsigned channel){
    return channel==1?6:channel==6?11:channel==11?1:0;
}
int wifi_channel_request(uint8_t *out,unsigned capacity,unsigned channel,unsigned token,const uint8_t *mac){
    if(!out || !mac || capacity<28 || !wifi_channel_next(channel) || !token || token>255)return 0;
    for(unsigned n=0;n<28;n++)out[n]=0;
    out[8]=1;out[9]=token;out[11]=channel;out[13]=1;
    out[16]=0x60;out[17]=0xea; /* 60000 ms, little endian. */
    for(unsigned n=0;n<6;n++)out[20+n]=mac[n];
    return 1;
}
int wifi_channel_grant(const uint8_t *p,unsigned length,unsigned channel,unsigned token){
    return p && length>=20 && wifi_channel_next(channel) && token && token<=255 &&
        p[4]==0x18 && p[8]==1 && p[9]==token && !p[10] && p[11]==channel && !p[12] && p[13]==1;
}
int wifi_channel_request_ap(uint8_t *out,unsigned capacity,unsigned channel,unsigned token,unsigned mode,const uint8_t *mac){
    static const uint8_t zero[6]={0};
    if(!mac || mode>1)return 0;
    return wifi_channel_request(out,capacity,channel,token,mode?mac:zero);
}
int wifi_channel_request_ais(uint8_t *out,unsigned capacity,unsigned channel,unsigned token,
    uint32_t max_interval_ms,const uint8_t ap[6]){
    if(!out || !ap || capacity<28 || channel<1 || channel>13 || !token ||
       token>255 || !max_interval_ms || max_interval_ms>60000 || (ap[0]&1))return 0;
    unsigned nonzero=0;for(unsigned i=0;i<6;i++)nonzero|=ap[i];
    if(!nonzero)return 0;
    uint8_t p[28]={0};p[9]=(uint8_t)token;p[11]=(uint8_t)channel;p[13]=1;
    for(unsigned i=0;i<4;i++)p[16+i]=(uint8_t)(max_interval_ms>>(8*i));
    for(unsigned i=0;i<6;i++)p[20+i]=ap[i];
    for(unsigned i=0;i<28;i++)out[i]=p[i];
    return 1;
}
int wifi_channel_grant_ais(const uint8_t *p,unsigned n,unsigned channel,unsigned token,
    uint32_t *granted_ms){
    if(!granted_ms)return 0;
    *granted_ms=0;
    if(!p || n!=20 || (p[0]|((unsigned)p[1]<<8))!=n || (p[2]&3)!=1 ||
       p[4]!=0x18 || p[8] || !token || token>255 || p[9]!=token || p[10] ||
       channel<1 || channel>13 || p[11]!=channel || p[12] || p[13]!=1 || p[14])return 0;
    uint32_t interval=0;for(unsigned i=0;i<4;i++)interval|=(uint32_t)p[16+i]<<(8*i);
    if(!interval || interval>60000)return 0;
    *granted_ms=interval;return 1;
}
