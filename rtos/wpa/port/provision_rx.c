/* SPDX-License-Identifier: MIT */
#include "provision_rx.h"
static void wipe(void *p,size_t n)
{ volatile u8 *v=p;while(n--)*v++=0; }
static enum tuvl_provision_rx_state finish(struct tuvl_provision_rx *r,
    enum tuvl_provision_rx_state state)
{
    wipe(r->packet,sizeof r->packet);r->used=0;r->state=state;return state;
}
int tuvl_provision_rx_reset(struct tuvl_provision_rx *r)
{
    if(!r || r->state==TUVL_RX_APPLYING)return -1;
    wipe(r,sizeof *r);return 0;
}
int tuvl_provision_rx_begin(struct tuvl_provision_rx *r,struct tuvl_rsn_owner *o,u32 now)
{
    if(!r || !o || r->state!=TUVL_RX_IDLE || !o->prepared || o->session || o->busy)
        return -1;
    wipe(r->packet,sizeof r->packet);r->used=0;r->owner=o;r->started=now;
    r->state=TUVL_RX_RECEIVING;return 0;
}
enum tuvl_provision_rx_state tuvl_provision_rx_poll(struct tuvl_provision_rx *r,u32 now)
{
    if(!r)return TUVL_RX_REJECTED;
    if(r->state==TUVL_RX_RECEIVING && (u32)(now-r->started)>=TUVL_PROVISION_TIMEOUT_MS)
        return finish(r,TUVL_RX_TIMEOUT);
    return r->state;
}
enum tuvl_provision_rx_state tuvl_provision_rx_feed(struct tuvl_provision_rx *r,
    const u8 *p,size_t n,u32 now)
{
    enum tuvl_provision_rx_state state=tuvl_provision_rx_poll(r,now);
    if(state!=TUVL_RX_RECEIVING)return state;
    if((n && !p) || r->used>sizeof r->packet || n>sizeof r->packet-r->used)
        return finish(r,TUVL_RX_REJECTED);
    for(size_t i=0;i<n;i++)r->packet[r->used+i]=p[i];
    r->used+=n;
    if(r->used!=sizeof r->packet)return r->state;
    r->state=TUVL_RX_APPLYING;
    int result=tuvl_rsn_owner_provision(r->owner,r->packet,sizeof r->packet);
    return finish(r,result?TUVL_RX_REJECTED:TUVL_RX_ACCEPTED);
}
