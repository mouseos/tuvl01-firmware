/* SPDX-License-Identifier: MIT. Single SDIO owner, copied public BSS data. */
#include "wifi_scan_cache.h"
void wifi_scan_cache_begin(struct wifi_scan_cache *c){
    if(c){c->count=c->next=c->complete=0;c->active=1;}
}
void wifi_scan_cache_finish(struct wifi_scan_cache *c,unsigned success){
    if(c){c->active=0;c->complete=success!=0;if(!success)c->count=c->next=0;}
}
static int same(const uint8_t *a,const uint8_t *b){
    for(unsigned i=0;i<6;i++)if(a[i]!=b[i])return 0;
    return 1;
}
void wifi_scan_cache_observe(struct wifi_scan_cache *c,const struct wifi_ais_beacon *b,
                            uint32_t tick,unsigned profile,uint8_t rcpi){
    if(!c || !b || !c->active || b->channel<1 || b->channel>13 ||
       b->rx_channel!=b->channel || (b->ap[0]&1))return;
    unsigned nonzero=0;for(unsigned i=0;i<6;i++)nonzero|=b->ap[i];
    if(!nonzero)return;
    unsigned slot;
    for(slot=0;slot<c->count;slot++)if(same(c->entries[slot].beacon.ap,b->ap))break;
    if(slot==c->count){
        if(c->count<WIFI_SCAN_CACHE_CAPACITY)c->count++;
        else {slot=c->next;c->next=(c->next+1)%WIFI_SCAN_CACHE_CAPACITY;}
    }
    c->entries[slot].beacon=*b;c->entries[slot].seen=tick;
    c->entries[slot].profile=profile;c->entries[slot].rcpi=rcpi;
}
int wifi_scan_cache_select(const struct wifi_scan_cache *c,uint32_t now,uint32_t age,
                          unsigned profile,const uint8_t *ap,unsigned channel,
                          struct wifi_ais_beacon *out,uint8_t *rcpi){
    if(!c || !ap || !out || !rcpi || c->active || !c->complete || !age ||
       age>=0x80000000U || channel<1 || channel>13)return 0;
    for(unsigned i=0;i<c->count;i++){
        const struct wifi_scan_cache_entry *e=&c->entries[i];
        if(e->profile==profile && e->beacon.channel==channel &&
           e->beacon.rx_channel==channel && same(e->beacon.ap,ap) &&
           (uint32_t)(now-e->seen)<=age){
            *out=e->beacon;*rcpi=e->rcpi;return 1;
        }
    }
    return 0;
}
