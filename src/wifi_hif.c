/* SPDX-License-Identifier: MIT. Independent decoding of MT5931 HIF RX fields.
 * Byte order and format fields checked against the public hif_rx.h/nic_rx.c.
 * Event and raw 802.11 packets must not reach the Ethernet/EAPOL backend. */
#include "wifi_hif.h"
int wifi_hif_ethernet(const uint8_t *p,unsigned n,unsigned network,
                      struct wifi_ethernet_view *v){
    if(!v)return 0;
    v->frame=0;v->length=0;v->ethertype=0;v->station=v->rcpi=0;
    if(!p || n<12 || network>15 ||
       (p[0]|((unsigned)p[1]<<8))!=n || (p[2]&3) ||
       (p[5]&1) || (p[5]>>4)!=network)return 0;
    unsigned offset=12+(p[4]&3);
    if(n<offset+14 || n-offset>1514)return 0;
    v->frame=p+offset;v->length=n-offset;
    v->ethertype=((uint16_t)p[offset+12]<<8)|p[offset+13];
    v->station=p[8];v->rcpi=p[9];
    return 1;
}
