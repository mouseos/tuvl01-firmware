/* SPDX-License-Identifier: MIT */
#include "wifi_tx_timing.h"
void wifi_tx_timing_reset(struct wifi_tx_timing *s){
    uint8_t *p=(uint8_t *)s;for(unsigned n=0;n<sizeof *s;n++)p[n]=0;
}
static void record(uint32_t delta,uint32_t *count,uint32_t *sum,uint32_t *minimum,uint32_t *maximum){
    if(!*count || delta<*minimum)*minimum=delta;
    if(!*count || delta>*maximum)*maximum=delta;
    ++*count;*sum+=delta;
}
void wifi_tx_timing_other(struct wifi_tx_timing *s){
    if(s->active){s->active=0;++s->excluded;}
}
void wifi_tx_timing_begin(struct wifi_tx_timing *s,unsigned packets,uint32_t now){
    wifi_tx_timing_other(s);
    if(!packets || packets>7)return;
    s->packets=packets;s->start=now;s->active=1;
    s->polls=0;s->last_poll=now;s->poll_gap=0;
}
void wifi_tx_timing_poll(struct wifi_tx_timing *s,uint32_t now){
    if(!s->active)return;
    uint32_t gap=now-s->last_poll;
    if(gap>s->poll_gap)s->poll_gap=gap;
    ++s->polls;s->last_poll=now;
}
void wifi_tx_timing_written(struct wifi_tx_timing *s,uint32_t now){
    if(!s->active)return;
    struct wifi_tx_time_bin *b=s->bin+s->packets-1;
    ++b->writes;b->write_sum+=now-s->start;
}
void wifi_tx_timing_credit(struct wifi_tx_timing *s,unsigned free,uint32_t now){
    if(!s->active || free!=14)return;
    struct wifi_tx_time_bin *b=s->bin+s->packets-1;
    if(!b->credits || s->polls<b->poll_min)b->poll_min=s->polls;
    if(s->polls>b->poll_max)b->poll_max=s->polls;
    b->poll_sum+=s->polls;
    uint32_t tail=now-s->last_poll;
    if(tail>s->poll_gap)s->poll_gap=tail;
    if(s->poll_gap>b->poll_gap_max)b->poll_gap_max=s->poll_gap;
    record(now-s->start,&b->credits,&b->credit_sum,&b->credit_min,&b->credit_max);s->active=0;
}
void wifi_tx_timing_sample(struct wifi_tx_timing *s,uint8_t tag,unsigned packets,uint32_t now){
    if(!(tag&128) || !packets || packets>7)return;
    unsigned slot=tag&127;s->sample_packets[slot]=packets;s->sample_start[slot]=now;
}
void wifi_tx_timing_done(struct wifi_tx_timing *s,uint8_t tag,uint8_t status,uint32_t now){
    if(!(tag&128))return;
    unsigned slot=tag&127,packets=s->sample_packets[slot];if(!packets)return;
    s->sample_packets[slot]=0;
    struct wifi_tx_time_bin *b=s->bin+packets-1;
    record(now-s->sample_start[slot],&b->done,&b->done_sum,&b->done_min,&b->done_max);
    if(status)++b->done_failed;
}
void wifi_tx_timing_cancel(struct wifi_tx_timing *s,uint8_t tag){
    if(tag&128)s->sample_packets[tag&127]=0;
    wifi_tx_timing_other(s);
}
