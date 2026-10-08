/* SPDX-License-Identifier: MIT */
#include "key-ledger.h"
#include "mt5931-key.h"
static void wipe(void *p,size_t n){volatile uint8_t *v=p;while(n--)*v++=0;}
static int same(const uint8_t *a,const uint8_t *b,size_t n){while(n--)if(*a++!=*b++)return 0;return 1;}
int tuvl_key_ledger_submit(struct tuvl_key_ledger *l,tuvl_key_submit_fn send,void *ctx,
    const uint8_t *p,size_t n)
{
    uint8_t canonical[64];
    if(!l || !send || !p || n!=64 || l->failed || l->busy || p[0]>1 || p[2]>1 ||
       p[1]!=(p[0]?p[2]:0))return -1;
    struct tuvl_mt5931_key req={p[0],p[1],p[2],p[12],p+4,p+16,p[13],NULL,0};
    size_t valid=tuvl_mt5931_key_body(canonical,sizeof canonical,&req);
    int matched=valid==64 && same(p,canonical,64);wipe(canonical,sizeof canonical);
    if(!matched)return -1;
    unsigned index=p[2]?0:1+p[12];
    struct tuvl_key_slot *s=&l->slot[index];
    if(s->pending && !same(s->peer,p+4,6))return -1;
    if(!p[0] && !s->pending)return 0; /* No repeated removal of an empty slot. */
    if(p[0]){
        for(unsigned i=0;i<6;i++)s->peer[i]=p[4+i];
        s->pending=1; /* The attempt may reach hardware even if send fails. */
    }
    l->busy=1;int result=send(ctx,p,n);l->busy=0;
    if(result){l->failed=1;return -1;}
    if(!p[0])wipe(s,sizeof *s);
    return 0;
}
int tuvl_key_ledger_close(struct tuvl_key_ledger *l,tuvl_key_submit_fn send,void *ctx)
{
    if(!l || !send || l->failed || l->busy)return -1;
    for(unsigned i=0;i<5;i++)if(l->slot[i].pending){
        uint8_t body[64];
        struct tuvl_mt5931_key req={0,0,i==0,i?i-1:0,l->slot[i].peer,NULL,0,NULL,0};
        if(tuvl_mt5931_key_body(body,sizeof body,&req)!=64){l->failed=1;return -1;}
        int result=tuvl_key_ledger_submit(l,send,ctx,body,sizeof body);
        wipe(body,sizeof body);
        if(result)return -1;
    }
    return 0;
}
