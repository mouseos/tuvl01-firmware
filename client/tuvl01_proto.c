/* SPDX-License-Identifier: MIT */
#include "tuvl01_proto.h"
static uint32_t be32(const uint8_t *p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint16_t be16(const uint8_t *p){return (uint16_t)((p[0]<<8)|p[1]);}
size_t tuvl01_build_request(uint8_t *out,uint8_t op,uint16_t id){
    out[0]='T';out[1]='C';out[2]='T';out[3]='1';out[4]=op;out[5]=0;out[6]=(uint8_t)(id>>8);out[7]=(uint8_t)id;
    return TUVL01_REQUEST_SIZE;
}
size_t tuvl01_build_tune_request(uint8_t *out,uint8_t channel,uint8_t partial,uint16_t id){
    tuvl01_build_request(out,TUVL01_OP_TUNE,id);out[8]=channel;out[9]=partial;return TUVL01_REQUEST_SIZE+2;
}
int tuvl01_parse_reply(const uint8_t *d,size_t n,tuvl01_reply *r){
    if(!d || !r || n<9 || d[0]!='T' || d[1]!='C' || d[2]!='T' || d[3]!='1' || !(d[4]&0x80))return -1;
    unsigned op=d[4]&0x7f;
    r->op=(uint8_t)op;r->status=d[5];r->id=be16(d+6);r->state=0;r->version=0;r->revision=0;
    r->stream_port=0;r->caps=0;r->channel=0;r->first_channel=r->last_channel=0;r->partial=r->tune=0;r->lock=255;
    if(r->status!=TUVL01_STATUS_OK)return 0;
    if(op==TUVL01_OP_HELLO){
        if(n<18)return -1;
        r->version=d[8];r->revision=be16(d+9);r->caps=be32(d+11);r->stream_port=be16(d+15);r->state=d[17];
        if(n>=20){r->first_channel=d[18];r->last_channel=d[19];}
    }else if(op==TUVL01_OP_STATUS){
        if(n<12)return -1;
        r->state=d[8];r->channel=be16(d+9);
        if(n>=14){r->partial=d[11];r->tune=d[12];r->lock=d[13];}
    }else r->state=d[8];
    return 0;
}
int tuvl01_parse_stream(const uint8_t *d,size_t n,tuvl01_stream *s){
    if(!d || !s || n<204 || n>TUVL01_STREAM_MAX_DATAGRAM || d[0]!='T' || d[1]!='T' || d[2]!='S' || d[3]!='1' ||
       (n-16)%188)return -1;
    s->sequence=be32(d+4);s->index=be32(d+8);s->flags=be32(d+12);
    if(s->flags&~1U)return -1;
    s->ts=d+16;s->packets=(n-16)/188;return 0;
}
void tuvl01_loss_init(tuvl01_loss *l){
    l->expected=0;l->started=0;l->datagrams=l->missing=l->resyncs=l->reordered=l->invalid=0;
}
int tuvl01_loss_update(tuvl01_loss *l,const tuvl01_stream *s){
    /* A START begins a new stream whose first datagram is sequence 0 / packet index 0 (docs/protocol.md).
     * That datagram is never "late" for the previous stream, whatever position it had reached. */
    if(l->started && s->sequence==0 && s->index==0 && l->expected!=0)l->started=0;
    if(l->started){
        uint32_t delta=s->sequence-l->expected;
        if(delta>=0x80000000U){++l->reordered;return 1;}
        l->missing+=delta;
    }
    l->started=1;l->expected=s->sequence+1;++l->datagrams;l->resyncs+=s->flags&1U;return 0;
}

