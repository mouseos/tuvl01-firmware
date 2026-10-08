/* SPDX-License-Identifier: MIT. Independent station protocol serializer. */
#include "wifi_fixed_rate.h"
int wifi_fixed_rate_apply(uint8_t *p,unsigned length,unsigned legacy,unsigned mcs,const struct wifi_ht_peer *peer){
    if(!p || length!=48 || legacy>2 || mcs>2 || (legacy && mcs))return 0;
    if(legacy && !(p[23]&0x20))return 0;
    unsigned index=mcs==2?7:0;
    if(mcs && (!wifi_ht_active(peer) || !(peer->mcs&(1U<<index))))return 0;
    if(!legacy && !mcs)return 1;
    p[21]=legacy?2:8;p[22]=p[24]=0;p[23]=p[25]=legacy?0x20:0x40;
    p[29]=legacy?0:index;p[30]=0;
    if(legacy)p[32]=p[33]=0;
    else p[32]&=(uint8_t)~0x72U; /*20MHz/long GI/no greenfield*/
    return 1;
}
