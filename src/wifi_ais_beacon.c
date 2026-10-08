/* SPDX-License-Identifier: MIT. Independent bounded infrastructure beacon codec. */
#include "wifi_ais_beacon.h"
#include "wifi_rates.h"
static unsigned le16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
int wifi_ais_beacon_parse(const uint8_t *p,unsigned n,unsigned rx_channel,
    const uint8_t *expected_ap,unsigned rate_profile,struct wifi_ais_beacon *out){
    if(!out)return 0;
    *out=(struct wifi_ais_beacon){0};
    const struct wifi_rates *r=wifi_rates_get(rate_profile);
    if(!r || !p || n<36 || p[0]!=0x80 || (p[1]&0xc7) || (p[22]&15) ||
       (p[10]&1) || rx_channel<1 || rx_channel>13 ||
       !le16(p+32) || (le16(p+34)&3)!=1)return 0;
    unsigned nonzero=0;
    for(unsigned i=0;i<6;i++){
        if(p[4+i]!=255 || p[10+i]!=p[16+i] ||
           (expected_ap && p[16+i]!=expected_ap[i]))return 0;
        nonzero|=p[16+i];
    }
    if(!nonzero)return 0;
    struct wifi_ais_beacon result={0};
    result.interval=(uint16_t)le16(p+32);result.capability=(uint16_t)le16(p+34);
    result.channel=result.rx_channel=(uint8_t)rx_channel;
    result.short_preamble=!!(result.capability&0x20);
    result.short_slot=!!(result.capability&0x400);
    for(unsigned i=0;i<6;i++)result.ap[i]=p[16+i];
    unsigned seen=0,mask=0,basic=0;
    static const uint8_t codes[]={2,4,11,22,0,0,12,18,24,36,48,72,96,108};
    for(unsigned pos=36;pos<n;){
        if(n-pos<2 || p[pos+1]>n-pos-2)return 0;
        unsigned id=p[pos],count=p[pos+1],flag=0;
        const uint8_t *ie=p+pos+2;
        switch(id){
        case 0:
            flag=1;if(count>32)return 0;result.ssid_length=(uint8_t)count;
            for(unsigned i=0;i<count;i++)result.ssid[i]=ie[i];
            break;
        case 1:case 50:
            flag=id==1?2:4;if(!count || (id==1 && count>8))return 0;
            for(unsigned i=0;i<count;i++){
                unsigned value=ie[i],bit=0;
                for(unsigned j=0;j<sizeof codes;j++)if(codes[j] && codes[j]==(value&127)){bit=1U<<j;break;}
                if((value&128) && !(bit&r->operational))return 0;
                mask|=bit;if(value&128)basic|=bit;
            }
            break;
        case 3:
            flag=8;if(count!=1 || ie[0]<1 || ie[0]>13)return 0;
            result.channel=ie[0];break;
        case 5:
            flag=16;if(count<4 || !ie[1] || ie[0]>=ie[1])return 0;
            result.tim_present=1;result.dtim_count=ie[0];result.dtim_period=ie[1];break;
        case 42:
            flag=32;if(count!=1)return 0;
            result.erp_protection=!!(ie[0]&2);
            if(ie[0]&4)result.short_preamble=0;
            break;
        case 48:
            flag=64;if(count<2 || le16(ie)!=1)return 0;
            result.rsn_length=(uint16_t)(count+2);
            for(unsigned i=0;i<count+2;i++)result.rsn[i]=p[pos+i];
            break;
        default:break;
        }
        if(flag && (seen&flag))return 0;
        seen|=flag;pos+=2+count;
    }
    if((seen&3)!=3 || !(mask&r->operational) || !basic)return 0;
    result.operational=(uint16_t)(mask&r->operational);result.basic=(uint16_t)basic;
    *out=result;return 1;
}
