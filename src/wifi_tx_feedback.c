/* SPDX-License-Identifier: MIT. Independent sampled TX status bookkeeping. */
#include "wifi_tx_feedback.h"
int wifi_tx_feedback_reserve(struct wifi_tx_feedback *s,uint32_t sequence,uint8_t *tag){
    if(!s || !tag)return 0;
    for(unsigned n=0;n<128;n++){
        unsigned slot=(s->next+n)&127U;
        if(s->occupied[slot])continue;
        s->occupied[slot]=1;s->sequence[slot]=sequence;s->next=(slot+1)&127U;
        ++s->requested;++s->pending;*tag=(uint8_t)(slot|128U);return 1;
    }
    ++s->skipped;return 0;
}
int wifi_tx_feedback_complete(struct wifi_tx_feedback *s,uint8_t tag,uint8_t status,uint32_t *sequence){
    if(!s || !(tag&128U))return 0;
    unsigned slot=tag&127U;
    if(!s->occupied[slot]){++s->unmatched;return 0;}
    if(sequence)*sequence=s->sequence[slot];
    s->occupied[slot]=0;--s->pending;++s->completed;++s->status[status];return 1;
}
void wifi_tx_feedback_cancel(struct wifi_tx_feedback *s,uint8_t tag){
    if(!s || !(tag&128U) || !s->occupied[tag&127U])return;
    s->occupied[tag&127U]=0;--s->pending;++s->cancelled;
}
