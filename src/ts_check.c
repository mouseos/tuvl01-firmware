/* SPDX-License-Identifier: MIT */
#include "ts_check.h"
void ts_check_reset(struct ts_check *s){
    s->packets=s->sync=s->tei=s->adaptation=s->comparisons=s->cc_jumps=s->cc_repeats=0;
    for(unsigned n=0;n<8192;n++)s->last[n]=255;
}
void ts_check_packet(struct ts_check *s,const uint8_t p[188]){
    s->packets++;
    if(p[0]!=0x47){s->sync++;return;}
    unsigned pid=((p[1]&31U)<<8)|p[2],afc=(p[3]>>4)&3U,cc=p[3]&15U;
    if(p[1]&128U)s->tei++;
    if(!afc || ((afc&2U) && (p[4]>183 || (afc==3 && p[4]>182)))){
        s->adaptation++;return;
    }
    if((afc&2U) && p[4] && (p[5]&128U))s->last[pid]=255;
    if(!(afc&1U) || pid==8191)return;
    if(s->last[pid]!=255){
        s->comparisons++;
        if(cc==s->last[pid])s->cc_repeats++;
        else if(cc!=((s->last[pid]+1U)&15U))s->cc_jumps++;
    }
    s->last[pid]=cc;
}
