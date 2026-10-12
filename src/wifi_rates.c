/* SPDX-License-Identifier: MIT. Independent legacy/ERP rate serialization. */
#include "wifi_rates.h"
static const uint8_t mixed[]={1,8,0x82,0x84,0x8b,0x96,0x8c,0x12,0x98,0x24,50,4,0xb0,0x48,0x60,0x6c};
static const uint8_t erp[]={1,8,0x8c,0x12,0x98,0x24,0xb0,0x48,0x60,0x6c};
static const struct wifi_rates profiles[]={
    {0x3fcf,0x054f,3,mixed,sizeof mixed},
    {0x3fc0,0x0540,2,erp,sizeof erp}
};
unsigned wifi_rates_tim_aid1;
const struct wifi_rates *wifi_rates_get(unsigned profile){return profile<2?profiles+profile:0;}
unsigned wifi_rates_ies_channel(unsigned profile,unsigned kind,unsigned channel,uint8_t *out,unsigned capacity){
    const struct wifi_rates *r=wifi_rates_get(profile);
    if(!r || kind>2 || !out || channel<1 || channel>13)return 0;
    unsigned size=r->length+(kind==2?0:14)+(kind==1?6:0);
    if(capacity<size)return 0;
    static const uint8_t ssid[]={0,6,'T','U','V','L','0','1'};
    const uint8_t ds[]={3,1,(uint8_t)channel};
    /* Optional diagnostic: advertise buffered traffic for AID 1 (bitmap bit 1) so a station
     * that dozes between frames is told to stay awake. Default stays an empty bitmap. */
    uint8_t tim[]={5,4,0,1,0,(uint8_t)(wifi_rates_tim_aid1?2:0)};
    static const uint8_t erp_info[]={42,1,0};
    unsigned n=0;
    if(kind!=2)for(unsigned i=0;i<sizeof ssid;i++)out[n++]=ssid[i];
    for(unsigned i=0;i<r->length;i++)out[n++]=r->ies[i];
    if(kind!=2){
        for(unsigned i=0;i<sizeof ds;i++)out[n++]=ds[i];
        if(kind==1)for(unsigned i=0;i<sizeof tim;i++)out[n++]=tim[i];
        for(unsigned i=0;i<sizeof erp_info;i++)out[n++]=erp_info[i];
    }
    return n;
}
unsigned wifi_rates_ies(unsigned profile,unsigned kind,uint8_t *out,unsigned capacity){
    return wifi_rates_ies_channel(profile,kind,1,out,capacity);
}
