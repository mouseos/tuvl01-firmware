/* SPDX-License-Identifier: MIT */
#include "wifi_power_events.h"
void wifi_power_events_reset(struct wifi_power_events *state){
    if(state)*state=(struct wifi_power_events){0};
}
int wifi_power_events_observe(struct wifi_power_events *state,
    const uint8_t *packet,unsigned length,unsigned network,unsigned station){
    if(!state)return -1;
    if(!packet || length<8){state->invalid++;return -1;}
    unsigned id=packet[4];
    if(id!=0x19 && id!=0x1a && id!=0x1e)return 0;
    if(length!=12 || (packet[0]|((unsigned)packet[1]<<8))!=length ||
       packet[2]!=1 || packet[3]!=0 || network>255 || station>255){
        state->invalid++;return -1;
    }
    if(packet[8]!=(id==0x19?network:station)){state->foreign++;return 2;}
    /* Preserve raw flags/modes; unknown values do not become known state. */
    if(id==0x19){
        state->bss_events++;state->absent=packet[9];state->bss_quota=packet[10];
        state->known=(state->known&~1U)|(packet[9]<=1?1U:0U);
    }else if(id==0x1a){
        state->ps_events++;state->in_ps=packet[9];state->ps_mode=packet[10];
        state->ps_quota=packet[11];
        state->known=(state->known&~2U)|(packet[9]<=1?2U:0U);
    }else{
        state->quota_events++;state->quota_mode=packet[9];state->quota=packet[10];
        state->known|=4;
    }
    return 1;
}
