/* SPDX-License-Identifier: MIT. Independent infrastructure management codec. */
#include "wifi_ais_mgmt.h"
#include "wifi_rates.h"
static unsigned le16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
static int same(const uint8_t *a,const uint8_t *b){
    for(unsigned i=0;i<6;i++)if(a[i]!=b[i])return 0;
    return 1;
}
static int addresses(const uint8_t *own,const uint8_t *ap){
    if(!own || !ap || (own[0]&1) || (ap[0]&1) || same(own,ap))return 0;
    unsigned a=0,b=0;for(unsigned i=0;i<6;i++){a|=own[i];b|=ap[i];}
    return a && b;
}
static int overlap(const void *out,unsigned n,const void *in,unsigned length){
    uintptr_t a=(uintptr_t)out,b=(uintptr_t)in;
    return a<=b ? b-a<n : a-b<length;
}
static void header(uint8_t *out,unsigned n,unsigned subtype,const uint8_t *own,
                   const uint8_t *ap,unsigned sequence){
    for(unsigned i=0;i<n;i++)out[i]=0;
    out[0]=(uint8_t)subtype;
    for(unsigned i=0;i<6;i++){out[4+i]=out[16+i]=ap[i];out[10+i]=own[i];}
    out[22]=(uint8_t)(sequence<<4);out[23]=(uint8_t)(sequence>>4);
}
static int response(const uint8_t *p,unsigned n,unsigned subtype,
                    const uint8_t *own,const uint8_t *ap){
    return addresses(own,ap) && p && n>=30 && p[0]==subtype &&
        !(p[1]&0xc7) && !(p[22]&15) && same(p+4,own) &&
        same(p+10,ap) && same(p+16,ap);
}
unsigned wifi_ais_auth_request(const uint8_t own[6],const uint8_t ap[6],
    unsigned sequence,uint8_t *out,unsigned capacity){
    if(!addresses(own,ap) || sequence>4095 || !out || capacity<30 ||
       overlap(out,30,own,6) || overlap(out,30,ap,6))return 0;
    header(out,30,0xb0,own,ap,sequence);out[26]=1;return 30;
}
int wifi_ais_auth_response(const uint8_t *p,unsigned n,const uint8_t own[6],
    const uint8_t ap[6],uint16_t *status){
    if(!status)return 0;
    *status=0xffff;
    if(!response(p,n,0xb0,own,ap) || n!=30 || le16(p+24) || le16(p+26)!=2)return 0;
    *status=(uint16_t)le16(p+28);return 1;
}
unsigned wifi_ais_assoc_request(const uint8_t own[6],const uint8_t ap[6],
    unsigned sequence,uint16_t capability,uint16_t listen,
    const uint8_t *ssid,unsigned ssid_length,const uint8_t *rsn,unsigned rsn_length,
    unsigned rate_profile,uint8_t *out,unsigned capacity){
    const struct wifi_rates *r=wifi_rates_get(rate_profile);
    if(!addresses(own,ap) || !out || !r || sequence>4095 || !listen ||
       (capability&~0x431U) || !(capability&1) || !ssid || !ssid_length ||
       ssid_length>32 || !rsn || rsn_length<4 || rsn_length>257 ||
       rsn[0]!=48 || rsn[1]!=rsn_length-2 || !(capability&16))return 0;
    unsigned n=30+ssid_length+r->length+rsn_length;
    if(capacity<n || overlap(out,n,own,6) || overlap(out,n,ap,6) ||
       overlap(out,n,ssid,ssid_length) || overlap(out,n,rsn,rsn_length))return 0;
    header(out,n,0,own,ap,sequence);
    out[24]=(uint8_t)capability;out[25]=(uint8_t)(capability>>8);
    out[26]=(uint8_t)listen;out[27]=(uint8_t)(listen>>8);
    out[28]=0;out[29]=(uint8_t)ssid_length;
    unsigned pos=30;
    for(unsigned i=0;i<ssid_length;i++)out[pos++]=ssid[i];
    for(unsigned i=0;i<r->length;i++)out[pos++]=r->ies[i];
    for(unsigned i=0;i<rsn_length;i++)out[pos++]=rsn[i];
    return n;
}
int wifi_ais_assoc_response(const uint8_t *p,unsigned n,const uint8_t own[6],
    const uint8_t ap[6],unsigned rate_profile,struct wifi_ais_assoc *out){
    if(!out)return 0;
    *out=(struct wifi_ais_assoc){0};
    const struct wifi_rates *r=wifi_rates_get(rate_profile);
    if(!r || !response(p,n,0x10,own,ap))return 0;
    struct wifi_ais_assoc result={0};
    result.capability=(uint16_t)le16(p+24);result.status=(uint16_t)le16(p+26);
    unsigned seen=0,extended=0,mask=0,basic=0;
    static const uint8_t codes[]={2,4,11,22,0,0,12,18,24,36,48,72,96,108};
    for(unsigned pos=30;pos<n;){
        if(n-pos<2 || p[pos+1]>n-pos-2)return 0;
        unsigned id=p[pos],count=p[pos+1];
        if(id==1 || id==50){
            if(!count || (id==1 && (seen || count>8)) || (id==50 && extended))return 0;
            if(id==1)seen=1;else extended=1;
            for(unsigned i=0;i<count;i++){
                unsigned value=p[pos+2+i],bit=0;
                for(unsigned j=0;j<sizeof codes;j++)if(codes[j] && codes[j]==(value&127)){bit=1U<<j;break;}
                if(!result.status && (value&128) && !(bit&r->operational))return 0;
                mask|=bit;if(value&128)basic|=bit;
            }
        }
        pos+=2+count;
    }
    if(!result.status){
        unsigned aid=le16(p+28);
        if((result.capability&3)!=1 || !seen || !(mask&r->operational) ||
           (aid&0xc000)!=0xc000 || !(aid&0x3fff) || (aid&0x3fff)>2007)return 0;
        result.aid=(uint16_t)(aid&0x3fff);
        result.operational=(uint16_t)(mask&r->operational);result.basic=(uint16_t)basic;
    }
    result.ies=p+30;result.ie_length=n-30;*out=result;return 1;
}
