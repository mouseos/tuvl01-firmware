/* SPDX-License-Identifier: MIT. Independent bounded RSN selection policy. */
#include "wifi_ais_rsn.h"
static unsigned le16(const uint8_t *p){return p[0]|((unsigned)p[1]<<8);}
static int suite(const uint8_t *p,unsigned type){
    return !p[0] && p[1]==15 && p[2]==172 && p[3]==type;
}
static int list(const uint8_t *p,unsigned n,unsigned *pos,unsigned type){
    if(n-*pos<2)return 0;
    unsigned count=le16(p+*pos);*pos+=2;
    if(!count || count>(n-*pos)/4)return 0;
    unsigned found=0;
    while(count--){found|=suite(p+*pos,type);*pos+=4;}
    return found;
}
unsigned wifi_ais_rsn_select(const uint8_t *p,unsigned n,uint8_t *out,unsigned capacity){
    static const uint8_t selection[]={48,20,1,0,0,15,172,4,1,0,0,15,172,4,
        1,0,0,15,172,2,0,0};
    if(!p || !out || capacity<sizeof selection || n<18 || n>257 ||
       p[0]!=48 || p[1]!=n-2 || le16(p+2)!=1 || !suite(p+4,4))return 0;
    unsigned pos=8;
    if(!list(p,n,&pos,4) || !list(p,n,&pos,2))return 0;
    if(pos<n){
        if(n-pos<2 || (le16(p+pos)&0x40))return 0; /* MFPR */
        pos+=2;
    }
    if(pos<n){
        if(n-pos<2 || le16(p+pos))return 0; /* No cached PMKID */
        pos+=2;
    }
    if(pos<n){
        if(n-pos!=4 || !suite(p+pos,6))return 0; /* Optional BIP-CMAC-128 */
        pos+=4;
    }
    if(pos!=n)return 0;
    for(unsigned i=0;i<sizeof selection;i++)out[i]=selection[i];
    return sizeof selection;
}
