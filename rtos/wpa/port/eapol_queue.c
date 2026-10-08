/* SPDX-License-Identifier: MIT */
#include "eapol_queue.h"
static void wipe(void *p,size_t n){volatile uint8_t *v=p;while(n--)*v++=0;}
int tuvl_eapol_queue_push(struct tuvl_eapol_queue *q,const uint8_t *p,size_t n)
{
    if(!q || q->failed)return -1;
    if(!p || n<30 || n>TUVL_EAPOL_RX_MAX || q->count==TUVL_EAPOL_QUEUE_DEPTH){
        q->failed=1;return -1;
    }
    unsigned slot=(q->head+q->count)%TUVL_EAPOL_QUEUE_DEPTH;
    for(size_t i=0;i<n;i++)q->packet[slot][i]=p[i];
    q->length[slot]=n;q->count++;return 0;
}
const uint8_t *tuvl_eapol_queue_front(const struct tuvl_eapol_queue *q,size_t *n)
{
    if(n)*n=0;
    if(!q || !n || q->failed || !q->count)return NULL;
    *n=q->length[q->head];return q->packet[q->head];
}
void tuvl_eapol_queue_pop(struct tuvl_eapol_queue *q)
{
    if(!q || !q->count)return;
    wipe(q->packet[q->head],sizeof q->packet[q->head]);q->length[q->head]=0;
    q->head=(q->head+1)%TUVL_EAPOL_QUEUE_DEPTH;q->count--;
}
void tuvl_eapol_queue_clear(struct tuvl_eapol_queue *q){if(q)wipe(q,sizeof *q);}
