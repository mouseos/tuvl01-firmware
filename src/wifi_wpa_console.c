/* SPDX-License-Identifier: MIT. Volatile provisioning and diagnostic AIS trial. */
#include "wifi_wpa_console.h"
#include "wifi_ais_beacon.h"
#include "board.h"
#include "sdio.h"
#include "owner.h"
#include "provision_rx.h"
#include "diagnostic.h"
#include "timer.h"
#include "eapol_queue.h"
#include "mt5931-eapol.h"
#include "supplicant-send.h"
#include "supplicant-key.h"
#include "key-ledger.h"
static struct tuvl_rsn_owner owner;
static struct tuvl_provision_rx receiver;
static struct tuvl_eapol_queue rx_queue;
static struct tuvl_send_transport transport;
static struct tuvl_key_transport key_transport;
static struct tuvl_key_ledger key_ledger;
static unsigned cleanup_unresolved;
static unsigned phase,used,sync_pos,clock_initialized;
static unsigned radio_pending,leave_pending;
static uint32_t started;
static uint8_t target[7];
static const char sync_marker[]="TUVL-WPA-RESYNC\n";
/* HIF send/RX and keys require an associated owner and activated AIS peer.
 * WPA2 protection remains unavailable. */
static int radio_submit(void *ctx,unsigned port,unsigned tc,const uint8_t *p,size_t n)
{ (void)ctx;return sdio_wifi_wpa_eapol_submit(port,tc,p,(unsigned)n); }
static int radio_send(void *ctx,const u8 *p,size_t n)
{
    (void)ctx;
    if(!owner.associated)return -1;
    os_memcpy(transport.own,owner.target.own,6);os_memcpy(transport.ap,owner.target.ap,6);
    transport.submit=radio_submit;
    return tuvl_supplicant_send(&transport,p,n);
}
static int radio_key_submit(void *ctx,const u8 *body,size_t n)
{(void)ctx;return sdio_wifi_wpa_key_submit(body,(unsigned)n);}
static int tracked_key_submit(void *ctx,const u8 *body,size_t n)
{return tuvl_key_ledger_submit(&key_ledger,radio_key_submit,ctx,body,n);}
static int radio_key(void *ctx,int link,enum wpa_alg alg,const u8 *addr,int idx,int tx,
    const u8 *seq,size_t sn,const u8 *key,size_t kn,enum key_flag flags)
{
    (void)ctx;if(!owner.associated)return -1;
    os_memcpy(key_transport.ap,owner.target.ap,6);key_transport.submit=tracked_key_submit;
    return tuvl_supplicant_key(&key_transport,link,alg,addr,idx,tx,seq,sn,key,kn,flags);
}
static int unavailable_protection(void *ctx,const u8 *addr,int type,int key_type)
{ (void)ctx;(void)addr;(void)type;(void)key_type;return -1; }
static void disconnected(void *ctx,u16 reason){(void)ctx;(void)reason;leave_pending=1;}
static void panic_stop(void *ctx){(void)ctx;fault();}
static void latch(const char *status)
{
    uart_puts(status);phase=3;sync_pos=0;used=0;
    for(unsigned i=0;i<sizeof target;i++)target[i]=0;
}
void wifi_wpa_uart_begin(uint32_t now)
{
    if(cleanup_unresolved || key_ledger.failed){uart_puts("WPA cleanup refused-unresolved\n");return;}
    if(phase || owner.session){uart_puts("WPA provisioning refused-active\n");return;}
    if(!clock_initialized){
        if(tuvl_rsn_clock_start(now)){uart_puts("WPA provisioning clock-failed\n");return;}
        clock_initialized=1;
    }
    tuvl_rsn_set_panic(panic_stop,NULL);
    tuvl_rsn_set_log(NULL,NULL,3); /* Never forward credential-bearing debug. */
    phase=1;started=now;used=sync_pos=0;
    uart_puts("WPA target bytes=7 version=1\n");
}
void wifi_wpa_uart_close(void)
{
    /* Delete while the AIS station/network still exists. Failed transfers
     * may have reached the radio: cache failure and never issue them again. */
    if(!cleanup_unresolved){
        if(tuvl_key_ledger_close(&key_ledger,radio_key_submit,NULL))cleanup_unresolved=1;
        else if(sdio_wifi_wpa_leave())cleanup_unresolved=2;
    }
    tuvl_rsn_owner_close(&owner);tuvl_provision_rx_reset(&receiver);
    tuvl_eapol_queue_clear(&rx_queue);
    radio_pending=leave_pending=0;
    if(cleanup_unresolved==1)uart_puts("WPA key cleanup unresolved\n");
    if(cleanup_unresolved==2)uart_puts("WPA AIS cleanup unresolved\n");
    uart_puts("WPA volatile session closed\n");
}
void wifi_wpa_uart_info(void){uart_puts("WPA protocol=1 provisioning-only\n");}
int wifi_wpa_radio_validate(const uint8_t *own,const struct wifi_ais_beacon *b)
{
    if(!own || !b || !owner.session || owner.associated || owner.busy ||
       b->ssid_length!=owner.target.ssid_length || b->rsn_length!=owner.target.rsn_length ||
       b->channel!=owner.target.channel || b->rx_channel!=b->channel ||
       os_memcmp(own,owner.target.own,6) || os_memcmp(b->ap,owner.target.ap,6) ||
       os_memcmp(b->ssid,owner.target.ssid,b->ssid_length) ||
       os_memcmp(b->rsn,owner.target.rsn,b->rsn_length))return -1;
    return 0;
}
unsigned wifi_wpa_radio_assoc_ie(uint8_t *p,unsigned capacity)
{
    size_t n=capacity;
    if(tuvl_rsn_owner_assoc_ie(&owner,p,&n) || n>capacity)return 0;
    return (unsigned)n;
}
void wifi_wpa_uart_join(void)
{
    if(cleanup_unresolved || key_ledger.failed || phase || !owner.session || owner.associated){
        uart_puts("WPA association refused\n");return;
    }
    uint8_t selected[7];selected[0]=(uint8_t)owner.target.channel;
    os_memcpy(selected+1,owner.target.ap,6);
    radio_pending=1;
    int result=sdio_wifi_wpa_join(selected);
    radio_pending=0;
    /* Synchronize elapsed time after the blocking radio join, before
     * starting the RSN auth deadline. Never count JOIN wait as WPA time. */
    if(result || rx_queue.failed || tuvl_rsn_poll(sdio_wifi_milliseconds())<0 ||
       tuvl_rsn_owner_associated(&owner)){
        wifi_wpa_uart_close();uart_puts("WPA association failed\n");return;
    }
    uart_puts("WPA association ready; protection=unimplemented\n");
}
void wifi_wpa_radio_rx(const uint8_t *p,unsigned n)
{
    struct tuvl_eapol_rx view;
    if(owner.session && (owner.associated || radio_pending) &&
       tuvl_mt5931_eapol_rx(p,n,owner.target.own,owner.target.ap,&view))
        (void)tuvl_eapol_queue_push(&rx_queue,p,n);
}
static void radio_dispatch(void)
{
    if(rx_queue.failed){
        wifi_wpa_uart_close();uart_puts("WPA radio queue-failed\n");return;
    }
    /* One copied packet per outer service call. Hardware callbacks may add
     * more packets during command waits, but cannot reenter RSN processing. */
    size_t n;const uint8_t *p=tuvl_eapol_queue_front(&rx_queue,&n);
    if(p && owner.associated){
        (void)tuvl_rsn_owner_rx(&owner,p,n);tuvl_eapol_queue_pop(&rx_queue);
        if(!owner.session)tuvl_eapol_queue_clear(&rx_queue);
    }
}
/* Keep target selection locals out of the RSN/timer service stack. This
 * boundary must survive optimization; both paths run in the same task. */
