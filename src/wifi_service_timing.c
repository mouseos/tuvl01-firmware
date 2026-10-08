/* SPDX-License-Identifier: MIT */
#include "wifi_service_timing.h"
void wifi_service_start(struct wifi_service_timing *s,uint32_t now){
    *s=(struct wifi_service_timing){0};
    wifi_io_start(&s->phases,now);wifi_io_start(&s->loops,now);
    s->open=1;s->last=s->loop_begin=now;
}
void wifi_service_stop(struct wifi_service_timing *s,uint32_t now){
    if(!s->phases.active)return;
    if(s->open)wifi_io_record(&s->phases,s->stage,0,s->last,now,0);
    wifi_io_stop(&s->phases,now);wifi_io_stop(&s->loops,now);s->open=0;
}
void wifi_service_mark(struct wifi_service_timing *s,unsigned mark,uint32_t now,uint32_t stalls,uint32_t tx){
    if(!s->phases.active)return;
    if(mark==0 && !s->open){s->open=1;s->stage=0;s->last=s->loop_begin=now;return;}
    if(!s->open || mark>5 || mark!=s->stage+1){s->invalid=1;return;}
    wifi_io_record(&s->phases,s->stage,0,s->last,now,0);s->stage=mark;s->last=now;
    if(mark==2){s->stalls_begin=stalls;s->tx_begin=tx;}
    if(mark==3){s->stalled=stalls-s->stalls_begin;s->sent=tx-s->tx_begin;}
    if(mark==5){
        unsigned kind=s->sent?(s->stalled?2:1):(s->stalled?0:3);
        wifi_io_record(&s->loops,kind,s->sent,s->loop_begin,now,0);s->open=0;
    }
}
