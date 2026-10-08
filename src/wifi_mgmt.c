/* SPDX-License-Identifier: MIT. Independent bounded open-AP management frames. */
#include "wifi_mgmt.h"
#include "wifi_rates.h"
static int same(const uint8_t *a,const uint8_t *b,unsigned n){
    for(unsigned i=0;i<n;i++)if(a[i]!=b[i])return 0;
    return 1;
}
static int broadcast(const uint8_t *a){
    for(unsigned i=0;i<6;i++)if(a[i]!=255)return 0;
    return 1;
}
unsigned wifi_mgmt_reply_channel(const uint8_t *p,unsigned n,const uint8_t mac[6],
                         uint16_t sequence,uint8_t *out,unsigned capacity,unsigned profile,unsigned channel){
    static const uint8_t ssid[]={'T','U','V','L','0','1'};
    uint8_t ies[36];unsigned ie_length=wifi_rates_ies_channel(profile,0,channel,ies,sizeof ies);
    if(!ie_length)return 0;
    if(n<24 || (p[1]&0xc7) || (p[22]&15) || (p[10]&1))return 0;
    unsigned nonzero=0;for(unsigned i=10;i<16;i++)nonzero|=p[i];
    if(!nonzero || same(p+10,mac,6))return 0;
    unsigned size,subtype=p[0];
    if(subtype==0x40){
        if((!same(p+4,mac,6)&&!broadcast(p+4)) ||
           (!same(p+16,mac,6)&&!broadcast(p+16)))return 0;
        unsigned found=0;
        for(unsigned pos=24;pos<n;){
            if(n-pos<2 || p[pos+1]>n-pos-2)return 0;
            unsigned count=p[pos+1];
            if(p[pos]==0){
                if(found || (count && (count!=6 || !same(p+pos+2,ssid,6))))return 0;
                found=1;
            }
            pos+=2+count;
        }
        if(!found)return 0;
        size=36+ie_length;
    }else if(subtype==0xb0){
        if(n!=30 || !same(p+4,mac,6) || !same(p+16,mac,6) ||
           p[24] || p[25] || p[26]!=1 || p[27] || p[28] || p[29])return 0;
        size=30;
    }else return 0;
    if(size>capacity)return 0;
    for(unsigned i=0;i<size;i++)out[i]=0;
    out[0]=subtype==0x40?0x50:0xb0;
    for(unsigned i=0;i<6;i++){out[4+i]=p[10+i];out[10+i]=out[16+i]=mac[i];}
    out[22]=(uint8_t)(sequence<<4);out[23]=(uint8_t)(sequence>>4);
    if(subtype==0xb0)out[26]=2;
    else{
        out[32]=100;out[34]=1;out[35]=4;
        for(unsigned i=0;i<ie_length;i++)out[36+i]=ies[i];
    }
    return size;
}
unsigned wifi_mgmt_reply_profile(const uint8_t *p,unsigned n,const uint8_t mac[6],
                         uint16_t sequence,uint8_t *out,unsigned capacity,unsigned profile){
    return wifi_mgmt_reply_channel(p,n,mac,sequence,out,capacity,profile,1);
}
unsigned wifi_assoc_reply_profile(const uint8_t *p,unsigned n,const uint8_t mac[6],
                         const uint8_t peer[6],uint16_t sequence,uint8_t *out,
                         unsigned capacity,uint16_t *rates,uint16_t *listen,unsigned profile){
    static const uint8_t ssid[]={'T','U','V','L','0','1'};
    static const uint8_t codes[]={2,4,11,22,0,0,12,18,24,36,48,72,96,108};
    const struct wifi_rates *r=wifi_rates_get(profile);
    if(!r)return 0;
    if(n<28 || p[0] || (p[1]&0xc7) || (p[22]&15) || (p[10]&1) ||
       !same(p+4,mac,6) || !same(p+16,mac,6) || !same(p+10,peer,6))return 0;
    unsigned nonzero=0;for(unsigned i=0;i<6;i++)nonzero|=peer[i];
    if(!nonzero || same(peer,mac,6))return 0;
    unsigned cap=p[24]|((unsigned)p[25]<<8);
    unsigned interval=p[26]|((unsigned)p[27]<<8);
    if((cap&0x13)!=1 || !interval)return 0; /* ESS, no IBSS/privacy */
    unsigned found=0,seen_rates=0,seen_extended=0,mask=0;
    for(unsigned pos=28;pos<n;){
        if(n-pos<2 || p[pos+1]>n-pos-2)return 0;
        unsigned id=p[pos],count=p[pos+1];
        if(id==0){
            if(found || count!=6 || !same(p+pos+2,ssid,6))return 0;
            found=1;
        }else if(id==1 || id==50){
            if(!count)return 0;
            if(id==1){if(seen_rates || count>8)return 0;seen_rates=1;}
            else{if(seen_extended)return 0;seen_extended=1;}
            for(unsigned i=0;i<count;i++){
                unsigned value=p[pos+2+i],known=0;
                for(unsigned j=0;j<sizeof codes;j++){
                    if(codes[j] && codes[j]==(value&127)){mask|=1U<<j;known=1;break;}
                }
                if(!known && (value&128))return 0;
            }
        }
        pos+=2+count;
    }
    if(!found || !seen_rates || (mask&r->basic)!=r->basic || capacity<30+r->length)return 0;
    unsigned size=30+r->length;
    for(unsigned i=0;i<size;i++)out[i]=0;
    out[0]=0x10;
    for(unsigned i=0;i<6;i++){out[4+i]=peer[i];out[10+i]=out[16+i]=mac[i];}
    out[22]=(uint8_t)(sequence<<4);out[23]=(uint8_t)(sequence>>4);
    out[24]=1;out[25]=4;out[28]=1;out[29]=0xc0; /* capability/status/AID1 */
    for(unsigned i=0;i<r->length;i++)out[30+i]=r->ies[i];
    *rates=(uint16_t)(mask&r->operational);*listen=(uint16_t)interval;
    return size;
}
unsigned wifi_mgmt_reply(const uint8_t *p,unsigned n,const uint8_t mac[6],uint16_t sequence,uint8_t *out,unsigned capacity){
    return wifi_mgmt_reply_profile(p,n,mac,sequence,out,capacity,0);
}
unsigned wifi_assoc_reply(const uint8_t *p,unsigned n,const uint8_t mac[6],const uint8_t peer[6],uint16_t sequence,
                         uint8_t *out,unsigned capacity,uint16_t *rates,uint16_t *listen){
    return wifi_assoc_reply_profile(p,n,mac,peer,sequence,out,capacity,rates,listen,0);
}