static void __attribute__((noinline)) provision_target(uint32_t now)
{
    struct wifi_ais_beacon b;u8 own[6];struct tuvl_rsn_target selected={0};
    struct tuvl_rsn_driver d={NULL,radio_send,radio_key,disconnected,unavailable_protection};
    if(sdio_wifi_wpa_select(target[0],target+1,own,&b) ||
       !b.ssid_length || b.ssid_length>sizeof b.ssid ||
       b.rsn_length<2 || b.rsn_length>sizeof b.rsn ||
       b.channel!=target[0] || b.rx_channel!=b.channel ||
       os_memcmp(b.ap,target+1,6)){
        latch("WPA provisioning target-refused\n");return;
    }
    os_memcpy(selected.own,own,6);os_memcpy(selected.ap,b.ap,6);
    os_memcpy(selected.ssid,b.ssid,b.ssid_length);selected.ssid_length=b.ssid_length;
    os_memcpy(selected.rsn,b.rsn,b.rsn_length);selected.rsn_length=b.rsn_length;selected.channel=b.channel;
    if(tuvl_rsn_owner_prepare(&owner,&selected,&d) ||
       tuvl_provision_rx_begin(&receiver,&owner,now)){
        latch("WPA provisioning target-refused\n");return;
    }
    for(unsigned i=0;i<sizeof target;i++)target[i]=0;
    phase=2;uart_puts("WPA credentials bytes=148 version=1\n");
}
int wifi_wpa_uart_intercept(int byte,uint32_t now)
{
    radio_dispatch();
    if(clock_initialized)tuvl_rsn_poll(now);
    if(leave_pending)wifi_wpa_uart_close(); /* Outside RSN/timer callbacks. */
    if(owner.associated && byte>=0 && byte!='i' && byte!=3){
        uart_puts("WPA command refused-active\n");return 1;
    }
    if(!phase)return 0;
    if(phase==3){
        if(byte==0){sync_pos=0;uart_puts("WPA waiting-for-resync version=1\n");return 1;}
        if(byte>=0){
            if((unsigned char)byte==(unsigned char)sync_marker[sync_pos])sync_pos++;
            else sync_pos=(unsigned char)byte==(unsigned char)sync_marker[0]?1:0;
            if(sync_pos==sizeof sync_marker-1){
                tuvl_provision_rx_reset(&receiver);phase=sync_pos=0;
                uart_puts("WPA UART resynchronized\n");
            }
        }
        return 1;
    }
    if(phase==1){
        if((uint32_t)(now-started)>=3000){latch("WPA provisioning target-timeout\n");return 1;}
        if(byte<0)return 1;
        target[used++]=(uint8_t)byte;
        if(used==sizeof target){
            provision_target(now);
        }
        return 1;
    }
    u8 value=(u8)byte;
    enum tuvl_provision_rx_state state=byte<0?tuvl_provision_rx_poll(&receiver,now):
        tuvl_provision_rx_feed(&receiver,&value,1,now);
    value=0;
    if(state==TUVL_RX_ACCEPTED)latch("WPA provisioning accepted; association=unimplemented\n");
    else if(state==TUVL_RX_TIMEOUT)latch("WPA provisioning input-timeout\n");
    else if(state==TUVL_RX_REJECTED)latch("WPA provisioning rejected\n");
    return 1;
}
