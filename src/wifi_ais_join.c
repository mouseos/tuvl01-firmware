/* SPDX-License-Identifier: MIT. Independent legacy AIS join bookkeeping. */
#include "wifi_ais_join.h"
#include "wifi_ais_bss.h"
#include "wifi_station.h"
#include "wifi_rates.h"
static int same(const uint8_t *a,const uint8_t *b,unsigned n){
    for(unsigned i=0;i<n;i++)if(a[i]!=b[i])return 0;
    return 1;
}
int wifi_ais_join_prepare(struct wifi_ais_join *j,const uint8_t own[6],
    const struct wifi_ais_beacon *b,const struct wifi_ais_assoc *a,unsigned profile,unsigned rcpi){
    if(!j)return 0;
    *j=(struct wifi_ais_join){0};
    if(!own || !b || !a || !wifi_rates_get(profile) || rcpi>255 ||
       a->status || !a->aid || a->aid>2007 || (a->capability&3)!=1 ||
       !(a->capability&16) || !b->interval || !b->ssid_length || b->ssid_length>32 ||
       b->channel!=b->rx_channel)return 0;
    struct wifi_ais_join r={0};r.selected=*b;
    for(unsigned i=0;i<6;i++)r.own[i]=own[i];
    r.rcpi=(uint8_t)rcpi;r.profile=(uint8_t)profile;r.aid=a->aid;
    r.capability=a->capability;r.operational=a->operational;r.basic=a->basic;
    uint8_t packet[88];
    if(!wifi_ais_join_bss(&r,packet,sizeof packet) ||
       !wifi_ais_join_station(&r,packet,sizeof packet))return 0;
    *j=r;return 1;
}
unsigned wifi_ais_join_bss(const struct wifi_ais_join *j,uint8_t *out,unsigned n){
    if(!j || !j->aid)return 0;
    struct wifi_ais_bss_config c={0};
    for(unsigned i=0;i<6;i++){c.own[i]=j->own[i];c.ap[i]=j->selected.ap[i];}
    c.ssid_length=j->selected.ssid_length;
    for(unsigned i=0;i<c.ssid_length && i<32;i++)c.ssid[i]=j->selected.ssid[i];
    /* AIS uses the configured CCMP-enabled enum, not the key-absent
     * result returned by a host query. No key is installed here. */
    c.channel=j->selected.channel;c.connected=1;c.enc_status=6;
    c.operational=j->operational;c.basic=j->basic;c.phy=(c.operational&15)?3:2;
    c.short_preamble=!!(j->capability&0x20) && j->selected.short_preamble;
    c.short_slot=!!(j->capability&0x400);c.erp_protection=j->selected.erp_protection;
    return wifi_ais_bss_pack(out,n,&c);
}
unsigned wifi_ais_join_station(const struct wifi_ais_join *j,uint8_t *out,unsigned n){
    if(!j || !j->aid)return 0;
    struct wifi_station_config c={0};
    for(unsigned i=0;i<6;i++)c.peer[i]=j->selected.ap[i];
    c.aid=j->aid;c.listen=1;c.operational=j->operational;c.basic=j->basic;
    c.phy=(c.operational&15)?3:2;c.state=3;c.rcpi=j->rcpi;
    return wifi_station_pack(out,n,&c);
}
void wifi_ais_join_watch(struct wifi_ais_join *j){
    if(j && j->aid){j->watch=1;j->activated=j->beacon_seen=0;}
}
void wifi_ais_join_observe(struct wifi_ais_join *j,const uint8_t *p,unsigned n){
    if(!j || !j->watch || !p || n<8 || (p[0]|((unsigned)p[1]<<8))!=n)return;
    unsigned type=p[2]&3;
    if(type==1 && n>=20 && p[4]==0x13 && !p[14] && !p[15] &&
       !p[16] && p[17]==1 && same(p+8,j->selected.ap,6)){
        j->activated=1;return;
    }
    /* Activation and the first matching live beacon can arrive in either
     * order. Retain both observations; PM still requires both below. */
    if(type!=3 || n<12 || p[5]!=1 || (p[7]&0x80))return;
    unsigned off=12+(p[4]&3);
    if(n<off)return;
    struct wifi_ais_beacon b;
    if(!wifi_ais_beacon_parse(p+off,n-off,p[10],j->selected.ap,j->profile,&b) ||
       b.channel!=j->selected.channel || b.rx_channel!=j->selected.channel ||
       !b.tim_present || !b.dtim_period || b.interval!=j->selected.interval ||
       b.ssid_length!=j->selected.ssid_length ||
       !same(b.ssid,j->selected.ssid,b.ssid_length) ||
       b.rsn_length!=j->selected.rsn_length ||
       !same(b.rsn,j->selected.rsn,b.rsn_length))return;
    j->connected_beacon=b;j->beacon_seen=1;
}
unsigned wifi_ais_join_pm(const struct wifi_ais_join *j,uint8_t *out,unsigned n){
    if(!j || !out || n<20 || !j->watch || !j->activated || !j->beacon_seen ||
       !j->aid || j->aid>2007 || !j->connected_beacon.dtim_period ||
       !j->connected_beacon.interval)return 0;
    uint8_t p[20]={0};p[9]=j->connected_beacon.dtim_period;
    p[10]=(uint8_t)j->aid;p[11]=(uint8_t)(j->aid>>8);
    p[12]=(uint8_t)j->connected_beacon.interval;p[13]=(uint8_t)(j->connected_beacon.interval>>8);
    for(unsigned i=0;i<20;i++)out[i]=p[i];
    return 20;
}
