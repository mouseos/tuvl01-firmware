/* SPDX-License-Identifier: MIT */
#include "supplicant-send.h"
#include "mt5931-eapol.h"
static void wipe(struct tuvl_send_transport *t)
{
    volatile uint8_t *p=(volatile uint8_t *)t->packet;
    size_t i;for(i=0;i<sizeof(t->packet);i++)p[i]=0;
}
int tuvl_supplicant_send(void *ctx,const uint8_t *frame,size_t n)
{
    struct tuvl_send_transport *t=ctx;
    size_t i,padded;unsigned own=0,ap=0,different=0;
    int result=-1;
    if(!t || t->busy)return -1;
    t->busy=1;
    if(!t->submit || !frame || n<18 || n>2062 ||
       (t->own[0]&1) || (t->ap[0]&1))goto done;
    for(i=0;i<6;i++){
        own|=t->own[i];ap|=t->ap[i];different|=t->own[i]^t->ap[i];
        if(frame[i]!=t->ap[i] || frame[6+i]!=t->own[i])goto done;
    }
    if(!own || !ap || !different)goto done;
    padded=tuvl_mt5931_eapol_tx((uint8_t *)t->packet,sizeof(t->packet),frame,n);
    if(!padded)goto done;
    if(!t->submit(t->ctx,TUVL_EAPOL_PORT,TUVL_EAPOL_TC,
                  (const uint8_t *)t->packet,padded))result=0;
done:
    wipe(t);t->busy=0;return result;
}
