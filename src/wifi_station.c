/* SPDX-License-Identifier: MIT. Independent MT5931 station wire format. */
#include "wifi_station.h"
unsigned wifi_station_pack(uint8_t *out,unsigned capacity,const struct wifi_station_config *c){
    if(!out || !c || capacity<48 || c->network>1 || (c->peer[0]&1) ||
       c->aid>2007 || !c->listen || c->state<1 || c->state>3 ||
       (c->phy!=2 && c->phy!=3) || !c->operational ||
       (c->operational&~0x3fcfU) || (c->basic&~0x3fcfU) ||
       (!c->network && c->state==3 && !c->aid))return 0;
    unsigned nonzero=0;for(unsigned i=0;i<6;i++)nonzero|=c->peer[i];
    if(!nonzero)return 0;
    uint8_t p[48]={0};
    /* Authentication starts with the P2P-network provisional client role.
     * Our open AP accepts ordinary infrastructure clients, not P2P GCs. */
    p[9]=c->network?(c->state==3?0x21:0x22):0x41;
    for(unsigned i=0;i<6;i++)p[10+i]=c->peer[i];
    p[16]=(uint8_t)c->aid;p[17]=(uint8_t)(c->aid>>8);
    p[18]=(uint8_t)c->listen;p[19]=(uint8_t)(c->listen>>8);
    p[20]=c->network;p[21]=c->phy;
    p[22]=(uint8_t)c->operational;p[23]=(uint8_t)(c->operational>>8);
    p[24]=(uint8_t)c->basic;p[25]=(uint8_t)(c->basic>>8);
    /* Host class states 1/2/3 are encoded by the radio as 0/1/2. */
    p[28]=c->state-1;p[41]=c->rcpi;p[42]=c->state==3;
    for(unsigned i=0;i<48;i++)out[i]=p[i];
    return 48;
}
