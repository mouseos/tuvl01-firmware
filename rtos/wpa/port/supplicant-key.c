/* SPDX-License-Identifier: MIT. Independent callback-to-wire bridge. */
#include "supplicant-key.h"
#include "mt5931-key.h"
static int same(const u8 *a,const u8 *b){
    for(unsigned i=0;i<6;i++)if(a[i]!=b[i])return 0;
    return 1;
}
int tuvl_supplicant_key(void *ctx,int link,enum wpa_alg alg,const u8 *addr,
    int index,int tx,const u8 *seq,size_t sn,const u8 *key,size_t kn,enum key_flag flags){
    struct tuvl_key_transport *t=ctx;
    static const u8 broadcast[6]={255,255,255,255,255,255};
    if(!t || !t->submit || !addr || link!=-1 || index<0 || index>3 ||
       (tx!=0 && tx!=1) || (t->ap[0]&1))return -1;
    unsigned valid=0;for(unsigned i=0;i<6;i++)valid|=t->ap[i];
    if(!valid || (!same(addr,t->ap) && !same(addr,broadcast)))return -1;
    unsigned pairwise=flags==KEY_FLAG_PAIRWISE_RX_TX;
    if(!pairwise && flags!=KEY_FLAG_GROUP_RX)return -1;
    if(pairwise && (index || !same(addr,t->ap)))return -1;
    if(alg==WPA_ALG_CCMP){
        if(tx!=(int)pairwise || !key || kn!=16)return -1;
    }else if(alg!=WPA_ALG_NONE || tx || sn || kn)return -1;
    struct tuvl_mt5931_key req={alg==WPA_ALG_CCMP,(unsigned)tx,pairwise,
        (unsigned)index,addr,key,kn,NULL,0};
    u8 body[64];
    if(!tuvl_mt5931_key_zero_sequence(body,sizeof body,&req,seq,sn))return -1;
    int result=t->submit(t->ctx,body,sizeof body);
    volatile u8 *wipe=body;for(unsigned i=0;i<sizeof body;i++)wipe[i]=0;
    return result==0?0:-1;
}
