/* SPDX-License-Identifier: MIT. Independent MT5931 AIS BSS wire format. */
#include "wifi_ais_bss.h"
unsigned wifi_ais_bss_pack(uint8_t *out,unsigned capacity,const struct wifi_ais_bss_config *c){
    if(!out || !c || capacity<88 || !c->ssid_length || c->ssid_length>32 ||
       c->channel<1 || c->channel>13 || c->connected>1 ||
       (c->phy!=2 && c->phy!=3) || c->enc_status!=6 ||
       c->short_preamble>1 || c->short_slot>1 || c->erp_protection>1 ||
       !c->operational || !c->basic || (c->operational&~0x3fcfU) ||
       (c->basic&~c->operational) || (c->own[0]&1) || (c->ap[0]&1))return 0;
    unsigned own=0,ap=0,different=0;
    for(unsigned i=0;i<6;i++){own|=c->own[i];ap|=c->ap[i];different|=c->own[i]^c->ap[i];}
    if(!own || !ap || !different)return 0;
    /* Public media-state enum is connected0/disconnected1, not a Boolean. */
    uint8_t p[88]={0};p[9]=c->connected?0:1;p[11]=c->ssid_length;
    for(unsigned i=0;i<c->ssid_length;i++)p[12+i]=c->ssid[i];
    for(unsigned i=0;i<6;i++){p[44+i]=c->ap[i];p[63+i]=c->own[i];}
    p[52]=(uint8_t)c->operational;p[53]=(uint8_t)(c->operational>>8);
    p[54]=(uint8_t)c->basic;p[55]=(uint8_t)(c->basic>>8);
    p[56]=c->connected?0:0xfe;
    p[59]=1; /* ERP non-HT basic PHY index, unlike PHY bit set2/3. */
    p[60]=7;p[61]=c->enc_status;p[62]=c->phy;
    p[73]=1;p[74]=c->channel;p[76]=c->erp_protection;
    p[85]=c->short_preamble;p[86]=c->short_slot;p[87]=0x72;
    for(unsigned i=0;i<88;i++)out[i]=p[i];
    return 88;
}
