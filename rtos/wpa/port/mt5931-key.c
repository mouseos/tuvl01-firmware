/* SPDX-License-Identifier: MIT; no manufacturer implementation copied. */
#include "mt5931-key.h"
size_t tuvl_mt5931_key_body(uint8_t *out,size_t capacity,
                           const struct tuvl_mt5931_key *req)
{
    uint8_t body[64];
    size_t i;
    unsigned nonzero=0, broadcast=1;
    if(!out || capacity<64 || !req || !req->peer || req->add>1 ||
       req->transmit>1 || req->pairwise>1 || req->index>3 ||
       (req->pairwise && req->index!=0)) return 0;
    if(req->add) {
        if(!req->key || req->key_length!=16 ||
           (req->rsc_length!=0 && req->rsc_length!=16) ||
           (req->rsc_length && !req->rsc)) return 0;
    } else if(req->key_length || req->rsc_length || req->transmit) return 0;
    for(i=0;i<6;i++) {
        nonzero|=req->peer[i];
        if(req->peer[i]!=0xff) broadcast=0;
    }
    if(!nonzero || ((req->peer[0]&1) && (req->pairwise || !broadcast))) return 0;
    for(i=0;i<64;i++) body[i]=0;
    body[0]=(uint8_t)req->add;
    body[1]=(uint8_t)req->transmit;
    body[2]=(uint8_t)req->pairwise;
    /* authenticator=0, network=AIS0; no struct packing/native endian. */
    for(i=0;i<6;i++) body[4+i]=req->peer[i];
    body[11]=(uint8_t)(req->add ? 4 : 0); /* CIPHER_SUITE_CCMP, public privacy.h */
    body[12]=(uint8_t)req->index;
    if(req->add) {
        body[13]=16;
        for(i=0;i<16;i++) body[16+i]=req->key[i];
        for(i=0;i<req->rsc_length;i++) body[48+i]=req->rsc[i];
    }
    for(i=0;i<64;i++) out[i]=body[i];
    { volatile uint8_t *v=body; for(i=0;i<64;i++) v[i]=0; }
    return 64;
}
size_t tuvl_mt5931_key_zero_sequence(uint8_t *out,size_t capacity,
    const struct tuvl_mt5931_key *req,const uint8_t *seq,size_t seq_length)
{
    size_t i;
    if(!req || req->rsc_length || (seq_length!=0 && seq_length!=6) ||
       (seq_length && !seq) || (!req->add && seq_length))return 0;
    for(i=0;i<seq_length;i++)if(seq[i])return 0;
    return tuvl_mt5931_key_body(out,capacity,req);
}
int tuvl_mt5931_key_result(const uint8_t *p,size_t n,uint8_t sequence,
                           uint8_t *status)
{
    if(!p || !status || n!=12 || (p[0]|((unsigned)p[1]<<8))!=n ||
       p[2]!=1 || p[3]!=0 || p[4]!=1 || p[5]!=sequence || p[8]!=8) return 0;
    *status=p[9];
    return 1;
}
