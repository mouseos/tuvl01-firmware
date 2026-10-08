/* Independent single-owner WPA2-PSK/CCMP adapter, no hardware success stubs. */
#include "session.h"
#include "utils/eloop.h"
struct tuvl_rsn_session {
    struct tuvl_rsn_driver driver;
    struct wpa_sm *sm;
    enum wpa_states state;
    u8 own[6],ap[6];
    int associated;
    int protection_failed;
};
static void auth_timeout(void *,void *);
static void state_set(void *ctx,enum wpa_states state)
{
    struct tuvl_rsn_session *s=ctx;
    s->state=s->protection_failed?WPA_DISCONNECTED:state;
}
static enum wpa_states state_get(void *ctx)
{ return ((struct tuvl_rsn_session *)ctx)->state; }
static void deauth(void *ctx,u16 reason)
{
    struct tuvl_rsn_session *s=ctx;
    eloop_cancel_timeout(auth_timeout,s,NULL);
    s->associated=0;s->state=WPA_DISCONNECTED;
    s->driver.disconnect(s->driver.ctx,reason);
}
static void reconnect(void *ctx) { deauth(ctx,2); }
static int protection(void *ctx,const u8 *addr,int type,int key_type)
{
    struct tuvl_rsn_session *s=ctx;
    if(!s->associated || s->protection_failed || !addr ||
       os_memcmp(addr,s->ap,6) || key_type!=MLME_SETPROTECTION_KEY_TYPE_PAIRWISE ||
       (type!=MLME_SETPROTECTION_PROTECT_TYPE_RX &&
        type!=MLME_SETPROTECTION_PROTECT_TYPE_RX_TX) ||
       s->driver.protection(s->driver.ctx,addr,type,key_type)!=0){
        s->protection_failed=1;deauth(ctx,2);return -1;
    }
    return 0;
}
static void *network(void *ctx) { return ctx; }
static int bssid(void *ctx,u8 *out)
{
    struct tuvl_rsn_session *s=ctx;
    if(!s->associated) return -1;
    os_memcpy(out,s->ap,6);return 0;
}
static void auth_timeout(void *ctx,void *user)
{ (void)user;deauth(ctx,15); }
static void cancel_timeout(void *ctx)
{ eloop_cancel_timeout(auth_timeout,ctx,NULL); }
/* The validated AP RSN IE was copied to sm at open. No beacon lookup stub. */
static int beacon(void *ctx)
{ return ((struct tuvl_rsn_session *)ctx)->associated ? 0 : -1; }
static u8 *alloc_eapol(void *ctx,u8 type,const void *data,u16 n,
                       size_t *total,void **data_pos)
{
    u8 *out;
    (void)ctx;
    if(!total || !data_pos || n>2044) return NULL;
    out=os_zalloc((size_t)n+4);
    if(!out) return NULL;
    out[0]=2;out[1]=type;out[2]=(u8)(n>>8);out[3]=(u8)n;
    if(data && n) os_memcpy(out+4,data,n);
    *total=(size_t)n+4;*data_pos=out+4;
    return out;
}
static int send_eapol(void *ctx,const u8 *dest,u16 proto,const u8 *data,size_t n)
{
    struct tuvl_rsn_session *s=ctx;
    u8 *frame;
    int res;
    if(!s->associated || !dest || !data || proto!=0x888e || n<4 || n>2048 ||
       os_memcmp(dest,s->ap,6) || ((size_t)data[2]<<8 | data[3])!=n-4) return -1;
    frame=os_malloc(n+14);if(!frame) return -1;
    os_memcpy(frame,dest,6);os_memcpy(frame+6,s->own,6);
    frame[12]=0x88;frame[13]=0x8e;os_memcpy(frame+14,data,n);
    res=s->driver.send(s->driver.ctx,frame,n+14);
    os_free(frame);return res==0 ? 0 : -1;
}
static int key(void *ctx,int link,enum wpa_alg alg,const u8 *addr,int index,
               int tx,const u8 *seq,size_t sn,const u8 *bytes,size_t n,
               enum key_flag flags)
{
    struct tuvl_rsn_session *s=ctx;
    if(!s->associated || link!=-1 || !addr || index<0 || index>3 ||
       (tx!=0 && tx!=1) || sn>6 || (sn && !seq)) return -1;
    if(alg==WPA_ALG_CCMP) {
        unsigned i,broadcast=1;
        for(i=0;i<6;i++) if(addr[i]!=0xff) broadcast=0;
        if(flags&KEY_FLAG_PAIRWISE) {
            if(index || os_memcmp(addr,s->ap,6)) return -1;
        } else if(!broadcast && os_memcmp(addr,s->ap,6)) return -1;
        if(!bytes || n!=16 || check_key_flag(flags) ||
           !(flags&(KEY_FLAG_PAIRWISE|KEY_FLAG_GROUP))) return -1;
    } else if(alg!=WPA_ALG_NONE || n || sn) return -1;
    return s->driver.key(s->driver.ctx,link,alg,addr,index,tx,seq,sn,bytes,n,flags)==0 ? 0 : -1;
}
static int unicast(const u8 *mac)
{
    unsigned v=0;size_t i;
    if(!mac || (mac[0]&1)) return 0;
    for(i=0;i<6;i++) v|=mac[i];
    return v!=0;
}
struct tuvl_rsn_session *tuvl_rsn_session_open(const struct tuvl_rsn_driver *drv,
    const u8 own[6],const u8 ap[6],const u8 *ssid,size_t ssid_n,const u8 pmk[32],
    const u8 *ie,size_t ie_n)
{
    struct tuvl_rsn_session *s;
    struct wpa_sm_ctx *ctx;
    struct wpa_ie_data parsed;
    struct rsn_supp_config cfg={0};
    if(!drv || !drv->send || !drv->key || !drv->disconnect || !drv->protection || !unicast(own) ||
       !unicast(ap) || !os_memcmp(own,ap,6) || !ssid || !ssid_n || ssid_n>32 ||
       !pmk || !ie || ie_n<2 || ie_n>257 || ie[0]!=48 || ie[1]+2u!=ie_n ||
       wpa_parse_wpa_ie(ie,ie_n,&parsed) || parsed.proto!=WPA_PROTO_RSN ||
       parsed.group_cipher!=WPA_CIPHER_CCMP || !(parsed.pairwise_cipher&WPA_CIPHER_CCMP) ||
       !(parsed.key_mgmt&WPA_KEY_MGMT_PSK) || (parsed.capabilities&WPA_CAPABILITY_MFPR))
        return NULL;
    s=os_zalloc(sizeof(*s));ctx=os_zalloc(sizeof(*ctx));
    if(!s || !ctx) { os_free(s);os_free(ctx);return NULL; }
    s->driver=*drv;s->state=WPA_DISCONNECTED;
    os_memcpy(s->own,own,6);os_memcpy(s->ap,ap,6);
    ctx->ctx=ctx->msg_ctx=s;ctx->set_state=state_set;ctx->get_state=state_get;
    ctx->deauthenticate=deauth;ctx->reconnect=reconnect;ctx->set_key=key;
    ctx->mlme_setprotection=protection;
    ctx->get_network_ctx=network;ctx->get_bssid=bssid;ctx->ether_send=send_eapol;
    ctx->get_beacon_ie=beacon;ctx->cancel_auth_timeout=cancel_timeout;
    ctx->alloc_eapol=alloc_eapol;
    s->sm=wpa_sm_init(ctx);
    if(!s->sm) { os_free(ctx);os_free(s);return NULL; }
    if(wpa_sm_set_param(s->sm,WPA_PARAM_PROTO,WPA_PROTO_RSN) ||
       wpa_sm_set_param(s->sm,WPA_PARAM_PAIRWISE,WPA_CIPHER_CCMP) ||
       wpa_sm_set_param(s->sm,WPA_PARAM_GROUP,WPA_CIPHER_CCMP) ||
       wpa_sm_set_param(s->sm,WPA_PARAM_KEY_MGMT,WPA_KEY_MGMT_PSK) ||
       wpa_sm_set_ap_rsn_ie(s->sm,ie,ie_n)) { tuvl_rsn_session_close(s);return NULL; }
    cfg.network_ctx=s;cfg.allowed_pairwise_cipher=WPA_CIPHER_CCMP;
    cfg.ssid=ssid;cfg.ssid_len=ssid_n;wpa_sm_set_config(s->sm,&cfg);
    wpa_sm_set_own_addr(s->sm,own);wpa_sm_set_pmk(s->sm,pmk,32,NULL,ap);
    return s;
}
int tuvl_rsn_session_assoc_ie(struct tuvl_rsn_session *s,u8 *ie,size_t *n)
{ return s && ie && n ? wpa_sm_set_assoc_wpa_ie_default(s->sm,ie,n) : -1; }
int tuvl_rsn_session_associated(struct tuvl_rsn_session *s)
{
    if(!s || s->associated || s->protection_failed ||
       eloop_register_timeout(30,0,auth_timeout,s,NULL)) return -1;
    s->associated=1;s->state=WPA_ASSOCIATED;wpa_sm_notify_assoc(s->sm,s->ap);return 0;
}
int tuvl_rsn_session_rx(struct tuvl_rsn_session *s,const u8 *frame,size_t n,
                         enum frame_encryption encryption)
{
    if(!s || !s->associated || !frame || n<18 || n>2062 ||
       os_memcmp(frame,s->own,6) || os_memcmp(frame+6,s->ap,6) ||
       frame[12]!=0x88 || frame[13]!=0x8e || (frame[14]!=1 && frame[14]!=2) ||
       frame[15]!=3 || ((size_t)frame[16]<<8 | frame[17])!=n-18 ||
       (encryption!=FRAME_NOT_ENCRYPTED && encryption!=FRAME_ENCRYPTED &&
        encryption!=FRAME_ENCRYPTION_UNKNOWN)) return -1;
    return wpa_sm_rx_eapol(s->sm,frame+6,frame+14,n-14,encryption);
}
enum wpa_states tuvl_rsn_session_state(const struct tuvl_rsn_session *s)
{ return s ? s->state : WPA_DISCONNECTED; }
void tuvl_rsn_session_close(struct tuvl_rsn_session *s)
{
    if(!s) return;
    if(s->associated) deauth(s,3);
    cancel_timeout(s);wpa_sm_deinit(s->sm);os_free(s);
}
