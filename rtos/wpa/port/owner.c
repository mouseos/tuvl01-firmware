/* SPDX-License-Identifier: MIT */
#include "owner.h"
#include "provision.h"
#include "entropy.h"
#include "timer.h"
#include "mt5931-eapol.h"
static void wipe(void *p,size_t n)
{ volatile u8 *v=p;while(n--)*v++=0; }
static int unicast(const u8 *p)
{
    unsigned v=0;for(unsigned i=0;i<6;i++)v|=p[i];
    return v && !(p[0]&1);
}
int tuvl_rsn_owner_prepare(struct tuvl_rsn_owner *o,const struct tuvl_rsn_target *t,
    const struct tuvl_rsn_driver *driver)
{
    if(!o || !t || !driver || o->session || o->busy || !driver->send ||
       !driver->key || !driver->disconnect || !driver->protection ||
       !unicast(t->own) || !unicast(t->ap) || !os_memcmp(t->own,t->ap,6) ||
       !t->ssid_length || t->ssid_length>32 || t->rsn_length<2 ||
       t->rsn_length>257 || t->rsn[0]!=48 || t->rsn[1]+2u!=t->rsn_length ||
       !t->channel || t->channel>13)return -1;
    /* No destructive reset of a live session or another owner's pool. */
    o->target=*t;o->driver=*driver;o->prepared=1;return 0;
}
static int apply(void *ctx,const struct tuvl_provision *c)
{
    struct tuvl_rsn_owner *o=ctx;
    if(!o->prepared || o->session || c->channel!=o->target.channel ||
       c->ssid_length!=o->target.ssid_length || os_memcmp(c->ap,o->target.ap,6) ||
       os_memcmp(c->ssid,o->target.ssid,c->ssid_length) ||
       tuvl_rsn_entropy_remaining())return -1;
    if(tuvl_rsn_entropy_supply(c->entropy,sizeof c->entropy))return -1;
    o->entropy_owned=1;
    o->session=tuvl_rsn_session_open(&o->driver,o->target.own,o->target.ap,
        o->target.ssid,o->target.ssid_length,c->pmk,o->target.rsn,o->target.rsn_length);
    if(!o->session){tuvl_rsn_entropy_clear();o->entropy_owned=0;return -1;}
    return 0;
}
int tuvl_rsn_owner_provision(struct tuvl_rsn_owner *o,u8 *p,size_t n)
{
    int result;
    if(!o || o->busy)return tuvl_provision_consume(p,n,NULL,NULL);
    o->busy=1;result=tuvl_provision_consume(p,n,apply,o);o->busy=0;return result;
}
int tuvl_rsn_owner_assoc_ie(struct tuvl_rsn_owner *o,u8 *p,size_t *n)
{
    int result;if(!o || !o->session || o->busy || o->associated)return -1;
    o->busy=1;result=tuvl_rsn_session_assoc_ie(o->session,p,n);o->busy=0;return result;
}
int tuvl_rsn_owner_associated(struct tuvl_rsn_owner *o)
{
    int result;if(!o || !o->session || o->busy || o->associated)return -1;
    o->busy=1;result=tuvl_rsn_session_associated(o->session);
    if(!result)o->associated=1;
    o->busy=0;return result;
}
enum wpa_states tuvl_rsn_owner_state(const struct tuvl_rsn_owner *o)
{ return o?tuvl_rsn_session_state(o->session):WPA_DISCONNECTED; }
void tuvl_rsn_owner_close(struct tuvl_rsn_owner *o)
{
    struct tuvl_rsn_session *s;if(!o || o->busy)return;
    o->busy=1;s=o->session;o->session=NULL;
    tuvl_rsn_session_close(s);
    if(o->entropy_owned)tuvl_rsn_entropy_clear();
    wipe(o,sizeof *o);
}
static void reap(struct tuvl_rsn_owner *o)
{
    if(o->associated && tuvl_rsn_owner_state(o)==WPA_DISCONNECTED)
        tuvl_rsn_owner_close(o);
}
int tuvl_rsn_owner_rx(struct tuvl_rsn_owner *o,const u8 *p,size_t n)
{
    struct tuvl_eapol_rx view;int result;
    if(!o || o->busy || !o->session || !o->associated ||
       !tuvl_mt5931_eapol_rx(p,n,o->target.own,o->target.ap,&view))return -1;
    o->busy=1;
    result=tuvl_rsn_session_rx(o->session,view.frame,view.length,
                             (enum frame_encryption)view.encryption);
    o->busy=0;reap(o);return result;
}
int tuvl_rsn_owner_poll(struct tuvl_rsn_owner *o,u32 now)
{
    int result;if(!o || o->busy || !o->session)return -1;
    o->busy=1;result=tuvl_rsn_poll(now);o->busy=0;reap(o);return result;
}
