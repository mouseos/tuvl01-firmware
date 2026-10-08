/* SPDX-License-Identifier: MIT. Disjoint transaction timing; units are caller-supplied monotonic counts. */
#include "wifi_io_timing.h"
unsigned wifi_io_read_kind(unsigned address){
    if(address==0x10)return WIFI_IO_WHISR;
    if(address==0x20 || address==0x24)return WIFI_IO_WTSR;
    if(address==0x50)return WIFI_IO_RX_LENGTH;
    return WIFI_IO_OTHER_READ;
}
void wifi_io_start(struct wifi_io_timing *s,uint32_t now){
    *s=(struct wifi_io_timing){0};s->active=1;s->start=now;
    for(unsigned i=0;i<WIFI_IO_KINDS;i++)s->bin[i].minimum=UINT32_MAX;
}
void wifi_io_stop(struct wifi_io_timing *s,uint32_t now){
    if(s->active){s->duration=now-s->start;s->active=0;}
}
static void add(uint32_t *value,uint32_t amount,struct wifi_io_bin *b){
    if(amount>UINT32_MAX-*value){*value=UINT32_MAX;b->overflow=1;}else *value+=amount;
}
void wifi_io_record(struct wifi_io_timing *s,unsigned kind,unsigned bytes,uint32_t begin,uint32_t end,int failed){
    if(!s->active || kind>=WIFI_IO_KINDS)return;
    struct wifi_io_bin *b=&s->bin[kind];uint32_t elapsed=end-begin;
    add(&b->calls,1,b);add(&b->ticks,elapsed,b);add(&b->requested_bytes,bytes,b);
    if(failed)add(&b->failed,1,b);
    if(elapsed<b->minimum)b->minimum=elapsed;
    if(elapsed>b->maximum)b->maximum=elapsed;
}
